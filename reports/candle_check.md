# Candle accuracy check

Run 21 Oct 2026 11:08 IST against Binance USD-M REST.

## 1. Missing 1m candles (last 30 days)

Expected 43,200 minutes, stored 43,200. Missing: 0 (in forex.com session hours: 0).

## 2. Stored 1m candles vs exchange (last 1500)

1500/1500 identical (OHLC + volume). Max difference 0.000000.

## 3. Our 5m / 15m / 1h vs Binance native klines (last 5 days, forex.com hours)

| TF | compared | identical | max diff |
|---|---|---|---|
| 5m | 827 | 827 | 0.000000 |
| 15m | 275 | 275 | 0.000000 |
| 1h | 68 | 68 | 0.000000 |

## 4. 4h and 1d candles (anchored to the 18:00 ET forex.com open)

| TF | compared | identical | max diff |
|---|---|---|---|
| 4h | 17 | 17 | 0.000000 |
| 1d | 2 | 2 | 0.000000 |

**Result: ALL CHECKS PASSED**