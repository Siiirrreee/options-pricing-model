# Results summary

_SPX options expiring 2026-12-18 (quotes at 2026-11-24 close). 88 two-sided quotes after cleaning; full detail in [results/summary.md](results/summary.md)._

**Flat-volatility Black-Scholes vs. market, by moneyness**

| Bucket                       |   Options | Avg market IV   |   Avg error ($) | Avg error (%)   | Inside bid/ask   |
|:-----------------------------|----------:|:----------------|----------------:|:----------------|:-----------------|
| Deep OTM puts (K < 90% of F) |         9 | 39.4%           |          -22.24 | -92.6%          | 0%               |
| OTM puts (90–97%)            |        10 | 31.6%           |          -30.25 | -52.9%          | 0%               |
| Near the money (97–103%)     |         9 | 24.1%           |            0.01 | 1.6%            | 11%              |
| OTM calls (K > 103%)         |        11 | 18.0%           |           20.58 | 270.3%          | 0%               |

**At-the-money contracts: price and Greeks at market implied vol**

| Contract   |   Market mid | Implied vol   |   BS price @ IV |   Delta |   Gamma |   Vega |   Theta/day |   Rho |
|:-----------|-------------:|:--------------|----------------:|--------:|--------:|-------:|------------:|------:|
| Call 7,200 |       150.35 | 23.4%         |          150.35 |   0.471 | 0.00093 |   7.28 |       -3.92 |  2.11 |
| Put 7,150  |       173.8  | 24.2%         |          173.8  |  -0.482 | 0.0009  |   7.29 |       -3.26 | -2.38 |

**Key findings**

- Put-call parity puts the forward at **7,155.7** (24 days, r = 4.2%). A parity regression with no rate assumption implies r ≈ 4.7%, close to the 4.2% 3-month T-bill rate, a useful cross-check on the inputs.
- At-the-money implied volatility is **24.1%**. The market does not use one number: the 6,000 put trades at **43.0%** IV and the 7,950 call at **18.0%**, a classic equity-index skew.
- With a single flat vol, Black-Scholes underprices deep out-of-the-money puts by **93%** on average (worst: 98% at the 6,000 strike). Investors pay up for crash protection that a lognormal model says is rare.
- The same flat vol **overprices** out-of-the-money calls by 270% on average: the market expects upside moves to be calmer than downside moves, which one volatility cannot capture.
- Errors are smallest near the money (average absolute error 11%) and grow fast in both tails: Black-Scholes works where it is calibrated and breaks down away from it.

## Inputs

| Input | Value |
|---|---|
| Index close (4:00 pm) | 7,201.09 |
| Parity forward | 7,155.72 |
| Spot implied by forward | 7,135.98 |
| Risk-free rate | 4.2% |
| Parity-implied rate | 4.72% |
| Days to expiry | 24 |
| ATM implied vol | 24.12% |

The spot implied by parity sits below the 4:00 pm index print. The delayed option quotes and the index close were not captured at the same instant, so the model prices off the parity forward, which reflects where the options were actually trading.
