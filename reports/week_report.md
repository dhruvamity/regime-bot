# Gold (XAUUSDT) week of 05 Oct 2026 - deep comparison

Generated 12 Oct 2026 20:42 IST. Data: Binance XAUUSDT 1m, forex.com session hours only (Sun 18:00 ET -> Fri 17:00 ET). Baseline = 26 weeks from 06 Apr 2026.

## 1. Every timeframe: last week vs previous 3 weeks vs 6 months

pct_vs_6m = percentile of last week among the previous 6 months of weeks (0 = lowest, 100 = highest).

| tf | metric | last_week | prev_3_weeks | median_6m | pct_vs_6m |
|---|---|---|---|---|---|
| 1m | Efficiency (higher = cleaner trend) | 0.349 | 0.332 | 0.320 | 96.154 |
| 1m | Choppiness Index (higher = choppier) | 41.554 | 44.165 | 44.786 | 0.000 |
| 1m | Wick share of candles (higher = more rejection) | 0.407 | 0.432 | 0.440 | 3.846 |
| 1m | Follow-through / variance ratio (>1 trends, <1 snaps back) | 1.034 | 1.037 | 0.982 | 69.231 |
| 1m | ATR $ (movement per candle) | 1.280 | 1.688 | 1.838 | 0.000 |
| 1m | Trend-follow 1:2 net R per entry (with 1h bias) | -0.276 | -0.244 | -0.223 | 19.231 |
| 1m | Trend-follow 1:1 net R per entry (with 1h bias) | -0.375 | -0.294 | -0.273 | 3.846 |
| 5m | Efficiency (higher = cleaner trend) | 0.324 | 0.326 | 0.314 | 65.385 |
| 5m | Choppiness Index (higher = choppier) | 46.109 | 47.533 | 48.110 | 3.846 |
| 5m | Wick share of candles (higher = more rejection) | 0.494 | 0.491 | 0.503 | 19.231 |
| 5m | Follow-through / variance ratio (>1 trends, <1 snaps back) | 1.020 | 0.919 | 0.954 | 73.077 |
| 5m | ATR $ (movement per candle) | 3.372 | 4.302 | 4.648 | 0.000 |
| 5m | Trend-follow 1:2 net R per entry (with 1h bias) | -0.090 | -0.091 | -0.104 | 57.692 |
| 5m | Trend-follow 1:1 net R per entry (with 1h bias) | -0.129 | -0.106 | -0.107 | 26.923 |
| 15m | Efficiency (higher = cleaner trend) | 0.313 | 0.329 | 0.319 | 30.769 |
| 15m | Choppiness Index (higher = choppier) | 46.781 | 47.742 | 48.558 | 3.846 |
| 15m | Wick share of candles (higher = more rejection) | 0.502 | 0.514 | 0.523 | 3.846 |
| 15m | Follow-through / variance ratio (>1 trends, <1 snaps back) | 0.831 | 0.968 | 0.917 | 7.692 |
| 15m | ATR $ (movement per candle) | 6.334 | 7.838 | 8.467 | 0.000 |
| 15m | Trend-follow 1:2 net R per entry (with 1h bias) | -0.148 | -0.081 | -0.068 | 26.923 |
| 15m | Trend-follow 1:1 net R per entry (with 1h bias) | -0.092 | -0.105 | -0.073 | 42.308 |
| 1h | Efficiency (higher = cleaner trend) | 0.308 | 0.302 | 0.333 | 23.077 |
| 1h | Choppiness Index (higher = choppier) | 47.456 | 48.953 | 47.865 | 42.308 |
| 1h | Wick share of candles (higher = more rejection) | 0.522 | 0.519 | 0.537 | 19.231 |
| 1h | Follow-through / variance ratio (>1 trends, <1 snaps back) | 0.833 | 0.784 | 0.952 | 30.769 |
| 1h | ATR $ (movement per candle) | 14.062 | 16.661 | 18.174 | 0.000 |

## 2. Movement and structure, week by week

overlap = share of each day's range inside the previous day's range (high = going nowhere). path_eff_1h = |net move| / total 1h path. y2/y1_ltf = average net R of 1:2 / 1:1 trend-following entries on 1m+5m+15m in the 1h-bias direction (after a $0.40 cost per trade).

|  | days | week_range | net_move | avg_day_range | overlap | path_eff_1h | atr_5m | er_15m | chop_15m | wick_5m | vr_15m | y2_ltf | y1_ltf |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-09-14 | 5.000 | 161.940 | 35.510 | 95.836 | 0.740 | 0.152 | 4.623 | 0.336 | 46.877 | 0.497 | 0.979 | -0.120 | -0.128 |
| 2026-09-21 | 5.000 | 139.140 | -85.830 | 71.078 | 0.700 | 0.182 | 4.132 | 0.304 | 49.495 | 0.488 | 0.794 | -0.105 | -0.193 |
| 2026-09-28 | 5.000 | 167.890 | -136.180 | 92.342 | 0.599 | 0.281 | 4.152 | 0.347 | 46.854 | 0.486 | 0.993 | -0.190 | -0.184 |
| 2026-10-05 | 5.000 | 139.380 | 57.920 | 68.734 | 0.673 | 0.223 | 3.372 | 0.313 | 46.781 | 0.494 | 0.812 | -0.171 | -0.199 |
| 6m median | 5.000 | 225.530 | -50.635 | 101.307 | 0.640 | 0.224 | 4.641 | 0.318 | 48.558 | 0.503 | 0.916 | -0.125 | -0.161 |

## 3. Day by day (last 4 weeks)

| sdate | range | overlap | body | path_eff_1h | atr_1m | atr_5m | er_5m | chop_5m | wick_5m | vr_5m | y2_1m | y2_5m | y2_15m | y1_5m |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Mon 14 Sep | 100.380 | 0.647 | 0.433 | 0.178 | 1.929 | 4.931 | 0.314 | 48.318 | 0.457 | 0.820 | -0.138 | 0.370 | 0.527 | 0.158 |
| Tue 15 Sep | 54.540 | 1.000 | 0.059 | 0.017 | 1.516 | 3.857 | 0.348 | 49.655 | 0.547 | 0.905 | -0.313 | -0.121 | -0.039 | -0.167 |
| Wed 16 Sep | 136.190 | 0.400 | 0.206 | 0.100 | 2.096 | 5.088 | 0.314 | 46.356 | 0.493 | 0.836 | -0.167 | -0.049 | -0.234 | -0.091 |
| Thu 17 Sep | 123.320 | 0.943 | 0.602 | 0.293 | 1.853 | 5.027 | 0.353 | 45.323 | 0.518 | 1.112 | -0.300 | -0.395 | -0.680 | -0.174 |
| Fri 18 Sep | 64.750 | 0.711 | 0.498 | 0.174 | 1.635 | 4.210 | 0.305 | 47.801 | 0.472 | 0.954 | -0.178 | -0.077 | -0.010 | -0.099 |
| Mon 21 Sep | 61.140 | 0.773 | 0.468 | 0.186 | 1.588 | 4.065 | 0.293 | 48.585 | 0.492 | 0.770 | -0.250 | -0.375 | -0.427 | -0.216 |
| Tue 22 Sep | 83.970 | 0.624 | 0.196 | 0.081 | 1.887 | 4.736 | 0.368 | 45.108 | 0.503 | 1.048 | -0.215 | -0.124 | -0.119 | -0.256 |
| Wed 23 Sep | 93.220 | 0.826 | 0.758 | 0.458 | 1.363 | 3.581 | 0.301 | 48.907 | 0.464 | 0.675 | -0.242 | 0.248 | 0.658 | 0.019 |
| Thu 24 Sep | 57.760 | 0.477 | 0.225 | 0.071 | 1.748 | 4.348 | 0.321 | 48.820 | 0.510 | 0.945 | -0.194 | 0.015 | -0.059 | -0.051 |
| Fri 25 Sep | 59.300 | 0.801 | 0.350 | 0.116 | 1.478 | 3.927 | 0.339 | 46.645 | 0.471 | 0.954 | -0.227 | -0.233 | -0.033 | -0.169 |
| Mon 28 Sep | 167.890 | 0.150 | 0.968 | 0.642 | 1.936 | 4.757 | 0.367 | 46.528 | 0.497 | 0.899 | 0.176 | 0.651 | 0.841 | 0.261 |
| Tue 29 Sep | 70.290 | 1.000 | 0.892 | 0.380 | 1.542 | 3.901 | 0.270 | 51.648 | 0.492 | 0.620 | -0.368 | -0.335 | -0.703 | -0.138 |
| Wed 30 Sep | 73.450 | 0.482 | 0.291 | 0.139 | 1.482 | 3.802 | 0.328 | 49.255 | 0.495 | 0.899 | -0.391 | -0.200 | -0.345 | -0.155 |
| Thu 01 Oct | 52.130 | 0.831 | 0.327 | 0.101 | 1.463 | 3.804 | 0.327 | 44.549 | 0.454 | 0.994 | -0.351 | -0.129 | -0.229 | -0.111 |
| Fri 02 Oct | 97.950 | 0.532 | 0.343 | 0.141 | 1.810 | 4.497 | 0.342 | 45.503 | 0.494 | 1.008 | -0.499 | -0.606 | -0.366 | -0.407 |
| Mon 05 Oct | 45.780 | 0.940 | 0.051 | 0.014 | 1.308 | 3.384 | 0.318 | 46.198 | 0.508 | 1.021 | -0.216 | -0.168 | -0.118 | -0.136 |
| Tue 06 Oct | 78.600 | 0.582 | 0.306 | 0.135 | 1.207 | 3.305 | 0.375 | 44.058 | 0.493 | 1.016 | -0.343 | 0.142 | -0.211 | -0.085 |
| Wed 07 Oct | 99.860 | 0.642 | 0.516 | 0.366 | 1.290 | 3.347 | 0.329 | 45.618 | 0.495 | 1.210 | -0.304 | -0.220 | -0.406 | -0.156 |
| Thu 08 Oct | 44.050 | 1.000 | 0.444 | 0.136 | 1.408 | 3.667 | 0.314 | 45.205 | 0.471 | 0.826 | -0.283 | -0.338 | -0.165 | -0.193 |
| Fri 09 Oct | 75.380 | 0.201 | 0.818 | 0.463 | 1.186 | 3.158 | 0.283 | 49.467 | 0.502 | 0.908 | -0.235 | 0.135 | 0.160 | -0.073 |

## 4. How often does a week like this happen?

* Last week's average daily range was **$68.7**: rank **1 of 27** weeks in the last 6 months (1 = quietest). 6-month median: $101.3.
* Definition of 'like last week': average daily range in the bottom 20% of the trailing 6 months **and** below-median LTF trend-following results.
* Weeks matching in the prior 6 months: **4 of 26** (2026-05-18, 2026-07-06, 2026-07-20, 2026-07-27).
* All matching weeks in the full 10-month history: 2026-05-18, 2026-07-06, 2026-07-20, 2026-07-27, 2026-10-05.
* Individual days in the prior 6 months with a range at or below last week's average ($69): **24 of 130** (18%).

## 5. Today (2026-10-12) vs last week, same 17.2h into each session

|  | today | last_week_avg | last_6m_median | today_pct_vs_6m |
|---|---|---|---|---|
| range | 62.190 | 66.466 | 84.655 | 23.077 |
| net | -28.550 | 3.416 | -1.515 | 33.077 |
| atr_1m | 1.304 | 1.329 | 1.904 | 5.385 |
| atr_5m | 3.220 | 3.345 | 4.516 | 3.846 |
| er_1m | 0.315 | 0.350 | 0.322 | 36.923 |
| er_5m | 0.344 | 0.331 | 0.319 | 75.385 |
| er_15m | 0.326 | 0.323 | 0.314 | 55.385 |
| chop_5m | 47.001 | 46.049 | 48.066 | 34.615 |
| wick_5m | 0.528 | 0.494 | 0.504 | 82.308 |
| vr_5m | 0.829 | 0.995 | 0.922 | 28.462 |
| y2_1m | -0.438 | -0.256 | -0.243 | 9.231 |
| y2_5m | -0.546 | -0.044 | -0.132 | 5.385 |
| y1_1m | -0.432 | -0.361 | -0.277 | 6.923 |
| y1_5m | -0.324 | -0.126 | -0.117 | 9.231 |

Last week's sessions at the same point:

|  | range | net | atr_1m | atr_5m | er_1m | er_5m | er_15m | chop_5m | wick_5m | vr_5m | y2_1m | y2_5m | y1_1m | y1_5m |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Mon 05 Oct | 43.800 | 2.280 | 1.411 | 3.458 | 0.352 | 0.337 | 0.291 | 45.409 | 0.513 | 1.043 | -0.195 | -0.250 | -0.285 | -0.187 |
| Tue 06 Oct | 74.450 | 21.040 | 1.291 | 3.371 | 0.354 | 0.366 | 0.340 | 45.060 | 0.491 | 0.986 | -0.283 | 0.170 | -0.375 | -0.065 |
| Wed 07 Oct | 99.860 | -62.370 | 1.269 | 3.140 | 0.344 | 0.348 | 0.349 | 44.853 | 0.493 | 1.218 | -0.348 | 0.004 | -0.462 | -0.122 |
| Thu 08 Oct | 38.840 | 3.270 | 1.403 | 3.549 | 0.369 | 0.293 | 0.243 | 47.048 | 0.467 | 0.766 | -0.288 | -0.291 | -0.351 | -0.228 |
| Fri 09 Oct | 75.380 | 52.860 | 1.273 | 3.208 | 0.331 | 0.310 | 0.392 | 47.873 | 0.504 | 0.962 | -0.165 | 0.146 | -0.333 | -0.031 |
