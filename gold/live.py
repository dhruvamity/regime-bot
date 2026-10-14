"""Builds the dashboard state from the candle store. Used by the server on every closed 1m candle."""
from __future__ import annotations

import json
import math
import time
from datetime import datetime

import numpy as np
import pandas as pd

from . import regime, report, session, store
from .config import ET, IST, REPORTS_DIR
from .signal import STATE_TEXT, TIER_GREEN, TIER_RED, Engine

LOAD_DAYS = 400  # 6-month percentile window + 6-month same-hour baselines + warm-up; matches the full backtest exactly


def _f(x, nd=3):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(x) else round(x, nd)


def _pct(hist: pd.Series, cur) -> float | None:
    h = hist.dropna()
    if cur is None or not len(h) or not np.isfinite(cur):
        return None
    return round(float((h < cur).mean() * 100), 1)


def _ord(n) -> str:
    n = int(round(n))
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _fmt_t(ts: pd.Timestamp) -> dict:
    return {"utc": ts.isoformat(), "et": ts.tz_convert(ET).strftime("%a %d %b %H:%M ET"),
            "ist": ts.tz_convert(IST).strftime("%a %d %b %H:%M IST")}


def _reasons(row: pd.Series, med_hour_atr: float | None, X: pd.DataFrame) -> list[str]:
    r = []
    vr = row.get("volrel_5m")
    if vr is not None and np.isfinite(vr):
        word = "below" if vr < 1 else "above"
        r.append(f"Movement right now: 5m ATR over the last 4h is ${row.atr_5m_4h:.2f}, {abs(vr - 1) * 100:.0f}% {word} "
                 f"normal for this hour (${med_hour_atr:.2f})." if med_hour_atr else "")
    if np.isfinite(row.get("rng5_rel", np.nan)):
        r.append(f"Last 5 sessions averaged {row.rng5_rel * 100:.0f}% of the usual daily range "
                 f"(60-day median ${row.rng_med60:.0f}).")
    p1 = row.get("past1_1m_24h")
    if p1 is not None and np.isfinite(p1):
        r.append(f"Trades with the 1h bias over the last 24h averaged {p1:+.2f}R at 1:1 on 1m "
                 f"({_ord(row.p_past1_1m_24h)} percentile of 6 months).")
    p2 = row.get("past2_5m_4h")
    if p2 is not None and np.isfinite(p2):
        r.append(f"Last 4h of 5m 1:2 trades with the 1h bias: {p2:+.2f}R average ({_ord(row.p_past2_5m_4h)} percentile).")
    return [x for x in r if x]


def _day_tier(score):
    return "GREEN" if score >= TIER_GREEN else ("AMBER" if score >= TIER_RED else "RED")


def _daily_scores(X: pd.DataFrame, fwd: pd.DataFrame | None, eng: Engine, days: int) -> list[dict]:
    """Average hourly score during London+NY (03:00-13:00 ET) per session day, plus what actually happened."""
    pr = X[X.index >= X.index[-1] - pd.Timedelta(days=days)]
    et = pr.index.tz_convert(ET)
    pr = pr[(et.hour >= 3) & (et.hour <= 13)]
    if fwd is not None:
        pr = pr.join(fwd[["y2", "y1"]], how="left")
    d1 = eng.tfs["1d"]
    rng = pd.Series((d1.h - d1.l).to_numpy(), index=pd.Index(d1.sdate.astype(str)))
    out = []
    for sd, z in pr.groupby(pr.index.tz_convert(ET).strftime("%Y-%m-%d")):
        z = z.dropna(subset=["score"])
        if not len(z):
            continue
        sc = float(z.score.mean())
        out.append({"date": sd, "label": pd.Timestamp(sd).strftime("%a %d %b"), "score": _f(sc, 1), "tier": _day_tier(sc),
                    "red": int((z.tier == "RED").sum()), "amber": int((z.tier == "AMBER").sum()),
                    "green": int((z.tier == "GREEN").sum()),
                    "range": _f(rng.get(sd), 1),
                    "realized_r2": _f(z.y2.mean(), 3) if "y2" in z else None,
                    "realized_r1": _f(z.y1.mean(), 3) if "y1" in z else None})
    return out


def _daily_summary(days: list[dict]) -> list[dict]:
    """Per day-colour: how many days, and what those days actually delivered."""
    if not days:
        return []
    df = pd.DataFrame(days)
    rows = []
    for t in ("GREEN", "AMBER", "RED"):
        z = df[df.tier == t]
        rows.append({"tier": t, "days": int(len(z)), "avg_range": _f(z["range"].mean(), 1) if len(z) else None,
                     "realized_r2": _f(z.realized_r2.mean(), 3) if len(z) else None,
                     "realized_r1": _f(z.realized_r1.mean(), 3) if len(z) else None})
    return rows


def build_state(con, now: datetime | None = None, return_engine: bool = False):
    """`now` (UTC) replays the dashboard as it would have looked at that moment."""
    t0 = time.time()
    now_ts = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    now_ts = now_ts.tz_localize("UTC") if now_ts.tzinfo is None else now_ts.tz_convert("UTC")
    start_ms = int((now_ts - pd.Timedelta(days=LOAD_DAYS)).timestamp() * 1000)
    raw = store.load(con, start_ms=start_ms, end_ms=None if now is None else int(now_ts.timestamp() * 1000) - 59_999)
    eng = Engine(raw)
    T = eng.decision_times(extra_now=True)
    fwd = eng.forward(T[:-1]) if len(T) > 1 else None
    X = eng.score(T, fwd.reindex(T) if fwd is not None else None)
    cur = X.iloc[-1]
    hist = X.iloc[:-1]
    tier = cur.tier if isinstance(cur.tier, str) else "RED"
    title, advice = STATE_TEXT[tier]

    # same-hour normal ATR for the reason text
    same_hour = hist[hist.hour_et == cur.hour_et].atr_5m_4h.tail(126)
    med_hour_atr = float(same_hour.median()) if len(same_hour) else None

    # live LTF structure (descriptive)
    ltf = {}
    for tf in ("1m", "5m", "15m"):
        d = {}
        for k in ("er", "chop", "wick", "vr", "atr"):
            col = f"{k}_{tf}_4h"
            d[k] = _f(cur[col], 3)
            d[k + "_pct"] = _pct(hist[col].tail(126 * 23), cur[col])
        ltf[tf] = d
    tq = _f(cur.trend_q, 1)
    ltf_label = "Trending" if (tq or 0) >= 60 else ("Choppy" if (tq or 0) <= 40 else "Mixed")

    # session status (never blocks the signal; just tells you which candles it is based on)
    last_bar = eng.s1m.index[-1]
    raw_last = raw.index[-1]
    is_open = bool(session.in_session(pd.DatetimeIndex([raw_last]))[0])
    note = None
    if not is_open:
        nxt = session.next_open(raw_last.to_pydatetime())
        note = (f"forex.com session is closed. The reading below uses the final in-session candles "
                f"({last_bar.tz_convert(ET):%a %H:%M} ET). Next open {pd.Timestamp(nxt):%a %H:%M} ET / "
                f"{pd.Timestamp(nxt).tz_convert(IST):%a %H:%M} IST.")

    # hour-of-day guide (last ~6 months of resolved results)
    hrs = []
    if fwd is not None:
        H = hist.join(fwd[["y2", "fwd_range"]]).dropna(subset=["y2"])
        H = H[H.index >= H.index.max() - pd.Timedelta(days=182)]
        g = H.groupby("hour_et").agg(range=("fwd_range", "mean"), netR=("y2", "mean"))
        best = g.netR.rank(pct=True)
        today_et = now_ts.tz_convert(ET).normalize()
        for h, row in g.iterrows():
            t_et = today_et + pd.Timedelta(hours=int(h))
            hrs.append({"hour_et": int(h), "ist": t_et.tz_convert(IST).strftime("%H:%M"),
                        "et": f"{int(h):02d}:00", "range4h": _f(row.range, 1), "netR": _f(row.netR, 3),
                        "quality": "prime" if best[h] >= 0.7 else ("poor" if best[h] <= 0.3 else "ok")})
    cur_hour = int(cur.hour_et)
    hour_now = next((h for h in hrs if h["hour_et"] == cur_hour), None)

    # recent hourly history strip (last ~6 sessions)
    recent = X[X.index >= X.index[-1] - pd.Timedelta(days=8)]
    history = [{"t": int(ts.timestamp()), "et": ts.tz_convert(ET).strftime("%a %H:%M"),
                "ist": ts.tz_convert(IST).strftime("%a %H:%M"), "score": _f(r.score, 1), "tier": r.tier}
               for ts, r in recent.iterrows() if isinstance(r.tier, str)]

    # daily scores (London+NY hours, 03-13 ET) for the last 6 weeks and the last 6 months
    daily = _daily_scores(X, fwd, eng, 45)
    daily_6m = _daily_scores(X, fwd, eng, 182)
    summary_6m = _daily_summary(daily_6m)

    # today vs last week (same elapsed time)
    tv = report.today_vs_last_week(eng)
    keys = ["range", "net", "atr_1m", "atr_5m", "er_5m", "chop_5m", "wick_5m", "vr_5m", "y2_1m", "y2_5m", "y1_1m", "y1_5m"]
    cmp = []
    if len(tv["table_today"]):
        td = tv["table_today"].iloc[0]
        for k in keys:
            cmp.append({"key": k, "today": _f(td.get(k)), "last_week": _f(tv["table_last_week"][k].mean()) if len(tv["table_last_week"]) else None,
                        "median_6m": _f(tv["table_6m"][k].median()), "pct_6m": _pct(tv["table_6m"][k], td.get(k))})

    # wait-or-trade helper: what would move the score out of RED
    need = None
    if tier == "RED" and med_hour_atr:
        need = (f"The quickest way out of RED is movement returning: 5m ATR (4h average) back to about "
                f"${med_hour_atr:.2f}+ for this hour, i.e. bigger candles and range expansion.")

    bt = {}
    try:
        bt = json.loads((REPORTS_DIR / "backtest.json").read_text())
    except Exception:
        pass
    wk = {}
    try:
        wk = json.loads((REPORTS_DIR / "week_report.json").read_text())
    except Exception:
        pass

    htf = eng.htf_bias()
    bias_dirs = [htf[t]["dir"] for t in ("1h", "4h", "1d") if t in htf]
    bias = "LONG" if bias_dirs and all(d > 0 for d in bias_dirs) else ("SHORT" if bias_dirs and all(d < 0 for d in bias_dirs) else "MIXED")
    price = float(raw.c.iloc[-1])

    state = {
        "generated": _fmt_t(pd.Timestamp.now(tz="UTC")),
        "as_of": _fmt_t(last_bar + pd.Timedelta(minutes=1)),
        "price": price,
        "session_open": is_open,
        "session_note": note,
        "signal": {
            "tier": tier, "title": title, "advice": advice,
            "score": _f(cur.score, 1), "move": _f(cur.move, 1), "edge": _f(cur.edge, 1),
            "thresholds": {"red_below": TIER_RED, "green_from": TIER_GREEN},
            "reasons": _reasons(cur, med_hour_atr, X), "how_to_exit_red": need,
            "hour_quality": hour_now,
        },
        "components": {
            "volrel_5m": _f(cur.volrel_5m), "p_volrel_5m": _f(cur.p_volrel_5m, 1),
            "atr_5m_24h": _f(cur.atr_5m_24h), "p_atr_5m_24h": _f(cur.p_atr_5m_24h, 1),
            "rng5_rel": _f(cur.rng5_rel), "p_rng5_rel": _f(cur.p_rng5_rel, 1),
            "past1_1m_24h": _f(cur.past1_1m_24h), "p_past1_1m_24h": _f(cur.p_past1_1m_24h, 1),
            "past2_5m_4h": _f(cur.past2_5m_4h), "p_past2_5m_4h": _f(cur.p_past2_5m_4h, 1),
            "atr_5m_4h": _f(cur.atr_5m_4h), "normal_atr_5m_4h_this_hour": _f(med_hour_atr),
            "rng_prev": _f(cur.rng_prev, 1), "rng_med60": _f(cur.rng_med60, 1),
        },
        "ltf": ltf, "ltf_label": ltf_label, "trend_q": tq,
        "htf": htf, "bias": bias,
        "today_vs_last_week": {"today": tv["today"], "elapsed_hours": tv["elapsed_hours"],
                               "last_week_days": tv["last_week"], "rows": cmp},
        "regime": regime.current(eng.s1m),
        "hours": hrs, "history": history, "daily": daily, "daily_6m": daily_6m, "daily_6m_summary": summary_6m,
        "backtest": {k: bt.get(k) for k in ("TEST (out-of-sample)", "TRAIN", "ALL", "base_rates", "split")} if bt else None,
        "week_report": {k: wk.get(k) for k in ("week", "rank_quietest", "weeks_in_rank", "like_last_week_6m", "quiet_days", "base_days")} if wk else None,
        "compute_seconds": round(time.time() - t0, 2),
    }
    return (state, eng) if return_engine else state


def candles(con, tf: str = "5m", n: int = 400) -> list[dict]:
    """Session-filtered candles for the chart."""
    mins = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}[tf]
    days = max(3, int(n * mins / 1380 * 1.6) + 3)
    raw = store.load(con, start_ms=int((time.time() - days * 86400) * 1000))
    s = session.session_filter(raw)
    d = session.resample(s, tf).tail(n)
    return [{"time": int(ts.timestamp()), "open": r.o, "high": r.h, "low": r.l, "close": r.c} for ts, r in d.iterrows()]
