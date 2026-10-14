# Telegram alert backtest

Generated 12 Oct 2026 20:43 IST. Every 15-minute check and every 1h/4h/1d candle close since 5 Jan 2026 was replayed through the same alert code the bot runs (`gold/alerts.py`). Rules were picked on 5 Jan to 12 Apr. **The last 6 months (13 Apr to today) are the out-of-sample test.**

## 1. Conditions alerts (trade / selective / stop)

Thresholds: alert ON at score ≥38, OFF below 32, TRADE at ≥58 (drops back below 52). Each change must hold for 2 consecutive 15-min checks.

### selection (5 Jan-12 Apr)

**Time spent in each state, and what happened in the next 4 hours:**

| state | share | next4h_R_1to2 | next4h_R_1to1 | next4h_range | better_than_median |
|---|---|---|---|---|---|
| 🟢 TRADE | 47.881 | -0.052 | -0.056 | 78.020 | 52.609 |
| 🟡 SELECTIVE | 27.546 | -0.066 | -0.091 | 47.861 | 48.507 |
| 🔴 STOP | 24.573 | -0.113 | -0.141 | 33.805 | 46.589 |

**Each alert and the 4 hours after it:**

| kind | n | next4h_R_1to2 | next4h_R_1to1 | next4h_range | better_than_median | per_week |
|---|---|---|---|---|---|---|
| CONDITIONS_DOWN | 20.000 | -0.076 | -0.098 | 62.670 | 60.000 | 1.443 |
| CONDITIONS_GREEN | 20.000 | -0.055 | -0.009 | 54.580 | 55.000 | 1.443 |
| CONDITIONS_OFF | 17.000 | -0.281 | -0.260 | 33.242 | 41.176 | 1.227 |
| CONDITIONS_ON | 17.000 | -0.108 | -0.131 | 30.997 | 47.059 | 1.227 |

* Alerts per week (all condition types): **5.3**
* **ON / TRADE alerts followed by a better-than-median 4h: 51%** (coin flip 50%)
* **STOP alerts followed by a worse-than-median 4h: 59%** (coin flip 50%)
* Median length of a window: TRADE 12.6h · SELECTIVE 9.0h · STOP 17.0h

### LAST 6 MONTHS (13 Apr-now)

**Time spent in each state, and what happened in the next 4 hours:**

| state | share | next4h_R_1to2 | next4h_R_1to1 | next4h_range | better_than_median |
|---|---|---|---|---|---|
| 🟢 TRADE | 18.479 | -0.060 | -0.097 | 38.612 | 54.681 |
| 🟡 SELECTIVE | 31.124 | -0.118 | -0.139 | 36.317 | 51.289 |
| 🔴 STOP | 50.397 | -0.165 | -0.168 | 32.322 | 47.463 |

**Each alert and the 4 hours after it:**

| kind | n | next4h_R_1to2 | next4h_R_1to1 | next4h_range | better_than_median | per_week |
|---|---|---|---|---|---|---|
| CONDITIONS_DOWN | 33.000 | -0.033 | -0.090 | 32.234 | 51.515 | 1.269 |
| CONDITIONS_GREEN | 33.000 | -0.043 | -0.082 | 39.763 | 63.636 | 1.269 |
| CONDITIONS_OFF | 53.000 | -0.182 | -0.158 | 33.351 | 45.283 | 2.038 |
| CONDITIONS_ON | 53.000 | -0.249 | -0.223 | 34.028 | 43.396 | 2.038 |

* Alerts per week (all condition types): **6.6**
* **ON / TRADE alerts followed by a better-than-median 4h: 51%** (coin flip 50%)
* **STOP alerts followed by a worse-than-median 4h: 55%** (coin flip 50%)
* Median length of a window: TRADE 9.2h · SELECTIVE 8.2h · STOP 10.6h

## 2. Trend-shift alerts (market structure, closed candles)

A shift = a candle closes beyond the last confirmed swing high/low against the current trend (BOS/CHoCH). Judged on 1m candles: from the close of the shift candle, does price reach +1R / +2R in the new direction before −1R? (R = 1 ATR of that timeframe; horizon 12h for 1h, 1 day for 4h, 2 days for 1d; $0.40 cost included in R.)

### selection (5 Jan-12 Apr)

|  | n | per_week | hit +1R first % | hit +2R first % | random +1R % | random +2R % | avg R (1:2) | random R | median best move (R) | flip back fast % |
|---|---|---|---|---|---|---|---|---|---|---|
| ('1d', 'ALL') | 1.000 | 0.070 | 100.000 | 0.000 | 24.640 | 10.140 | 1.260 | 0.120 | 1.350 | 0.000 |
| ('1h', 'AGAINST') | 24.000 | 1.730 | 54.170 | 41.670 | 47.350 | 27.240 | 0.440 | -0.000 | 2.020 | 4.170 |
| ('1h', 'ALL') | 40.000 | 2.890 | 50.000 | 40.000 | 47.350 | 27.240 | 0.360 | -0.000 | 1.930 | 2.500 |
| ('1h', 'WITH') | 16.000 | 1.150 | 43.750 | 37.500 | 47.350 | 27.240 | 0.240 | -0.000 | 1.440 | 0.000 |
| ('4h', 'AGAINST') | 5.000 | 0.360 | 60.000 | 40.000 | 43.930 | 21.360 | 0.630 | 0.120 | 1.680 | 0.000 |
| ('4h', 'ALL') | 1.000 | 0.070 | 100.000 | 0.000 | 43.930 | 21.360 | 0.850 | 0.120 | 1.310 | 0.000 |
| ('4h', 'WITH') | 3.000 | 0.220 | 0.000 | 0.000 | 43.930 | 21.360 | -0.800 | 0.120 | 0.540 | 0.000 |

1h shifts split by direction vs 4h and by conditions at the time:

|  | n | hit1 | hit2 | avg_R |
|---|---|---|---|---|
| ('AGAINST', 'GREEN') | 10.000 | 70.000 | 40.000 | 0.680 |
| ('AGAINST', 'OFF') | 8.000 | 25.000 | 25.000 | -0.270 |
| ('AGAINST', 'ON') | 6.000 | 66.670 | 66.670 | 0.990 |
| ('WITH', 'GREEN') | 6.000 | 66.670 | 66.670 | 0.990 |
| ('WITH', 'OFF') | 6.000 | 16.670 | 16.670 | -0.420 |
| ('WITH', 'ON') | 4.000 | 50.000 | 25.000 | 0.090 |

### LAST 6 MONTHS (13 Apr-now)

|  | n | per_week | hit +1R first % | hit +2R first % | random +1R % | random +2R % | avg R (1:2) | random R | median best move (R) | flip back fast % |
|---|---|---|---|---|---|---|---|---|---|---|
| ('1d', 'ALL') | 2.000 | 0.080 | 50.000 | 0.000 | 20.770 | 3.080 | -0.020 | -0.040 | 0.670 | 0.000 |
| ('1h', 'AGAINST') | 59.000 | 2.270 | 47.460 | 27.120 | 47.660 | 28.160 | 0.050 | -0.040 | 1.600 | 5.080 |
| ('1h', 'ALL') | 102.000 | 3.920 | 53.920 | 29.410 | 47.660 | 28.160 | 0.110 | -0.040 | 1.620 | 8.820 |
| ('1h', 'WITH') | 43.000 | 1.650 | 62.790 | 32.560 | 47.660 | 28.160 | 0.190 | -0.040 | 1.700 | 13.950 |
| ('4h', 'AGAINST') | 11.000 | 0.420 | 45.450 | 27.270 | 45.640 | 20.900 | 0.040 | -0.010 | 1.140 | 0.000 |
| ('4h', 'ALL') | 20.000 | 0.770 | 40.000 | 20.000 | 45.640 | 20.900 | -0.150 | -0.010 | 1.040 | 0.000 |
| ('4h', 'WITH') | 9.000 | 0.350 | 33.330 | 11.110 | 45.640 | 20.900 | -0.390 | -0.010 | 0.940 | 0.000 |

1h shifts split by direction vs 4h and by conditions at the time:

|  | n | hit1 | hit2 | avg_R |
|---|---|---|---|---|
| ('AGAINST', 'GREEN') | 8.000 | 50.000 | 25.000 | 0.360 |
| ('AGAINST', 'OFF') | 27.000 | 51.850 | 33.330 | 0.050 |
| ('AGAINST', 'ON') | 24.000 | 41.670 | 20.830 | -0.060 |
| ('WITH', 'GREEN') | 3.000 | 66.670 | 33.330 | -0.020 |
| ('WITH', 'OFF') | 25.000 | 60.000 | 32.000 | 0.170 |
| ('WITH', 'ON') | 15.000 | 66.670 | 33.330 | 0.260 |

## 3. How many messages

Last 6 months: 6.6 conditions alerts + 4.8 trend-shift alerts per week (1h 3.9, 4h 0.8, 1d 0.1). About **8.1 loud notifications per week**. 'Selective ON' and downgrade messages arrive silently, because their moment wasn't better than a coin flip.

## 4. Exactly what the bot would have sent over the last 8 days

```
🔄 1H TREND SHIFT → BULLISH ▲
Against the 4h trend: counter-trend, so the 4h hasn't confirmed it.
closed above swing high 4153.74 · invalid on a close below 4130.75
1h ATR $17.19
Backtest (6m): +1R before −1R 47% · +2R before −1R 27% (random ≈ 48% / 28%) · n=59
Conditions now: 🟡 SELECTIVE (score 43)
Structure trend: 15m ▲ · 1h ▲ · 4h ▼ · 1d ▼
Price 4160.22
⏱ Mon 05 Oct 06:30 IST · 21:00 ET
```

```
🔄 1H TREND SHIFT → BEARISH ▼
With the 4h trend (4h is also bearish).
closed below swing low 4137.91 · invalid on a close above 4153.74
1h ATR $16.59
Backtest (6m): +1R before −1R 63% · +2R before −1R 33% (random ≈ 48% / 28%) · n=43
Conditions now: 🔴 NO TRADE (score 34)
Structure trend: 15m ▼ · 1h ▼ · 4h ▼ · 1d ▼
Price 4135.98
⏱ Mon 05 Oct 10:30 IST · 01:00 ET
```

```
🔄 1H TREND SHIFT → BULLISH ▲
Against the 4h trend: counter-trend, so the 4h hasn't confirmed it.
closed above swing high 4166.44 · invalid on a close below 4130.00
1h ATR $15.99
Backtest (6m): +1R before −1R 47% · +2R before −1R 27% (random ≈ 48% / 28%) · n=59
Conditions now: 🟢 TRADE (score 58)
Structure trend: 15m ▲ · 1h ▲ · 4h ▼ · 1d ▼
Price 4170.51
⏱ Mon 05 Oct 14:30 IST · 05:00 ET
```

```
🟢🟢 GOLD: TRADE CONDITIONS ON
Movement is back. Normal setups, 1:2+ targets OK.
Score 58/100 · SELECTIVE → TRADE
Backtest (6m): the next 4h was better than median 64% of the time (coin flip 50%), n=33
Structure trend: 15m ▲ · 1h ▲ · 4h ▼ · 1d ▼
Price 4162.38
⏱ Mon 05 Oct 15:30 IST · 06:00 ET
```

```
🟡 GOLD: DOWNGRADED TO SELECTIVE
Movement fading. Tighten up, take profits quicker.
Score 49/100 · TRADE → SELECTIVE
Backtest (6m): the next 4h was better than median 52% of the time (coin flip 50%), n=33
Structure trend: 15m ▲ · 1h ▲ · 4h ▼ · 1d ▼
Price 4164.93
⏱ Mon 05 Oct 16:45 IST · 07:15 ET
```

```
🔴 GOLD: STOP TRADING (NO-TRADE CONDITIONS)
Gold isn't moving enough to pay for stops and spread. Step away.
Score 24/100 · SELECTIVE → NO TRADE
Backtest (6m): the next 4h was worse than median 55% of the time (coin flip 50%), n=53
Structure trend: 15m ▼ · 1h ▲ · 4h ▼ · 1d ▼
Price 4146.35
⏱ Tue 06 Oct 03:45 IST · 18:15 ET
```

```
🔄 1H TREND SHIFT → BEARISH ▼
With the 4h trend (4h is also bearish).
closed below swing low 4128.02 · invalid on a close above 4155.15
1h ATR $14.26
Backtest (6m): +1R before −1R 63% · +2R before −1R 33% (random ≈ 48% / 28%) · n=43
Conditions now: 🟡 SELECTIVE (score 36)
Structure trend: 15m ▼ · 1h ▼ · 4h ▼ · 1d ▼
Price 4125.67
⏱ Tue 06 Oct 10:30 IST · 01:00 ET
```

```
🟡 GOLD: TRADABLE (SELECTIVE)
Conditions improved. A+ setups only, half size.
Score 39/100 · NO TRADE → SELECTIVE
Backtest (6m): the next 4h was better than median 43% of the time (coin flip 50%), n=53
Structure trend: 15m ▼ · 1h ▼ · 4h ▼ · 1d ▼
Price 4126.01
⏱ Tue 06 Oct 11:15 IST · 01:45 ET
```

```
🔄 1H TREND SHIFT → BULLISH ▲
Against the 4h trend: counter-trend, so the 4h hasn't confirmed it.
closed above swing high 4155.15 · invalid on a close below 4108.80
1h ATR $14.51
Backtest (6m): +1R before −1R 47% · +2R before −1R 27% (random ≈ 48% / 28%) · n=59
Conditions now: 🔴 NO TRADE (score 35)
Structure trend: 15m ▲ · 1h ▲ · 4h ▼ · 1d ▼
Price 4158.84
⏱ Tue 06 Oct 14:30 IST · 05:00 ET
```

```
🔴 GOLD: STOP TRADING (NO-TRADE CONDITIONS)
Gold isn't moving enough to pay for stops and spread. Step away.
Score 29/100 · SELECTIVE → NO TRADE
Backtest (6m): the next 4h was worse than median 55% of the time (coin flip 50%), n=53
Structure trend: 15m ▲ · 1h ▲ · 4h ▼ · 1d ▼
Price 4163.98
⏱ Tue 06 Oct 16:45 IST · 07:15 ET
```

```
🔄 1H TREND SHIFT → BEARISH ▼
With the 4h trend (4h is also bearish).
closed below swing low 4147.81 · invalid on a close above 4187.40
1h ATR $12.24
Backtest (6m): +1R before −1R 63% · +2R before −1R 33% (random ≈ 48% / 28%) · n=43
Conditions now: 🔴 NO TRADE (score 15)
Structure trend: 15m ▼ · 1h ▼ · 4h ▼ · 1d ▼
Price 4146.20
⏱ Wed 07 Oct 08:30 IST · 23:00 ET
```

```
🔄 1H TREND SHIFT → BULLISH ▲
Against the 4h trend: counter-trend, so the 4h hasn't confirmed it.
closed above swing high 4131.45 · invalid on a close below 4106.39
1h ATR $13.97
Backtest (6m): +1R before −1R 47% · +2R before −1R 27% (random ≈ 48% / 28%) · n=59
Conditions now: 🔴 NO TRADE (score 29)
Structure trend: 15m ▲ · 1h ▲ · 4h ▼ · 1d ▼
Price 4136.91
⏱ Thu 08 Oct 07:30 IST · 22:00 ET
```

```
🟡 GOLD: TRADABLE (SELECTIVE)
Conditions improved. A+ setups only, half size.
Score 40/100 · NO TRADE → SELECTIVE
Backtest (6m): the next 4h was better than median 43% of the time (coin flip 50%), n=53
Structure trend: 15m ▼ · 1h ▲ · 4h ▼ · 1d ▼
Price 4136.58
⏱ Fri 09 Oct 01:15 IST · 15:45 ET
```

```
🔴 GOLD: STOP TRADING (NO-TRADE CONDITIONS)
Gold isn't moving enough to pay for stops and spread. Step away.
Score 30/100 · SELECTIVE → NO TRADE
Backtest (6m): the next 4h was worse than median 55% of the time (coin flip 50%), n=53
Structure trend: 15m ▲ · 1h ▲ · 4h ▼ · 1d ▼
Price 4146.47
⏱ Fri 09 Oct 05:00 IST · 19:30 ET
```

```
🔄 4H BIAS CHANGE → BULLISH ▲
Against the 1d trend: counter-trend, so the 1d hasn't confirmed it.
Higher-timeframe bias info, not an entry signal.
closed above swing high 4187.40 · invalid on a close below 4110.68
4h ATR $30.33
Backtest (6m): +1R before −1R 40% · +2R before −1R 20% (random ≈ 46% / 21%) · n=20
Conditions now: 🔴 NO TRADE (score 27)
Structure trend: 15m ▲ · 1h ▲ · 4h ▲ · 1d ▼
Price 4198.01
⏱ Fri 09 Oct 11:30 IST · 02:00 ET
```

```
🟡 GOLD: TRADABLE (SELECTIVE)
Conditions improved. A+ setups only, half size.
Score 39/100 · NO TRADE → SELECTIVE
Backtest (6m): the next 4h was better than median 43% of the time (coin flip 50%), n=53
Structure trend: 15m ▲ · 1h ▲ · 4h ▲ · 1d ▼
Price 4198.84
⏱ Fri 09 Oct 13:30 IST · 04:00 ET
```

```
🔴 GOLD: STOP TRADING (NO-TRADE CONDITIONS)
Gold isn't moving enough to pay for stops and spread. Step away.
Score 30/100 · SELECTIVE → NO TRADE
Backtest (6m): the next 4h was worse than median 55% of the time (coin flip 50%), n=53
Structure trend: 15m ▼ · 1h ▲ · 4h ▲ · 1d ▼
Price 4189.81
⏱ Fri 09 Oct 17:00 IST · 07:30 ET
```

```
🔄 1H TREND SHIFT → BEARISH ▼
Against the 4h trend: counter-trend, so the 4h hasn't confirmed it.
closed below swing low 4189.98 · invalid on a close above 4222.58
1h ATR $12.17
Backtest (6m): +1R before −1R 47% · +2R before −1R 27% (random ≈ 48% / 28%) · n=59
Conditions now: 🔴 NO TRADE (score 19)
Structure trend: 15m ▼ · 1h ▼ · 4h ▲ · 1d ▼
Price 4185.97
⏱ Mon 12 Oct 13:30 IST · 04:00 ET
```
