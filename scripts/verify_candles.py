"""Check that every timeframe the bot reads matches the exchange.

1. No missing 1m candles in the store (last 30 days).
2. Stored 1m candles == Binance REST 1m (last 1500 candles).
3. Our 5m / 15m / 1h (built from 1m, forex.com hours only) == Binance native 5m / 15m / 1h klines.
4. Our 4h / 1d candles are anchored to the 18:00 ET open like forex.com (Binance's own 4h/1d
   are UTC-anchored, so they're not comparable 1:1); they're checked against Binance's
   native 1h klines aggregated over exactly the same windows.
Writes reports/candle_check.md.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import requests  # noqa: E402

from gold import session, store  # noqa: E402
from gold.config import IST, REPORTS_DIR, REST_BASE, SYMBOL  # noqa: E402


def native(interval: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    rows, cur = [], start_ms
    while cur < end_ms:
        r = requests.get(f"{REST_BASE}/fapi/v1/klines", params={"symbol": SYMBOL, "interval": interval,
                                                                 "startTime": cur, "endTime": end_ms, "limit": 1500}, timeout=20)
        r.raise_for_status()
        k = r.json()
        if not k:
            break
        rows += k
        cur = k[-1][0] + 1
        if len(k) < 1500:
            break
    now = time.time() * 1000
    df = pd.DataFrame([(x[0], float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])) for x in rows if x[6] < now],
                      columns=["ts", "o", "h", "l", "c", "v"])
    df.index = pd.to_datetime(df.pop("ts"), unit="ms", utc=True)
    df.index.name = "time"
    return df[~df.index.duplicated()]


def compare(ours: pd.DataFrame, theirs: pd.DataFrame, cols=("o", "h", "l", "c")) -> dict:
    idx = ours.index.intersection(theirs.index)
    a, b = ours.loc[idx, list(cols)], theirs.loc[idx, list(cols)]
    diff = (a - b).abs().max(axis=1)
    return {"compared": len(idx), "exact": int((diff < 1e-6).sum()), "max_diff": float(diff.max()) if len(idx) else 0.0,
            "mismatch_times": [str(t) for t in diff[diff >= 1e-6].index[:5]]}


def main():
    con = store.connect()
    now = pd.Timestamp.now(tz="UTC").floor("min")
    md = ["# Candle accuracy check", "", f"Run {pd.Timestamp.now(tz=IST):%d %b %Y %H:%M} IST against Binance USD-M REST.", ""]
    ok_all = True

    # 1. gaps
    raw = store.load(con, start_ms=int((now - pd.Timedelta(days=30)).timestamp() * 1000))
    full = pd.date_range(raw.index[0], raw.index[-1], freq="1min")
    missing = full.difference(raw.index)
    miss_in = missing[session.in_session(missing)] if len(missing) else missing
    md += ["## 1. Missing 1m candles (last 30 days)", "",
           f"Expected {len(full):,} minutes, stored {len(raw):,}. Missing: {len(missing)} (in forex.com session hours: {len(miss_in)}).", ""]
    ok_all &= len(miss_in) == 0
    print(f"1) missing 1m candles: {len(missing)} (in-session {len(miss_in)})")

    # 2. 1m vs REST
    end = int(now.timestamp() * 1000)
    start = end - 1500 * 60_000
    n1 = native("1m", start, end)
    ours1 = store.load(con, start_ms=start, end_ms=end)
    r1 = compare(ours1, n1, ("o", "h", "l", "c", "v"))
    md += ["## 2. Stored 1m candles vs exchange (last 1500)", "", f"{r1['exact']}/{r1['compared']} identical (OHLC + volume). "
           f"Max difference {r1['max_diff']:.6f}.", ""]
    ok_all &= r1["exact"] == r1["compared"]
    print(f"2) 1m: {r1}")

    # 3. 5m / 15m / 1h vs native (in-session buckets that are fully inside the session)
    start3 = int((now - pd.Timedelta(days=5)).timestamp() * 1000)
    s1m = session.session_filter(store.load(con, start_ms=start3 - 86_400_000, end_ms=end))
    md += ["## 3. Our 5m / 15m / 1h vs Binance native klines (last 5 days, forex.com hours)", "",
           "| TF | compared | identical | max diff |", "|---|---|---|---|"]
    for tf, mins in (("5m", 5), ("15m", 15), ("1h", 60)):
        ours = session.resample(s1m, tf)
        cnt = s1m.groupby(s1m.index.floor(f"{mins}min")).size()
        ours = ours[cnt.reindex(ours.index).fillna(0).to_numpy() == mins]  # full buckets only
        ours = ours[ours.index + pd.Timedelta(minutes=mins) <= now]
        nat = native(tf, start3, end)
        r = compare(ours[ours.index >= nat.index.min()], nat)
        ok_all &= r["exact"] == r["compared"]
        md.append(f"| {tf} | {r['compared']} | {r['exact']} | {r['max_diff']:.6f} |")
        print(f"3) {tf}: {r}")
    md.append("")

    # 4. 4h / 1d (forex.com anchored) vs native 1h aggregated over the same windows
    n1h = native("1h", start3 - 86_400_000, end)
    n1h["sdate"] = session.session_date(n1h.index)
    n1h = n1h[session.in_session(n1h.index)]
    md += ["## 4. 4h and 1d candles (anchored to the 18:00 ET forex.com open)", "",
           "| TF | compared | identical | max diff |", "|---|---|---|---|"]
    for tf in ("4h", "1d"):
        ours = session.resample(s1m, tf)
        theirs = session.resample(n1h, tf)
        # only completed candles fully covered by both
        last_close = now - pd.Timedelta(hours=4 if tf == "4h" else 24)
        ours, theirs = ours[ours.index <= last_close], theirs[theirs.index <= last_close]
        ours = ours[ours.index >= theirs.index.min() + pd.Timedelta(days=1)]
        r = compare(ours, theirs)
        ok_all &= r["exact"] == r["compared"]
        md.append(f"| {tf} | {r['compared']} | {r['exact']} | {r['max_diff']:.6f} |")
        print(f"4) {tf}: {r}")
    md += ["", f"**Result: {'ALL CHECKS PASSED' if ok_all else 'MISMATCHES FOUND (see above)'}**"]
    REPORTS_DIR.mkdir(exist_ok=True)
    (REPORTS_DIR / "candle_check.md").write_text("\n".join(md))
    print("ALL CHECKS PASSED" if ok_all else "MISMATCHES FOUND")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
