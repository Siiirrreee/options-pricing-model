# Data

`spx_chain_2026-11-24.csv`: S&P 500 index (SPX) options expiring **2026-12-18**, 15-minute delayed quotes captured after the close on **2026-11-24** from Yahoo Finance (Cboe data). Strikes 6,000 to 8,400 in steps of 50, calls and puts.

| Column | Meaning |
|---|---|
| quote_date / expiration | Snapshot date and expiration date |
| type | `call` or `put` |
| root | `SPX` (monthly, AM-settled) or `SPXW` (PM-settled), the standard SPX contract is used when both exist |
| strike | Strike price |
| bid / ask / last | Quotes and last trade price |
| volume / open_interest | Contracts traded that day / open contracts |

SPX index close that day: **7,201.09**. Run `python main.py --live SPY` to pull a fresh chain instead.
