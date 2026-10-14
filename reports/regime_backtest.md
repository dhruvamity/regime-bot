# Quiet-mode backtest

Sessions 2026-03-09 to 2026-10-13 (156), Binance XAUUSDT perp, forex.com hours. Mode = average daily range of the last 3 sessions vs the 60-session median: QUIET below 0.75, back to NORMAL at 0.80. Each session is judged by the mode known before it opened; outcomes are for the 17:00-24:00 IST evening.

| mode at session start | sessions | next evening quiet % | evening move vs normal | reach $9 in 60 min % | reach $16.5 in 60 min % | random 1:2 R | random 1:3 R | random 1:5.5 R |
|---|---|---|---|---|---|---|---|---|
| NORMAL | 131.00 | 22.14 | 1.03 | 81.46 | 44.66 | 0.02 | 0.04 | 0.03 |
| QUIET | 25.00 | 48.00 | 0.81 | 72.63 | 38.31 | 0.02 | 0.05 | 0.12 |

Mode flips (alerts) over the period: 21 with the 0.75/0.80 buffer, 23 with a single 0.75 line.

Reach columns: how often a far target gets hit at all. R columns: random entries (no edge by design, no costs), which show whether a far target also cost expectancy in that mode. In quiet mode the stop gets hit less often too, so fewer far targets does not automatically mean lower R.

Now: **QUIET** (ratio 0.74, last 3 ranges [75.4, 62.2, 52.4], normal $86).

_Computed in 73s._
