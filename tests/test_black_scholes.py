import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from options_pricing import black_scholes as bs  # noqa: E402
from options_pricing import market  # noqa: E402

# Textbook example (Hull, Options, Futures and Other Derivatives): S=42, K=40, r=10%, sigma=20%, T=0.5
HULL = dict(S=42.0, K=40.0, T=0.5, r=0.10, sigma=0.20)


def test_textbook_prices():
    assert bs.price(**HULL, kind="call") == pytest.approx(4.76, abs=0.005)
    assert bs.price(**HULL, kind="put") == pytest.approx(0.81, abs=0.005)


@pytest.mark.parametrize("q", [0.0, 0.02])
def test_put_call_parity(q):
    S, K, T, r, sig = 100.0, 95.0, 0.75, 0.04, 0.3
    c, p = bs.price(S, K, T, r, sig, "call", q), bs.price(S, K, T, r, sig, "put", q)
    assert c - p == pytest.approx(S * np.exp(-q * T) - K * np.exp(-r * T), abs=1e-10)


@pytest.mark.parametrize("kind", ["call", "put"])
def test_greeks_match_finite_differences(kind):
    S, K, T, r, sig, q = 100.0, 105.0, 0.4, 0.03, 0.25, 0.01
    g = bs.greeks(S, K, T, r, sig, kind, q)
    f = lambda **kw: bs.price(**{**dict(S=S, K=K, T=T, r=r, sigma=sig, kind=kind, q=q), **kw})  # noqa: E731
    h = 1e-4
    assert g["delta"] == pytest.approx((f(S=S + h) - f(S=S - h)) / (2 * h), rel=1e-5)
    assert g["gamma"] == pytest.approx((f(S=S + 0.01) - 2 * f() + f(S=S - 0.01)) / 0.01**2, rel=1e-3)
    assert g["vega"] == pytest.approx((f(sigma=sig + h) - f(sigma=sig - h)) / (2 * h) / 100, rel=1e-5)
    assert g["rho"] == pytest.approx((f(r=r + h) - f(r=r - h)) / (2 * h) / 100, rel=1e-5)
    assert g["theta"] == pytest.approx(-(f(T=T + h) - f(T=T - h)) / (2 * h) / 365, rel=1e-5)


@pytest.mark.parametrize("kind", ["call", "put"])
@pytest.mark.parametrize("sig", [0.05, 0.2, 0.8])
@pytest.mark.parametrize("K", [80.0, 100.0, 125.0])
def test_implied_vol_round_trip(kind, sig, K):
    S, T, r = 100.0, 0.5, 0.04
    if bs.greeks(S, K, T, r, sig, kind)["vega"] < 1e-4:
        pytest.skip("deep in-the-money at low vol: price equals intrinsic, IV is not identifiable")
    assert bs.implied_vol(bs.price(S, K, T, r, sig, kind), S, K, T, r, kind) == pytest.approx(sig, abs=1e-6)


def test_implied_vol_rejects_arbitrage_price():
    # A call can never be worth more than the underlying
    assert np.isnan(bs.implied_vol(150.0, 100.0, 100.0, 0.5, 0.04, "call"))


def test_parity_recovers_rates():
    S, T, r, q = 100.0, 0.25, 0.045, 0.015
    K = np.linspace(90, 110, 9)
    c, p = bs.price(S, K, T, r, 0.2, "call", q), bs.price(S, K, T, r, 0.2, "put", q)
    r_hat, q_hat, fwd = bs.implied_rates_from_parity(K, c, p, S, T)
    assert r_hat == pytest.approx(r, abs=1e-8)
    assert q_hat == pytest.approx(q, abs=1e-8)
    assert fwd == pytest.approx(S * np.exp((r - q) * T), rel=1e-10)


def test_snapshot_pipeline():
    chain = market.clean_chain(market.load_chain(ROOT / "data" / market.SNAPSHOT_FILE))
    T = market.year_fraction("2026-11-24", "2026-12-18")
    fwd = market.parity_forward(chain, market.SNAPSHOT_SPOT, T, 0.042)
    s_eff = fwd * np.exp(-0.042 * T)
    smile = market.otm_smile(market.add_implied_vols(chain, s_eff, T, 0.042, 0.0), fwd)
    assert 0.10 < market.atm_vol(smile, fwd) < 0.50
    # equity-index skew: low-strike puts carry higher implied vol than high-strike calls
    assert smile["iv"].iloc[0] > smile["iv"].iloc[-1]
