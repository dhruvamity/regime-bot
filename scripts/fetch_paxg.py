"""Download Binance spot PAXGUSDT 1m candles (gold-backed token, 1 PAXG = 1 oz) into data/paxg_1m.parquet.

Used only by scripts/backtest_bias.py to extend the structure backtest before the XAUUSDT perp listed
(11 Dec 2025). Same idea as the quiet-mode study, which ran on PAXG + perp back to Sep 2023.
Re-running only adds what is missing.  Usage: python scripts/fetch_paxg.py [YYYY-MM-DD start]
"""
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "paxg_1m.parquet"
URL = "https://api.binance.com/api/v3/klines"
END = pd.Timestamp("2025-12-11", tz="UTC")       # the perp takes over from here


def main(start: str = "2023-09-01"):
    old = pd.read_parquet(OUT) if OUT.exists() else None
    cur = int((old.index[-1] + pd.Timedelta(minutes=1)).timestamp() * 1000) if old is not None and len(old) else \
        int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    end = int(END.timestamp() * 1000)
    rows, s = [], requests.Session()
    while cur < end:
        for attempt in range(6):
            r = s.get(URL, params={"symbol": "PAXGUSDT", "interval": "1m", "startTime": cur, "limit": 1000}, timeout=20)
            if r.status_code in (418, 429):
                time.sleep(int(r.headers.get("Retry-After", 5)) + 1)
                continue
            r.raise_for_status()
            break
        kl = r.json()
        if not kl:
            break
        rows += [(int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])) for k in kl]
        nxt = int(kl[-1][0]) + 60_000
        if nxt <= cur:
            break
        cur = nxt
        if len(rows) % 100_000 < 1000:
            print(f"  {pd.Timestamp(cur, unit='ms'):%Y-%m-%d}  {len(rows)} candles", flush=True)
    df = pd.DataFrame(rows, columns=["ts", "o", "h", "l", "c", "v"])
    df.index = pd.to_datetime(df.pop("ts"), unit="ms", utc=True)
    df.index.name = "time"
    df = df[df.index < END]
    if old is not None:
        df = pd.concat([old, df])
    df = df[~df.index.duplicated(keep="last")].sort_index()
    OUT.parent.mkdir(exist_ok=True)
    df.to_parquet(OUT)
    print(f"{len(df)} candles {df.index[0]} -> {df.index[-1]}")


if __name__ == "__main__":
    main(*sys.argv[1:])
