"""Binance USD-M REST backfill for XAUUSDT 1m candles."""
import time

import requests

from . import store
from .config import LISTING_MS, REST_BASE, SYMBOL

MIN_MS = 60_000


def _klines(start_ms: int, limit: int = 1500, session: requests.Session | None = None):
    s = session or requests
    for attempt in range(5):
        r = s.get(
            f"{REST_BASE}/fapi/v1/klines",
            params={"symbol": SYMBOL, "interval": "1m", "startTime": start_ms, "limit": limit},
            timeout=20,
        )
        if r.status_code in (418, 429):
            time.sleep(int(r.headers.get("Retry-After", 5)) + 1)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("Binance rate limit: gave up after retries")


def rows_from_klines(kl, now_ms: int):
    """Only closed candles (close time already passed) are returned."""
    out = []
    for k in kl:
        if k[6] >= now_ms:
            continue
        out.append((int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5]), int(k[8])))
    return out


def backfill(con, start_ms: int | None = None, verbose: bool = False) -> int:
    """Fill from the last stored candle (or start_ms / listing date) up to now."""
    last = store.last_ts(con)
    cursor = start_ms if start_ms is not None else (last + MIN_MS if last else LISTING_MS)
    total = 0
    sess = requests.Session()
    while True:
        now_ms = int(time.time() * 1000)
        if cursor > now_ms - MIN_MS:
            break
        kl = _klines(cursor, session=sess)
        if not kl:
            break
        rows = rows_from_klines(kl, now_ms)
        total += store.upsert(con, rows)
        nxt = int(kl[-1][0]) + MIN_MS
        if verbose and total and (total // 1500) % 20 == 0:
            print(f"  ... {time.strftime('%Y-%m-%d %H:%M', time.gmtime(nxt / 1000))} UTC  ({total} candles)", flush=True)
        if nxt <= cursor or len(kl) < 2:
            break
        cursor = nxt
    return total
