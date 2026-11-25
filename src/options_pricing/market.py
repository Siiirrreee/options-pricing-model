"""Load an option chain, clean it, and compare Black-Scholes prices with the market."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from . import black_scholes as bs

# Snapshot shipped with the repo: S&P 500 index (SPX) options, delayed quotes at the
# close on 2026-11-24, expiring 2026-12-18. Source: Yahoo Finance (Cboe data).
SNAPSHOT_FILE = "spx_chain_2026-11-24.csv"
SNAPSHOT_SPOT = 7201.09


def load_chain(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["mid"] = (df["bid"] + df["ask"]) / 2
    df["spread_pct"] = (df["ask"] - df["bid"]) / df["mid"]
    return df


def year_fraction(quote_date: str, expiration: str) -> float:
    """Calendar-day year fraction, close-to-close (4 pm to 4 pm)."""
    days = (datetime.fromisoformat(expiration) - datetime.fromisoformat(quote_date)).days
    return days / 365.0


def fetch_live_chain(ticker: str, expiration: str | None = None) -> tuple[pd.DataFrame, float]:
    """Download a current chain with yfinance (run locally; needs internet).

    Returns the chain in the same format as the bundled snapshot plus the spot price.
    """
    import yfinance as yf  # imported lazily so the snapshot works offline

    tk = yf.Ticker(ticker)
    expiration = expiration or tk.options[min(3, len(tk.options) - 1)]
    chain = tk.option_chain(expiration)
    spot = float(tk.history(period="1d")["Close"].iloc[-1])
    frames = []
    for kind, raw in (("call", chain.calls), ("put", chain.puts)):
        frames.append(pd.DataFrame({
            "quote_date": datetime.today().strftime("%Y-%m-%d"),
            "expiration": expiration,
            "type": kind,
            "root": ticker,
            "strike": raw["strike"],
            "bid": raw["bid"],
            "ask": raw["ask"],
            "last": raw["lastPrice"],
            "volume": raw["volume"].fillna(0).astype(int),
            "open_interest": raw["openInterest"].fillna(0).astype(int),
        }))
    return pd.concat(frames, ignore_index=True), spot


def clean_chain(df: pd.DataFrame, min_mid: float = 0.50, max_spread_pct: float = 0.25) -> pd.DataFrame:
    """Keep quotes that are two-sided, not tiny, and not too wide to trust."""
    keep = (df["bid"] > 0) & (df["ask"] > df["bid"]) & (df["mid"] >= min_mid) & (df["spread_pct"] <= max_spread_pct)
    return df.loc[keep].copy()


def _pairs(df: pd.DataFrame, spot: float, band: float):
    calls = df[df["type"] == "call"].set_index("strike")["mid"]
    puts = df[df["type"] == "put"].set_index("strike")["mid"]
    strikes = calls.index.intersection(puts.index)
    strikes = strikes[(strikes > spot * (1 - band)) & (strikes < spot * (1 + band))]
    return strikes.values.astype(float), calls[strikes].values, puts[strikes].values


def parity_rates(df: pd.DataFrame, spot: float, T: float, band: float = 0.10) -> tuple[float, float, float]:
    """Market-implied r, q and forward from a put-call parity regression (a sanity check on r)."""
    return bs.implied_rates_from_parity(*_pairs(df, spot, band), spot, T)


def parity_forward(df: pd.DataFrame, spot: float, T: float, r: float, band: float = 0.05) -> float:
    """Forward price implied by put-call parity, given r:  F = K + e^(rT) * (C - P).

    Index desks price off the forward instead of spot: it bakes in dividends and
    removes any timing mismatch between the index print and the option quotes.
    The median across near-the-money strikes is robust to a single bad quote.
    """
    strikes, c, p = _pairs(df, spot, band)
    return float(np.median(strikes + np.exp(r * T) * (c - p)))


def add_implied_vols(df: pd.DataFrame, spot: float, T: float, r: float, q: float) -> pd.DataFrame:
    df = df.copy()
    df["iv"] = [bs.implied_vol(m, spot, k, T, r, kind, q)
                for m, k, kind in zip(df["mid"], df["strike"], df["type"])]
    df["moneyness"] = df["strike"] / spot
    return df


def otm_smile(df: pd.DataFrame, forward: float) -> pd.DataFrame:
    """Out-of-the-money options only (puts below the forward, calls above) - the liquid side."""
    otm = ((df["type"] == "put") & (df["strike"] < forward)) | ((df["type"] == "call") & (df["strike"] >= forward))
    return df.loc[otm & df["iv"].notna()].sort_values("strike").reset_index(drop=True)


def atm_vol(smile: pd.DataFrame, forward: float) -> float:
    """Implied volatility at the forward, linearly interpolated between neighbouring strikes."""
    return float(np.interp(forward, smile["strike"], smile["iv"]))


def compare_flat_vol(smile: pd.DataFrame, spot: float, T: float, r: float, q: float, sigma: float) -> pd.DataFrame:
    """Price every option with ONE volatility (classic Black-Scholes) and measure the error."""
    out = smile.copy()
    out["bs_price"] = [bs.price(spot, k, T, r, sigma, kind, q) for k, kind in zip(out["strike"], out["type"])]
    out["error"] = out["bs_price"] - out["mid"]
    out["error_pct"] = out["error"] / out["mid"]
    out["inside_spread"] = (out["bs_price"] >= out["bid"]) & (out["bs_price"] <= out["ask"])
    greeks = bs.greeks(spot, out["strike"].values, T, r, out["iv"].values, "call", q)
    put_greeks = bs.greeks(spot, out["strike"].values, T, r, out["iv"].values, "put", q)
    is_call = (out["type"] == "call").values
    for g in greeks:
        out[g] = np.where(is_call, greeks[g], put_greeks[g])
    return out
