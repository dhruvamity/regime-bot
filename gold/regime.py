"""Quiet mode: is gold in a low-movement stretch where far targets stop getting hit?

One implementation for the Telegram bot and scripts/backtest_regime.py.

Rule (chosen 14 Oct 2026 on Sep 2023 - Jun 2025, confirmed on Jul 2025 - Oct 2026):
  ratio = average daily range of the last 2 complete sessions
          / median daily range of the last 60 complete sessions
  QUIET when ratio < 0.80. Once quiet, it stays quiet until the ratio is back to 0.90
  (a buffer so a ratio hovering near 0.80 doesn't flip the mode, and the bot, every day).
  Versus the first version (3 sessions, 0.75/0.80) it catches 34-43% of quiet days instead of 19-31%,
  with the same precision (~46% of flagged days were quiet vs a 20-23% base rate), at 12-15 flips per
  100 sessions instead of 8-11.

The bot quotes current evidence from reports/regime_backtest.json (scripts/backtest_regime.py).
On the trader's own entries 1:3 was the best target in normal markets (better than 1:2, p=0.03).
The flag lags: it switches on after quiet sessions, and quiet stretches are short.
"""
from __future__ import annotations

import html
import json

import pandas as pd

from .config import EARLY_CLOSE_DATES, ET, REPORTS_DIR, SESSION_CLOSE_HOUR_ET

LOOKBACK = 2          # sessions averaged
NORMAL_WINDOW = 60    # sessions in the "normal" median
QUIET_BELOW = 0.80    # ratio threshold to switch quiet mode on
QUIET_EXIT = 0.90     # ...and to switch it off again
MIN_BARS = 600        # a session with fewer in-session 1m candles (holiday stub, data gap) is skipped
STOP_USD = 3.0
QUIET_TARGET_CAP = 9.0    # 1:3 on a $3 stop
FAR_TARGET = 15.0


def session_ranges(s1m: pd.DataFrame) -> pd.Series:
    """Daily range per complete forex.com session, indexed by session date.
    s1m must be session-filtered (has 'sdate'); the last session is dropped if still in progress."""
    g = s1m.groupby("sdate")
    d = pd.DataFrame({"rng": g.h.max() - g.l.min(), "n": g.size(),
                      "end": s1m.index.to_series().groupby(s1m["sdate"]).max()})
    d.index = pd.to_datetime(d.index.astype(str))
    d = d.sort_index()
    if len(d):
        # the last session counts only once its final candle is in: 16:59 ET, or 13:29 ET on the listed
        # early-close days. (Checking 13:29 on every day made each 13:30 ET reading treat a half-finished
        # session as complete.)
        last_end = d.end.iloc[-1].tz_convert(ET)
        close_hr = EARLY_CLOSE_DATES.get(d.index[-1].strftime("%Y-%m-%d"), SESSION_CLOSE_HOUR_ET)
        final = pd.Timestamp(d.index[-1].date()).tz_localize(ET) + pd.Timedelta(hours=close_hr) - pd.Timedelta(minutes=1)
        if last_end < final:
            d = d.iloc[:-1]
    return d.rng[d.n >= MIN_BARS]


def series(rng: pd.Series) -> pd.DataFrame:
    """Mode as known after each session closes (applies to the NEXT session)."""
    out = pd.DataFrame({"rng": rng})
    out["avgN"] = rng.rolling(LOOKBACK).mean()
    out["normal"] = rng.rolling(NORMAL_WINDOW).median()
    out["ratio"] = out.avgN / out.normal
    mode, cur = [], None
    for r in out.ratio:
        if pd.isna(r):
            mode.append(None)
            continue
        cur = "QUIET" if (r < QUIET_BELOW or (cur == "QUIET" and r < QUIET_EXIT)) else "NORMAL"
        mode.append(cur)
    out["mode"] = mode
    return out


def current(s1m: pd.DataFrame) -> dict | None:
    r = series(session_ranges(s1m)).dropna()
    if r.empty:
        return None
    last = r.iloc[-1]
    since = r.index[-1]
    for d, m in r["mode"][::-1].items():
        if m != last["mode"]:
            break
        since = d
    tail = r.rng.iloc[-LOOKBACK:]
    return {
        "mode": last["mode"],
        "ratio": round(float(last.ratio), 3),
        "avgN": round(float(last.avgN), 1),
        "lookback": LOOKBACK,
        "lastN": [round(float(x), 1) for x in tail],
        "lastN_dates": [d.strftime("%Y-%m-%d") for d in tail.index],
        "normal": round(float(last.normal), 1),
        "threshold": round(float(last.normal) * QUIET_BELOW, 1),
        "exit_level": round(float(last.normal) * QUIET_EXIT, 1),
        "as_of_session": r.index[-1].strftime("%Y-%m-%d"),
        "since_session": since.strftime("%Y-%m-%d"),
        "target_cap": QUIET_TARGET_CAP if last["mode"] == "QUIET" else None,
    }


def _d(s: str) -> str:
    return pd.Timestamp(s).strftime("%a %d %b")


def load_stats() -> dict:
    """Per-mode results from scripts/backtest_regime.py (regenerated daily by the server)."""
    try:
        res = json.loads((REPORTS_DIR / "regime_backtest.json").read_text())
        return {row["mode at session start"]: row for row in res["table"]} | {"_sessions": res["sessions"]}
    except Exception:
        return {}


def evidence(st: dict) -> list[str]:
    q, n = st.get("QUIET"), st.get("NORMAL")
    if not q or not n:
        return []
    return [f"Backtest on the bot's data ({st['_sessions']} sessions): after a QUIET reading the next evening "
            f"was quiet {q['next evening quiet %']:.0f}% of the time ({n['next evening quiet %']:.0f}% otherwise). "
            f"Within an hour, $16.5 was reached {q['reach $16.5 in 60 min %']:.0f}% of the time "
            f"({n['reach $16.5 in 60 min %']:.0f}% normally) and $9 {q['reach $9 in 60 min %']:.0f}% "
            f"({n['reach $9 in 60 min %']:.0f}%)."]


def summary_line(r: dict | None) -> str:
    """One line for /status and the daily brief."""
    if not r:
        return ""
    if r["mode"] == "QUIET":
        return (f"🌙 <b>QUIET MODE</b> · last {LOOKBACK} sessions {r['ratio'] * 100:.0f}% of a normal range → "
                f"<b>target max ${QUIET_TARGET_CAP:.0f} (1:3), never ${FAR_TARGET:.0f}+</b>")
    return f"☀️ Normal movement · last {LOOKBACK} sessions {r['ratio'] * 100:.0f}% of a normal range · 1:3 targets OK"


def detail_text(r: dict | None, st: dict | None = None) -> str:
    """Reply to /mode."""
    if not r:
        return "Quiet-mode check needs 60 complete sessions of candles; not enough data yet."
    st = load_stats() if st is None else st
    ranges = ", ".join(f"${x:.0f}" for x in r["lastN"])
    lines = [summary_line(r), "",
             f"Daily range, last {LOOKBACK} sessions: {ranges} (average <b>${r['avgN']:.0f}</b>).",
             f"Normal (median of {NORMAL_WINDOW} sessions): ${r['normal']:.0f}. "
             f"Quiet below {QUIET_BELOW:.0%} = <b>${r['threshold']:.0f}</b>.",
             f"In this mode since the session of {_d(r['since_session'])}."]
    if r["mode"] == "QUIET":
        lines += [f"Quiet mode ends when the {LOOKBACK}-session average is back above ${r['exit_level']:.0f} "
                  f"({QUIET_EXIT:.0%} of normal).", "",
                  f"<b>Cap the target at ${QUIET_TARGET_CAP:.0f} (1:3 on a ${STOP_USD:.0f} stop). "
                  f"Never aim for ${FAR_TARGET:.0f}+.</b>"]
    else:
        lines += [f"Quiet mode switches on when the {LOOKBACK}-session average drops below ${r['threshold']:.0f}.", "",
                  "On your own entries, 1:3 was the best target in normal markets (better than 1:2)."]
    ev = evidence(st)
    if ev:
        lines += [""] + ev
    lines += ["", "<i>Read it as “today is likely quieter”. It lags, and quiet stretches are often over within days.</i>"]
    return "\n".join(lines)


def alert_text(r: dict, st: dict | None = None) -> str:
    """Sent when the mode flips."""
    st = load_stats() if st is None else st
    e = lambda x: html.escape(str(x), quote=False)  # noqa: E731
    ranges = ", ".join(f"${x:.0f}" for x in r["lastN"])
    head = (f"Last {LOOKBACK} sessions averaged a <b>${r['avgN']:.0f}</b> daily range ({e(ranges)}): "
            f"{r['ratio'] * 100:.0f}% of normal (${r['normal']:.0f}).")
    if r["mode"] == "QUIET":
        lines = ["🌙 <b>GOLD: QUIET MODE ON</b>", head, "",
                 f"<b>Cap the target at ${QUIET_TARGET_CAP:.0f} (1:3 on a ${STOP_USD:.0f} stop). "
                 f"Never aim for ${FAR_TARGET:.0f}+.</b>"]
    else:
        lines = ["☀️ <b>GOLD: QUIET MODE OFF</b>", head, "", "Normal targets are back; on your entries 1:3 has been the best."]
    ev = evidence(st)
    return "\n".join(lines + ([""] + ev if ev else []))
