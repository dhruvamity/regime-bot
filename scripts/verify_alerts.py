"""Check that the live bot sends exactly the alerts the backtests describe.

Replays the server's own code path, one step per 15-minute candle close, each step seeing only the candles
a live server would have had (the same LOAD_DAYS window), and compares with the backtests' reference lists:
  1. conditions + trend-shift alerts (gold.alert_runner.AlertRunner) vs scripts/backtest_alerts.py logic.
     The runner is restarted from its saved state halfway, and taken offline for 3 hours over a stretch that
     contains alerts: restarts must never repeat an alert, and alerts older than STALE_MIN must be held back.
  2. quiet-mode flips (AlertRunner.regime_change + gold.regime) vs gold.regime.series on the full history
     (scripts/backtest_regime.py). Each flip must be sent once, at the close of the session that caused it.

  python scripts/verify_alerts.py [--days 30] [--regime-days 120]   -> reports/alert_check.md, exit 1 on a mismatch
"""
import argparse
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from gold import alerts, regime, session, store  # noqa: E402
from gold.alert_runner import STALE_MIN, AlertRunner  # noqa: E402
from gold.config import IST, REPORTS_DIR  # noqa: E402
from gold.live import LOAD_DAYS  # noqa: E402
from gold.signal import Engine  # noqa: E402

REF_START = pd.Timestamp("2026-01-05", tz="UTC")   # same start as scripts/backtest_alerts.py
STALE = pd.Timedelta(minutes=STALE_MIN)
LOAD = pd.Timedelta(days=LOAD_DAYS)


def akey(a) -> tuple:
    return (a.kind, a.time.tz_convert("UTC"), a.tf, a.direction if a.kind == "SHIFT" else None)


def fmt(k) -> str:
    arrow = {1: " ▲", -1: " ▼"}.get(k[3], "")
    return f"{k[0]}{' ' + k[2] if k[2] else ''}{arrow} @ {k[1].tz_convert(IST):%a %d %b %H:%M} IST"


def check_alerts(raw_all, full, days):
    eng_ref = full
    S = eng_ref.score(eng_ref.slot_times(15))
    S = S[S.index >= REF_START]
    tr = alerts.ConditionTracker()
    ref = set()
    for t, row in S.iterrows():
        for a in tr.step(t, row):
            ref.add(akey(a))
    for t, e in alerts.shift_events(eng_ref).iterrows():
        ref.add(("SHIFT", t.tz_convert("UTC"), e.tf, int(e.dir)))

    steps = eng_ref.slot_times(15)
    steps = steps[steps >= steps[-1] - pd.Timedelta(days=days)]
    ref = {k for k in ref if k[1] > steps[0]}
    restart_at = steps[len(steps) // 2]
    # outage: the 3-hour window (after the restart) holding the most alerts that must be held back
    best, off_from = -1, steps[int(len(steps) * 0.75)]
    for i in range(len(steps) // 2 + 4, len(steps) - 12):
        a, b = steps[i - 1], steps[i] + pd.Timedelta(hours=3)
        n = sum(a < k[1] < b - STALE for k in ref)
        if n > best:
            best, off_from = n, steps[i]
    off_to = off_from + pd.Timedelta(hours=3)
    prev_step = steps[steps < off_from][-1]
    held = {k for k in ref if prev_step < k[1] < off_to - STALE}

    tmp = Path(tempfile.mkdtemp()) / "alert_state.json"
    runner = AlertRunner(tmp)
    sent = []
    for t in steps:
        if off_from <= t < off_to:
            continue
        if t == restart_at:
            runner = AlertRunner(tmp)          # restart: a fresh object reading the saved state
        raw = raw_all[(raw_all.index >= t - LOAD) & (raw_all.index < t)]
        sent += [(akey(a), t) for a in runner.process(Engine(raw), now=t)]
    keys = [k for k, _ in sent]
    expected = ref - held
    res = {
        "steps": steps, "restart_at": restart_at, "off": (off_from, off_to), "expected": expected, "held": held,
        "sent": sent, "missing": sorted(expected - set(keys)), "extra": sorted(set(keys) - ref),
        "dupes": sorted({k for k in keys if keys.count(k) > 1}), "leaked": sorted(set(keys) & held),
        "late": [(k, at) for k, at in sent if at - k[1] > STALE],
    }
    res["ok"] = not any(res[x] for x in ("missing", "extra", "dupes", "leaked", "late"))
    return res


def check_regime(raw_all, days):
    s_all = session.session_filter(raw_all)
    full = regime.series(regime.session_ranges(s_all)).dropna(subset=["ratio"])
    last_candle = s_all.index.to_series().groupby(s_all["sdate"]).max()
    last_candle.index = pd.to_datetime(last_candle.index.astype(str))
    steps = Engine(raw_all).slot_times(15)
    steps = steps[steps >= steps[-1] - pd.Timedelta(days=days)]
    ref, prev = {}, None
    for d, m in full["mode"].items():
        close = last_candle[d] + pd.Timedelta(minutes=1)
        if prev is not None and m != prev and close > steps[0]:
            ref[("QUIET_" + ("ON" if m == "QUIET" else "OFF"), d.strftime("%Y-%m-%d"))] = close
        prev = m
    runner = AlertRunner(Path(tempfile.mkdtemp()) / "alert_state.json")
    sent = {}
    modes_seen = []
    for t in steps:
        s1m = s_all[(s_all.index >= t - LOAD) & (s_all.index < t)]
        r = regime.current(s1m)
        if runner.regime_change(r, now=t):
            sent.setdefault((runner.history[-1]["kind"], runner.regime["session"]), []).append(t)
        modes_seen.append(r["mode"] if r else None)
    res = {"steps": steps, "ref": ref, "sent": sent,
           "missing": sorted(set(ref) - set(sent)), "extra": sorted(set(sent) - set(ref)),
           "dupes": sorted(k for k, v in sent.items() if len(v) > 1),
           "delay": {k: (v[0] - ref[k]).total_seconds() / 60 for k, v in sent.items() if k in ref}}
    res["late_or_early"] = {k: v for k, v in res["delay"].items() if not (0 <= v <= 15)}
    res["ok"] = not any(res[x] for x in ("missing", "extra", "dupes", "late_or_early"))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--regime-days", type=int, default=120)
    args = ap.parse_args()
    t0 = time.time()
    raw_all = store.load(store.connect())
    full = Engine(raw_all)
    A = check_alerts(raw_all, full, args.days)
    Q = check_regime(raw_all, args.regime_days)
    ok = A["ok"] and Q["ok"]
    keys = [k for k, _ in A["sent"]]
    by_kind = pd.Series([k[0] for k in keys]).value_counts().to_dict() if keys else {}
    st, (of, ot) = A["steps"], A["off"]
    md = ["# Alert check: live code vs backtest", "",
          f"Generated {pd.Timestamp.now(tz=IST):%d %b %Y %H:%M} IST.", "",
          "## 1. Trade-condition and trend-shift alerts", "",
          f"Replayed {len(st)} live steps (every 15-minute candle close) from {st[0].tz_convert(IST):%d %b %H:%M} to "
          f"{st[-1].tz_convert(IST):%d %b %H:%M} IST, each with only the candles a live server would have had. Restart "
          f"from saved state at {A['restart_at'].tz_convert(IST):%a %d %b %H:%M} IST; offline "
          f"{of.tz_convert(IST):%a %d %b %H:%M}–{ot.tz_convert(IST):%H:%M} IST.", "",
          f"* Should be sent: **{len(A['expected'])}** · must be held back as stale during the outage: **{len(A['held'])}**",
          f"* Sent by the live code: **{len(keys)}** {by_kind}",
          f"* Missing **{len(A['missing'])}** · extra **{len(A['extra'])}** · duplicates **{len(A['dupes'])}** · "
          f"more than {STALE_MIN} min late **{len(A['late'])}** · stale alerts leaked **{len(A['leaked'])}**",
          f"* **{'PASS' if A['ok'] else 'FAIL'}**", "",
          "## 2. Quiet-mode flips", "",
          f"Replayed {len(Q['steps'])} steps over {args.regime_days} days ({Q['steps'][0].tz_convert(IST):%d %b} → "
          f"{Q['steps'][-1].tz_convert(IST):%d %b}).", "",
          f"* Expected flips **{len(Q['ref'])}** · sent **{len(Q['sent'])}** · missing **{len(Q['missing'])}** · extra "
          f"**{len(Q['extra'])}** · duplicates **{len(Q['dupes'])}** · not within 15 min of the session close "
          f"**{len(Q['late_or_early'])}**",
          "* " + (", ".join(f"{k[0]} after {k[1]} ({v:+.0f} min)" for k, v in sorted(Q['delay'].items(), key=lambda x: x[0][1])) or "no flips"),
          f"* **{'PASS' if Q['ok'] else 'FAIL'}**", "",
          "**" + ("ALL CHECKS PASSED" if ok else "MISMATCH") + "**", ""]
    for name, lst in (("Missing", A["missing"]), ("Extra", A["extra"]), ("Duplicates", A["dupes"]), ("Leaked", A["leaked"])):
        if lst:
            md += [f"### {name}", ""] + [f"* {fmt(k)}" for k in lst] + [""]
    for name in ("missing", "extra", "dupes"):
        if Q[name]:
            md += [f"### Quiet-mode {name}", ""] + [f"* {k[0]} after {k[1]}: sent at "
                                                    f"{', '.join(f'{t.tz_convert(IST):%a %d %b %H:%M}' for t in Q['sent'].get(k, []))} IST"
                                                    for k in Q[name]] + [""]
    if A["held"]:
        md += ["### Held back during the outage (correct)", ""] + [f"* {fmt(k)}" for k in sorted(A["held"], key=lambda k: k[1])] + [""]
    md += ["### Every alert sent in the replay", ""] + [f"* {fmt(k)}" for k in sorted(set(keys), key=lambda k: k[1])]
    md += ["", f"_Took {time.time() - t0:.0f}s._"]
    REPORTS_DIR.mkdir(exist_ok=True)
    (REPORTS_DIR / "alert_check.md").write_text("\n".join(md) + "\n")
    print("\n".join(md[:24]))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
