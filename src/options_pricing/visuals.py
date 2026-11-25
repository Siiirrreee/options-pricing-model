"""Static charts (PNG) for the README."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from . import black_scholes as bs  # noqa: E402

BLUE, ORANGE, GREEN, GREY, RED = "#2a6fdb", "#e8832a", "#2e9e6a", "#8a8f98", "#d64545"
plt.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 150, "font.size": 10,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "axes.titleweight": "bold",
})


def _save(fig, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def price_curves(out: Path, K: float, T: float, r: float) -> None:
    """Call and put value vs. underlying price, for several volatilities."""
    S = np.linspace(K * 0.8, K * 1.2, 300)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for ax, kind in zip(axes, ("call", "put")):
        payoff = np.maximum(S - K, 0) if kind == "call" else np.maximum(K - S, 0)
        ax.plot(S, payoff, color="black", lw=1, ls="--", label="Payoff at expiry")
        for sig, c in zip((0.10, 0.20, 0.35), (GREEN, BLUE, ORANGE)):
            ax.plot(S, bs.price(S, K, T, r, sig, kind), color=c, lw=2, label=f"σ = {sig:.0%}")
        ax.axvline(K, color=GREY, lw=0.8)
        ax.set_title(f"European {kind} (K = {K:,.0f}, {T*365:.0f} days)")
        ax.set_xlabel("Underlying price")
    axes[0].set_ylabel("Option value")
    axes[0].legend(frameon=False)
    _save(fig, out)


def greeks_panel(out: Path, K: float, T: float, r: float, sigma: float) -> None:
    """The five Greeks vs. underlying price for a call and a put."""
    S = np.linspace(K * 0.85, K * 1.15, 300)
    gc, gp = bs.greeks(S, K, T, r, sigma, "call"), bs.greeks(S, K, T, r, sigma, "put")
    titles = {"delta": "Delta (per $1)", "gamma": "Gamma (per $1)", "vega": "Vega (per 1 vol pt)",
              "theta": "Theta (per day)", "rho": "Rho (per 1% rate)"}
    fig, axes = plt.subplots(1, 5, figsize=(17, 3.6))
    for ax, g in zip(axes, titles):
        ax.plot(S, gc[g], color=BLUE, lw=2, label="Call")
        ax.plot(S, gp[g], color=ORANGE, lw=2, ls="--" if g in ("gamma", "vega") else "-", label="Put")
        ax.axvline(K, color=GREY, lw=0.8)
        ax.set_title(titles[g])
        ax.set_xlabel("Underlying price")
    axes[0].legend(frameon=False)
    fig.suptitle(f"Black-Scholes Greeks  (K = {K:,.0f}, σ = {sigma:.0%}, {T*365:.0f} days, r = {r:.1%})",
                 fontweight="bold", y=1.03)
    _save(fig, out)


def time_decay(out: Path, K: float, r: float, sigma: float) -> None:
    """At-the-money vs. out-of-the-money call value as expiration approaches."""
    days = np.linspace(90, 0.5, 300)
    T = days / 365
    fig, ax = plt.subplots(figsize=(7.5, 4))
    for mny, c, lab in ((1.00, BLUE, "At the money (S = K)"), (0.97, ORANGE, "3% out of the money"),
                        (0.94, GREEN, "6% out of the money")):
        ax.plot(days, bs.price(K * mny, K, T, r, sigma, "call"), color=c, lw=2, label=lab)
    ax.invert_xaxis()
    ax.set_xlabel("Days to expiration")
    ax.set_ylabel("Call value")
    ax.set_title(f"Time decay accelerates near expiry (σ = {sigma:.0%})")
    ax.legend(frameon=False)
    _save(fig, out)


def volatility_smile(out: Path, smile: pd.DataFrame, forward: float, atm: float, label: str) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 4.4))
    puts, calls = smile[smile["type"] == "put"], smile[smile["type"] == "call"]
    ax.plot(puts["strike"], puts["iv"] * 100, "o-", color=ORANGE, ms=4, label="OTM puts (market)")
    ax.plot(calls["strike"], calls["iv"] * 100, "o-", color=BLUE, ms=4, label="OTM calls (market)")
    ax.axhline(atm * 100, color=GREY, ls="--", lw=1.2, label=f"Black-Scholes assumption: one vol ({atm:.1%})")
    ax.axvline(forward, color="black", lw=0.8)
    ax.text(forward, ax.get_ylim()[1] * 0.97, " forward", va="top", fontsize=9)
    ax.set_xlabel("Strike")
    ax.set_ylabel("Implied volatility (%)")
    ax.set_title(f"Volatility skew: {label}")
    ax.legend(frameon=False)
    _save(fig, out)


def model_vs_market(out: Path, comp: pd.DataFrame, label: str) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
    ax = axes[0]
    for kind, c in (("put", ORANGE), ("call", BLUE)):
        sub = comp[comp["type"] == kind]
        ax.errorbar(sub["strike"], sub["mid"], yerr=[sub["mid"] - sub["bid"], sub["ask"] - sub["mid"]],
                    fmt="o", color=c, ms=4, capsize=2, label=f"Market {kind}s (bid/mid/ask)")
        ax.plot(sub["strike"], sub["bs_price"], "-", color=c, lw=1.5, alpha=0.7,
                label=f"Black-Scholes {kind}s, one flat vol")
    ax.set_yscale("log")
    ax.set_xlabel("Strike")
    ax.set_ylabel("Option price (log scale)")
    ax.set_title("Model vs. market prices")
    ax.legend(frameon=False, fontsize=8)

    ax = axes[1]
    colors = np.where(comp["error"] < 0, RED, GREEN)
    ax.bar(comp["strike"], comp["error_pct"] * 100, width=35, color=colors)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xlabel("Strike")
    ax.set_ylabel("Model − market (% of market mid)")
    ax.set_title("Flat-vol pricing error: underprices crash protection")
    fig.suptitle(label, fontweight="bold", y=1.02)
    _save(fig, out)
