"""Download/refresh all XAUUSDT 1m history into data/candles.db."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gold import fetch, store  # noqa: E402

if __name__ == "__main__":
    con = store.connect()
    t0 = time.time()
    n = fetch.backfill(con, verbose=True)
    first = con.execute("SELECT MIN(ts), MAX(ts), COUNT(*) FROM candles_1m").fetchone()
    print(f"added {n} candles in {time.time() - t0:.0f}s")
    print("range:", time.strftime("%Y-%m-%d %H:%M", time.gmtime(first[0] / 1000)), "->",
          time.strftime("%Y-%m-%d %H:%M", time.gmtime(first[1] / 1000)), "UTC  total", first[2])
