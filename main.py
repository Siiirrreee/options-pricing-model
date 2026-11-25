"""Run the full options pricing pipeline.

Examples
--------
python main.py                         # bundled SPX snapshot (2026-11-24 close), works offline
python main.py --rf 0.045              # different risk-free rate
python main.py --live SPY              # fetch a current chain with yfinance (needs internet)
python -m pytest                       # run the tests
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from options_pricing import black_scholes as bs  # noqa: E402
from options_pricing import market, visuals  # noqa: E402

BUCKETS = [(0, 0.90, "Deep OTM puts (K < 90% of F)"), (0.90, 0.97, "OTM puts (90–97%)"),
           (0.97, 1.03, "Near the money (97–103%)"), (1.03, 9, "OTM calls (K > 103%)")]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Black-Scholes Options Pricing Model")
    p.add_argument("--rf", type=float, default=0.042,
                   help="Annual risk-free rate (default 4.2%%, 3-month T-bill, Nov 2026)")
    p.add_argument("--live", metavar="TICKER", help="Fetch a live chain via yfinance instead of the snapshot")
    p.add_argument("--expiration", help="YYYY-MM-DD expiration for --live")
    return p.parse_args()


def pct(x: float, d: int = 1) -> str:
    return f"{x:.{d}%}"


def main() -> None:
    args = parse_args()
    results, vis = ROOT / "results", ROOT / "visuals"
    results.mkdir(exist_ok=True)
    vis.mkdir(exist_ok=True)

    # 1. Data -----------------------------------------------------------------
    if args.live:
        chain, spot = market.fetch_live_chain(args.live, args.expiration)
        chain["mid"] = (chain["bid"] + chain["ask"]) / 2
        chain["spread_pct"] = (chain["ask"] - chain["bid"]) / chain["mid"]
        label = f"{args.live} options expiring {chain['expiration'].iloc[0]}"
    else:
        chain = market.load_chain(ROOT / "data" / market.SNAPSHOT_FILE)
        spot = market.SNAPSHOT_SPOT
        label = "SPX options expiring 2026-12-18 (quotes at 2026-11-24 close)"
    quote_date, expiration = chain["quote_date"].iloc[0], chain["expiration"].iloc[0]
    T = market.year_fraction(quote_date, expiration)
    r = args.rf
    clean = market.clean_chain(chain)

    # 2. Rates and forward from put-call parity ---------------------------------
    r_implied, _, _ = market.parity_rates(clean, spot, T)
    forward = market.parity_forward(clean, spot, T, r)
    s_eff = forward * np.exp(-r * T)          # price off the forward (Black-76 equivalent), q = 0

    # 3. Implied volatility smile -------------------------------------------------
    ivs = market.add_implied_vols(clean, s_eff, T, r, 0.0)
    smile = market.otm_smile(ivs, forward)
    atm = market.atm_vol(smile, forward)

    # 4. Flat-vol Black-Scholes vs market ---------------------------------------
    comp = market.compare_flat_vol(smile, s_eff, T, r, 0.0, atm)
    comp["moneyness_f"] = comp["strike"] / forward
    rows = []
    for lo, hi, name in BUCKETS:
        b = comp[(comp["moneyness_f"] >= lo) & (comp["moneyness_f"] < hi)]
        if len(b):
            rows.append({"Bucket": name, "Options": len(b), "Avg market IV": pct(b["iv"].mean()),
                         "Avg error ($)": f"{b['error'].mean():+.2f}", "Avg error (%)": pct(b["error_pct"].mean()),
                         "Inside bid/ask": f"{b['inside_spread'].mean():.0%}"})
    buckets = pd.DataFrame(rows)

    # 5. Example contracts: nearest-the-money call and put -------------------------
    k_atm_call = comp.loc[comp["type"] == "call", "strike"].iloc[0]
    k_atm_put = comp.loc[comp["type"] == "put", "strike"].iloc[-1]
    examples = []
    for kind, k in (("call", k_atm_call), ("put", k_atm_put)):
        row = comp[(comp["type"] == kind) & (comp["strike"] == k)].iloc[0]
        g = bs.greeks(s_eff, k, T, r, row["iv"], kind)
        examples.append({"Contract": f"{kind.title()} {k:,.0f}", "Market mid": f"{row['mid']:.2f}",
                         "Implied vol": pct(row["iv"]), "BS price @ IV": f"{bs.price(s_eff, k, T, r, row['iv'], kind):.2f}",
                         "Delta": f"{g['delta']:.3f}", "Gamma": f"{g['gamma']:.5f}", "Vega": f"{g['vega']:.2f}",
                         "Theta/day": f"{g['theta']:.2f}", "Rho": f"{g['rho']:.2f}"})
    examples = pd.DataFrame(examples)

    # 6. Save tables ------------------------------------------------------------
    ivs.to_csv(results / "implied_vols.csv", index=False)
    comp.to_csv(results / "model_vs_market.csv", index=False)
    buckets.to_csv(results / "error_by_moneyness.csv", index=False)
    examples.to_csv(results / "atm_greeks.csv", index=False)

    lo_put, hi_call = smile.iloc[0], smile.iloc[-1]
    deep = comp[comp["moneyness_f"] < 0.90]
    near = comp[(comp["moneyness_f"] >= 0.97) & (comp["moneyness_f"] < 1.03)]
    stats = {
        "label": label, "quote_date": quote_date, "expiration": expiration, "days": round(T * 365),
        "index_close": spot, "risk_free": r, "parity_implied_r": round(r_implied, 4),
        "forward": round(forward, 2), "parity_spot": round(s_eff, 2), "quotes_used": int(len(clean)),
        "otm_options": int(len(smile)), "atm_iv": round(atm, 4),
        "lowest_strike": float(lo_put["strike"]), "lowest_strike_iv": round(lo_put["iv"], 4),
        "highest_strike": float(hi_call["strike"]), "highest_strike_iv": round(hi_call["iv"], 4),
        "deep_otm_put_avg_error_pct": round(deep["error_pct"].mean(), 4) if len(deep) else None,
        "near_atm_inside_spread": round(near["inside_spread"].mean(), 4) if len(near) else None,
        "near_atm_abs_error_pct": round(near["error_pct"].abs().mean(), 4) if len(near) else None,
        "otm_call_avg_error_pct": round(comp.loc[comp["moneyness_f"] >= 1.03, "error_pct"].mean(), 4),
        "max_underpricing_pct": round(comp["error_pct"].min(), 4),
        "max_underpricing_strike": float(comp.loc[comp["error_pct"].idxmin(), "strike"]),
    }
    (results / "stats.json").write_text(json.dumps(stats, indent=2))

    # 7. Charts ---------------------------------------------------------------
    K = round(forward / 50) * 50
    visuals.price_curves(vis / "price_vs_spot.png", K, T, r)
    visuals.greeks_panel(vis / "greeks.png", K, T, r, atm)
    visuals.time_decay(vis / "time_decay.png", K, r, atm)
    visuals.volatility_smile(vis / "volatility_smile.png", smile, forward, atm, label)
    visuals.model_vs_market(vis / "model_vs_market.png", comp, label)

    # 8. Written summary ------------------------------------------------------
    findings = [
        f"Put-call parity puts the forward at **{forward:,.1f}** ({stats['days']} days, r = {pct(r)}). "
        f"A parity regression with no rate assumption implies r ≈ {pct(r_implied)}, close to the "
        f"{pct(r)} 3-month T-bill rate, a useful cross-check on the inputs.",
        f"At-the-money implied volatility is **{pct(atm)}**. The market does not use one number: the "
        f"{lo_put['strike']:,.0f} put trades at **{pct(lo_put['iv'])}** IV and the {hi_call['strike']:,.0f} "
        f"call at **{pct(hi_call['iv'])}**, a classic equity-index skew.",
        f"With a single flat vol, Black-Scholes underprices deep out-of-the-money puts by "
        f"**{pct(-stats['deep_otm_put_avg_error_pct'], 0)}** on average (worst: {pct(-stats['max_underpricing_pct'], 0)} "
        f"at the {stats['max_underpricing_strike']:,.0f} strike). Investors pay up for crash protection that "
        f"a lognormal model says is rare.",
        f"The same flat vol **overprices** out-of-the-money calls by {pct(stats['otm_call_avg_error_pct'], 0)} on "
        f"average: the market expects upside moves to be calmer than downside moves, which one volatility cannot capture.",
        f"Errors are smallest near the money (average absolute error {pct(stats['near_atm_abs_error_pct'], 0)}) "
        f"and grow fast in both tails: Black-Scholes works where it is calibrated and breaks down away from it.",
    ]
    table = buckets.to_markdown(index=False)
    greek_table = examples.to_markdown(index=False)
    block = (f"_{label}. {stats['quotes_used']} two-sided quotes after cleaning; "
             f"full detail in [results/summary.md](results/summary.md)._\n\n"
             f"**Flat-volatility Black-Scholes vs. market, by moneyness**\n\n{table}\n\n"
             f"**At-the-money contracts: price and Greeks at market implied vol**\n\n{greek_table}\n\n"
             f"**Key findings**\n\n" + "\n".join(f"- {f}" for f in findings))
    summary = (f"# Results summary\n\n{block}\n\n## Inputs\n\n"
               f"| Input | Value |\n|---|---|\n| Index close (4:00 pm) | {spot:,.2f} |\n"
               f"| Parity forward | {forward:,.2f} |\n| Spot implied by forward | {s_eff:,.2f} |\n"
               f"| Risk-free rate | {pct(r)} |\n| Parity-implied rate | {pct(r_implied, 2)} |\n"
               f"| Days to expiry | {stats['days']} |\n| ATM implied vol | {pct(atm, 2)} |\n\n"
               "The spot implied by parity sits below the 4:00 pm index print. The delayed option quotes and "
               "the index close were not captured at the same instant, so the model prices off the parity "
               "forward, which reflects where the options were actually trading.\n")
    (results / "summary.md").write_text(summary)

    readme = ROOT / "README.md"
    if readme.exists():
        text = readme.read_text()
        text = re.sub(r"<!-- RESULTS:START -->.*<!-- RESULTS:END -->",
                      f"<!-- RESULTS:START -->\n{block}\n<!-- RESULTS:END -->", text, flags=re.S)
        readme.write_text(text)

    print(summary)


if __name__ == "__main__":
    main()
