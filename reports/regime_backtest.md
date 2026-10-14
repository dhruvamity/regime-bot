# Quiet-mode backtest

Sessions 2026-03-09 to 2026-10-13 (156), Binance XAUUSDT perp, forex.com hours. Mode = average daily range of the last 2 sessions vs the 60-session median: QUIET below 0.80, back to NORMAL at 0.90. Each session is judged by the mode known before it opened; outcomes are for the 17:00-24:00 IST evening.

| mode at session start | sessions | next evening quiet % | evening move vs normal | reach $9 in 60 min % | reach $16.5 in 60 min % | random 1:2 R | random 1:3 R | random 1:5.5 R |
|---|---|---|---|---|---|---|---|---|
| NORMAL | 113.00 | 21.24 | 1.05 | 81.90 | 45.15 | 0.02 | 0.04 | 0.02 |
| QUIET | 43.00 | 39.53 | 0.86 | 75.17 | 39.69 | 0.03 | 0.06 | 0.09 |

Mode flips (alerts) over the period: 33 with the 0.80/0.90 buffer, 37 with a single 0.80 line.

Reach columns: how often a far target gets hit at all. R columns: random entries (no edge by design, no costs), which show whether a far target also cost expectancy in that mode. In quiet mode the stop gets hit less often too, so fewer far targets does not automatically mean lower R.

Now: **QUIET** (ratio 0.67, last 2 ranges [62.2, 52.4], normal $86).

_Computed in 67s._
