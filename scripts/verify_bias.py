"""Check that the live SMC bias alerts are exactly the switches the full-history mapping finds.

Replays gold.alert_runner.AlertRunner.smc_process every STEP minutes over the last DAYS days, each step seeing
only the 1m candles a live server would have stored by then. Compares what it would have sent with the switches
gold/bias.py finds on the full history (what scripts/backtest_bias.py measures):
  * nothing missing, extra or duplicated, and no switch that later "repaints" away
  * every alert sent at the first step after its candle closed
  * the runner is restarted from its saved state halfway, and taken offline for 3 hours over the stretch with the
    most switches: after the outage it must hold back everything older than STALE_MIN and send the rest once

  python scripts/verify_bias.py [--days 21] [--step 15]      -> reports/bias_check.md, exit 1 on any mismatch
"""
import argparse
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from gold import bias, smc_alerts, store  # noqa: E402
from gold.alert_runner import STALE_MIN, AlertRunner  # noqa: E402
from gold.config import IST, LISTING_MS, REPORTS_DIR  # noqa: E402

STALE = pd.Timedelta(minutes=STALE_MIN)


def keys(a) -> list:
    return [(a.kind, tf, a.time.tz_convert("UTC"), a.direction) for tf in [*a.data.get("also", []), a.tf]]


def fmt(k) -> str:
    return f"{k[0]} {k[1]} {'▲' if k[3] > 0 else '▼'} @ {k[2].tz_convert(IST):%a %d %b %H:%M} IST"


def main(days: int, step: int):
    t0 = time.time()
    con = store.connect()
    raw = store.load(con, start_ms=LISTING_MS)
    # the store as a live server would have had it at each step: candles that opened before `end_ms`
    ms = raw.index.as_unit("ms").asi8
    store.load = lambda c, start_ms=None, end_ms=None: raw[(ms >= (start_ms or 0)) & (ms <= (end_ms or 1 << 62))]
    cfg = smc_alerts.settings({})          # the defaults, independent of any local .env
    fr, last = bias.load_frames(con)
    full = bias.build(fr, last)
    end = last.floor(f"{step}min")
    start = end - pd.Timedelta(days=days)
    ref = {k for a in smc_alerts.alerts_between(full, start, end, cfg) for k in keys(a)}

    steps = pd.date_range(start, end, freq=f"{step}min")
    restart_at = steps[len(steps) // 2]
    # outage: the 3-hour window after the restart holding the most switches
    later = sorted(k for k in ref if k[2] > restart_at)
    off_from, best = steps[int(len(steps) * .75)], -1
    for k in later:
        n = sum(1 for x in later if k[2] <= x[2] < k[2] + pd.Timedelta(hours=3))
        if n > best:
            best, off_from = n, k[2] - pd.Timedelta(minutes=1)
    off_to = off_from + pd.Timedelta(hours=3)

    state = Path(tempfile.mkdtemp()) / "alert_state.json"
    r = AlertRunner(state)
    r.bias_cfg = cfg
    r.smc_process(con, now=steps[0], as_of=steps[0])        # warm start: adopts the structure silently
    sent, when = [], {}
    for t in steps[1:]:
        if off_from < t <= off_to:
            continue
        if t == restart_at:
            r = AlertRunner(state)
            r.bias_cfg = cfg
        for a in r.smc_process(con, now=t, as_of=t):
            for k in keys(a):
                sent.append(k)
                when.setdefault(k, t)
    resume = next(t for t in steps if t > off_to)
    held = {k for k in ref if off_from < k[2] <= resume and k[2] < resume - STALE}
    expect = ref - held
    got = set(sent)
    missing, extra = sorted(expect - got), sorted(got - expect)
    dup = sorted({k for k in sent if sent.count(k) > 1})
    late = sorted(k for k in got & expect if when[k] - k[2] > pd.Timedelta(minutes=step) and not (off_from < k[2] <= resume))
    ok = not (missing or extra or dup or late)

    L = ["# SMC bias alerts: live replay check", "",
         f"{pd.Timestamp.now(tz='UTC'):%Y-%m-%d %H:%M} UTC · `scripts/verify_bias.py --days {days} --step {step}` · "
         f"{len(steps)} steps · {time.time() - t0:.0f}s", "",
         f"* Window {start.tz_convert(IST):%d %b %H:%M} → {end.tz_convert(IST):%d %b %H:%M} IST. Settings: trend "
         f"{','.join(sorted(cfg['BIAS_TREND_TFS'], key=bias.TF_ORDER.index))}, internal "
         f"{','.join(sorted(cfg['BIAS_INTERNAL_TFS'], key=bias.TF_ORDER.index))}.",
         f"* Switches in the full-history mapping: **{len(ref)}**. Sent by the replay: **{len(got)}** "
         f"({len(sent)} including any repeats).",
         f"* Restart at {restart_at.tz_convert(IST):%d %b %H:%M} IST. Outage {off_from.tz_convert(IST):%d %b %H:%M} → "
         f"{off_to.tz_convert(IST):%H:%M} IST: {len(held)} switch(es) correctly held back as older than {STALE_MIN} min.",
         f"* Missing: {len(missing)} · extra / repainted: {len(extra)} · duplicated: {len(dup)} · late: {len(late)}", "",
         f"**{'ALL CHECKS PASSED' if ok else 'MISMATCH'}**", ""]
    for name, lst in (("Missing", missing), ("Extra", extra), ("Duplicated", dup), ("Late", late)):
        if lst:
            L += [f"## {name}", ""] + [f"* {fmt(k)}" for k in lst[:50]] + [""]
    L += ["## Every switch sent", ""] + [f"* {fmt(k)} → sent at {when[k].tz_convert(IST):%H:%M}" for k in sorted(got)]
    REPORTS_DIR.mkdir(exist_ok=True)
    (REPORTS_DIR / "bias_check.md").write_text("\n".join(L) + "\n")
    print("\n".join(L[:12]))
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=21)
    ap.add_argument("--step", type=int, default=15)
    a = ap.parse_args()
    sys.exit(0 if main(a.days, a.step) else 1)
