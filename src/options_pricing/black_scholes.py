"""Black-Scholes-Merton pricing, Greeks and implied volatility for European options.

Conventions
-----------
S      spot price of the underlying
K      strike price
T      time to expiration in years (calendar days / 365)
r      continuously compounded risk-free rate (0.04 = 4%)
sigma  annualized volatility (0.20 = 20%)
q      continuously compounded dividend yield (0.0 for a non-dividend stock)
kind   "call" or "put"

Greeks are returned in the units traders quote:
delta  change in option price per $1 move in S
gamma  change in delta per $1 move in S
vega   change in price per 1 percentage point change in volatility
theta  change in price per calendar day that passes
rho    change in price per 1 percentage point change in r
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm

ArrayLike = float | np.ndarray


def _check_kind(kind: str) -> str:
    kind = kind.lower()
    if kind not in ("call", "put"):
        raise ValueError(f"kind must be 'call' or 'put', got {kind!r}")
    return kind


def d1_d2(S: ArrayLike, K: ArrayLike, T: ArrayLike, r: float, sigma: ArrayLike, q: float = 0.0):
    """Return the d1 and d2 terms of the Black-Scholes formula."""
    S, K, T, sigma = map(np.asarray, (S, K, T, sigma))
    vol_sqrt_t = sigma * np.sqrt(T)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / vol_sqrt_t
    return d1, d1 - vol_sqrt_t


def price(S: ArrayLike, K: ArrayLike, T: ArrayLike, r: float, sigma: ArrayLike,
          kind: str = "call", q: float = 0.0) -> ArrayLike:
    """Black-Scholes-Merton price of a European call or put."""
    kind = _check_kind(kind)
    d1, d2 = d1_d2(S, K, T, r, sigma, q)
    disc_s = S * np.exp(-q * np.asarray(T))
    disc_k = K * np.exp(-r * np.asarray(T))
    if kind == "call":
        out = disc_s * norm.cdf(d1) - disc_k * norm.cdf(d2)
    else:
        out = disc_k * norm.cdf(-d2) - disc_s * norm.cdf(-d1)
    return float(out) if np.ndim(out) == 0 else out


def greeks(S: ArrayLike, K: ArrayLike, T: ArrayLike, r: float, sigma: ArrayLike,
           kind: str = "call", q: float = 0.0) -> dict[str, ArrayLike]:
    """All five first-order Greeks (plus gamma) in trader units. See module docstring."""
    kind = _check_kind(kind)
    S, K, T, sigma = map(np.asarray, (S, K, T, sigma))
    d1, d2 = d1_d2(S, K, T, r, sigma, q)
    eq, er = np.exp(-q * T), np.exp(-r * T)
    pdf_d1 = norm.pdf(d1)

    gamma = eq * pdf_d1 / (S * sigma * np.sqrt(T))
    vega = S * eq * pdf_d1 * np.sqrt(T) / 100.0
    common_theta = -S * eq * pdf_d1 * sigma / (2 * np.sqrt(T))
    if kind == "call":
        delta = eq * norm.cdf(d1)
        theta = common_theta - r * K * er * norm.cdf(d2) + q * S * eq * norm.cdf(d1)
        rho = K * T * er * norm.cdf(d2) / 100.0
    else:
        delta = -eq * norm.cdf(-d1)
        theta = common_theta + r * K * er * norm.cdf(-d2) - q * S * eq * norm.cdf(-d1)
        rho = -K * T * er * norm.cdf(-d2) / 100.0

    out = {"delta": delta, "gamma": gamma, "vega": vega, "theta": theta / 365.0, "rho": rho}
    return {k: (float(v) if np.ndim(v) == 0 else v) for k, v in out.items()}


def no_arbitrage_bounds(S: float, K: float, T: float, r: float, kind: str = "call",
                        q: float = 0.0) -> tuple[float, float]:
    """Lower and upper bounds any European option price must respect."""
    kind = _check_kind(kind)
    disc_s, disc_k = S * np.exp(-q * T), K * np.exp(-r * T)
    if kind == "call":
        return max(disc_s - disc_k, 0.0), disc_s
    return max(disc_k - disc_s, 0.0), disc_k


def implied_vol(market_price: float, S: float, K: float, T: float, r: float,
                kind: str = "call", q: float = 0.0,
                low: float = 1e-4, high: float = 5.0) -> float:
    """Volatility that makes the Black-Scholes price equal the market price.

    Uses Brent's method, which is guaranteed to converge because the BS price is
    strictly increasing in sigma. Returns NaN when the price violates the
    no-arbitrage bounds (no volatility can reproduce it).
    """
    lo_bound, hi_bound = no_arbitrage_bounds(S, K, T, r, kind, q)
    if not (lo_bound < market_price < hi_bound):
        return float("nan")

    def objective(sig: float) -> float:
        return price(S, K, T, r, sig, kind, q) - market_price

    if objective(low) > 0 or objective(high) < 0:
        return float("nan")
    return brentq(objective, low, high, xtol=1e-10, maxiter=200)


def implied_rates_from_parity(strikes: np.ndarray, call_mids: np.ndarray, put_mids: np.ndarray,
                              S: float, T: float) -> tuple[float, float, float]:
    """Back out the market's risk-free rate and dividend yield from put-call parity.

    Put-call parity for European options:  C - P = S*e^(-qT) - K*e^(-rT)
    Regressing (C - P) on K gives slope = -e^(-rT) and intercept = S*e^(-qT).

    Returns (r, q, forward_price).
    """
    y = np.asarray(call_mids) - np.asarray(put_mids)
    slope, intercept = np.polyfit(np.asarray(strikes, dtype=float), y, 1)
    r = -np.log(-slope) / T
    q = -np.log(intercept / S) / T
    forward = intercept / -slope
    return float(r), float(q), float(forward)
