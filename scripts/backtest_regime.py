"""Backtest the quiet-mode flag (gold/regime.py) exactly as the bot computes it.

For every session, the mode known after the previous session closed is compared with what the
NEXT evening (17:00-24:00 IST, the user's trading window) actually did:
  * was the evening quiet (5m movement < 80% of its 60-session median)?
  * from every 5m close, did price reach $9 (1:3 on a $3 stop) / $16.5 within 60 minutes?
  * random entries every 5 minutes 17:00-23:00 IST, long and short, $3 stop, 2-hour limit:
    average R at 1:2, 1:3 and 1:5.5 ($16.5), before costs.
Also counts how often the mode would have flipped (= alerts sent).

Uses only the bot's own data (Binance XAUUSDT perp, listed Dec 2025), so the first ~60 sessions
are warm-up. The 14 Oct 2026 study ran the same rule on PAXG + perp back to Sep 2023.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from gold import regime, session, store  # noqa: E402
from gold.config import IST, REPORTS_DIR  # noqa: E402
from gold.util import md_table  # noqa: E402

STOP = regime.STOP_USD
MULTS = (2.0, 3.0, 5.5)


def evening_stats(s1m: pd.DataFrame) -> pd.DataFrame:
    """Per session: evening 5m movement, reach rates and random-entry R."""
    H, L, C = s1m.h.to_numpy(), s1m.l.to_numpy(), s1m.c.to_numpy()
    ist = s1m.index.tz_convert(IST)
    eve = ist.hour >= 17
    sd = pd.to_datetime(s1m.sdate.astype(str)).to_numpy()
    rows = []
    pos = np.arange(len(C))
    for d, idx in pd.Series(pos[eve]).groupby(sd[eve]).apply(np.asarray).items():
        d = np.datetime64(d)
        if len(idx) < 300:
            continue
        e5 = idx[ist.minute[idx] % 5 == 4]   # 5m closes
        move = np.abs(np.diff(C[e5])).sum()
        reach9 = reach16 = 0
        n_reach = 0
        rr = {m: [] for m in MULTS}
        for e in e5:
            b = min(len(C), e + 61)
            if sd[b - 1] != d or b - e < 50:
                continue
            best = max(H[e + 1:b].max() - C[e], C[e] - L[e + 1:b].min())
            reach9 += best >= 9.0
            reach16 += best >= 16.5
            n_reach += 1
            if ist.hour[e] >= 23:
                continue
            b2 = min(len(C), e + 121)
            for side in (1, -1):
                fav = (H[e + 1:b2] - C[e]) if side == 1 else (C[e] - L[e + 1:b2])
                adv = (C[e] - L[e + 1:b2]) if side == 1 else (H[e + 1:b2] - C[e])
                st = adv >= STOP
                i_s = np.argmax(st) if st.any() else 10**9
                for m in MULTS:
                    tg = fav >= STOP * m
                    i_t = np.argmax(tg) if tg.any() else 10**9
                    if i_s == i_t == 10**9:
                        rr[m].append(side * (C[b2 - 1] - C[e]) / STOP)
                    else:
                        rr[m].append(m if i_t < i_s else -1.0)
        row = {"sdate": pd.Timestamp(d), "move": move, "n": n_reach,
               "reach9": reach9 / max(n_reach, 1), "reach16": reach16 / max(n_reach, 1)}
        for m in MULTS:
            row[f"R_{m:g}"] = float(np.mean(rr[m])) if rr[m] else np.nan
            row[f"n_{m:g}"] = len(rr[m])
        rows.append(row)
    return pd.DataFrame(rows).set_index("sdate")


def main():
    t0 = time.time()
    con = store.connect()
    s1m = session.session_filter(store.load(con))
    ser = regime.series(regime.session_ranges(s1m))
    ev = evening_stats(s1m)
    ev["move_rel"] = ev.move / ev.move.shift(1).rolling(60, min_periods=40).median()
    # the mode known when each session starts = the reading after the previous session closed
    mode_next = ser["mode"].shift(1).reindex(ev.index, method="ffill")
    ev["mode"] = mode_next
    Z = ev.dropna(subset=["mode", "move_rel"])

    g = Z.groupby("mode")
    t = pd.DataFrame({
        "sessions": g.size(),
        "next evening quiet %": g.move_rel.apply(lambda v: (v < 0.8).mean() * 100),
        "evening move vs normal": g.move_rel.mean(),
        "reach $9 in 60 min %": g.reach9.mean() * 100,
        "reach $16.5 in 60 min %": g.reach16.mean() * 100,
    })
    for m in MULTS:
        tot = (Z[f"R_{m:g}"].fillna(0) * Z[f"n_{m:g}"]).groupby(Z["mode"]).sum()
        t[f"random 1:{m:g} R"] = tot / Z[f"n_{m:g}"].groupby(Z["mode"]).sum()
    t.index.name = "mode at session start"

    plain = ser.ratio.dropna().lt(regime.QUIET_BELOW)
    flips = int((ser["mode"].dropna() != ser["mode"].dropna().shift()).sum() - 1)
    flips_plain = int((plain != plain.shift()).sum() - 1)
    now = regime.current(s1m)
    res = {
        "generated": pd.Timestamp.now(tz="UTC").isoformat(),
        "sessions": int(len(Z)), "first": str(Z.index.min().date()), "last": str(Z.index.max().date()),
        "table": json.loads(t.reset_index().to_json(orient="records")),
        "flips": flips, "flips_without_buffer": flips_plain, "current": now,
    }
    REPORTS_DIR.mkdir(exist_ok=True)
    (REPORTS_DIR / "regime_backtest.json").write_text(json.dumps(res, indent=1, default=str))
    md = [
        "# Quiet-mode backtest",
        "",
        f"Sessions {res['first']} to {res['last']} ({res['sessions']}), Binance XAUUSDT perp, forex.com hours. "
        f"Mode = average daily range of the last {regime.LOOKBACK} sessions vs the {regime.NORMAL_WINDOW}-session median: QUIET below "
        f"{regime.QUIET_BELOW:.2f}, back to NORMAL at {regime.QUIET_EXIT:.2f}. Each session is judged by the mode "
        "known before it opened; outcomes are for the 17:00-24:00 IST evening.",
        "",
        md_table(t, "{:.2f}"),
        "",
        f"Mode flips (alerts) over the period: {flips} with the {regime.QUIET_BELOW:.2f}/{regime.QUIET_EXIT:.2f} buffer, "
        f"{flips_plain} with a single {regime.QUIET_BELOW:.2f} line.",
        "",
        "Reach columns: how often a far target gets hit at all. R columns: random entries (no edge by design, "
        "no costs), which show whether a far target also cost expectancy in that mode. In quiet mode the stop "
        "gets hit less often too, so fewer far targets does not automatically mean lower R.",
        "",
        f"Now: **{now['mode']}** (ratio {now['ratio']:.2f}, last {regime.LOOKBACK} ranges {now['lastN']}, normal ${now['normal']:.0f})." if now else "",
        "",
        f"_Computed in {time.time() - t0:.0f}s._",
    ]
    (REPORTS_DIR / "regime_backtest.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
