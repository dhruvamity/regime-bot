"""Walk-forward backtest of the trade/no-trade filter.

At every hourly decision point we compute the signal using only data available then,
and compare it with what happened over the next 4 hours (same session): net R of
1:2 and 1:1 trend-following entries on 1m/5m/15m in the 1h-bias direction, and the
4h price range. The first 60% of the history is "train", the rest is an untouched test.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from gold import store  # noqa: E402
from gold.config import ET, IST, REPORTS_DIR  # noqa: E402
from gold.signal import TIER_GREEN, TIER_RED, Engine  # noqa: E402
from gold.util import md_table  # noqa: E402

GOOD, BAD = 0.0, -0.25


def tier_table(Z: pd.DataFrame) -> pd.DataFrame:
    g = Z.groupby("tier")
    t = g.agg(n=("y2", "size"), net_R_1to2=("y2", "mean"), net_R_1to1=("y1", "mean"),
              R2_1m=("y2_1m", "mean"), R2_5m=("y2_5m", "mean"), R2_15m=("y2_15m", "mean"),
              R1_1m=("y1_1m", "mean"), R1_5m=("y1_5m", "mean"), R1_15m=("y1_15m", "mean"),
              next4h_range=("fwd_range", "mean"))
    t["share_of_time"] = t.n / t.n.sum() * 100
    t["good_4h_pct"] = g.apply(lambda z: (z.y2 > GOOD).mean() * 100)
    t["bad_4h_pct"] = g.apply(lambda z: (z.y2 < BAD).mean() * 100)
    return t.reindex(["GREEN", "AMBER", "RED"])


def main():
    t0 = time.time()
    con = store.connect()
    eng = Engine(store.load(con))
    T = eng.decision_times(extra_now=False)
    fwd = eng.forward(T)
    X = eng.score(T, fwd).join(fwd)
    Z = X.dropna(subset=["score", "y2"])
    Z = Z[Z.index.tz_convert(ET).dayofweek != 5]
    split = Z.index[int(len(Z) * 0.6)]
    print(f"decision points: {len(Z)}  ({Z.index[0]:%Y-%m-%d} -> {Z.index[-1]:%Y-%m-%d}), split at {split:%Y-%m-%d}")
    base = {"good": (Z.y2 > GOOD).mean() * 100, "bad": (Z.y2 < BAD).mean() * 100,
            "y2": Z.y2.mean(), "y1": Z.y1.mean()}
    res = {"generated": pd.Timestamp.now(tz=IST).isoformat(), "split": str(split), "thresholds": [TIER_RED, TIER_GREEN],
           "base_rates": base}
    out_md = ["# Backtest - trade / no-trade filter", "",
              f"Decision points: hourly, {len(Z)} samples from {Z.index[0]:%d %b %Y} to {Z.index[-1]:%d %b %Y}. "
              f"Train = before {split:%d %b %Y}, Test = after (untouched).", "",
              f"Base rates (all hours): next-4h net R at 1:2 = {base['y2']:+.3f}, at 1:1 = {base['y1']:+.3f}; "
              f"good 4h windows (>0R) = {base['good']:.1f}%, bad windows (< -0.25R) = {base['bad']:.1f}%.", ""]
    for name, part in (("ALL", Z), ("TRAIN", Z[Z.index < split]), ("TEST (out-of-sample)", Z[Z.index >= split])):
        t = tier_table(part)
        res[name] = json.loads(t.round(4).to_json(orient="index"))
        print(f"\n== {name}")
        print(t.round(3).to_string())
        out_md += [f"## {name}", "", md_table(t.round(3)), ""]
    # month-by-month stability: GREEN minus RED
    Z = Z.assign(month=Z.index.tz_convert(ET).strftime("%Y-%m"))
    m = Z.groupby(["month", "tier"]).y2.mean().unstack()
    m["GREEN-RED"] = m.get("GREEN") - m.get("RED")
    cnt = Z.groupby(["month", "tier"]).size().unstack().fillna(0).astype(int)
    m = m.join(cnt, rsuffix="_n")
    print("\n== by month (net R at 1:2)")
    print(m.round(3).to_string())
    out_md += ["## Month by month (next-4h net R at 1:2)", "", md_table(m.round(3)), ""]
    res["monthly"] = json.loads(m.round(4).to_json(orient="index"))
    wins = (m["GREEN-RED"] > 0).sum()
    total = m["GREEN-RED"].notna().sum()
    print(f"GREEN beat RED in {wins}/{total} months")
    out_md += [f"GREEN beat RED in **{wins}/{total}** months.", ""]
    # hour of day
    Z = Z.assign(hour_et=Z.index.tz_convert(ET).hour, hour_ist=Z.index.tz_convert(IST).strftime("%H:%M"))
    recent = Z[Z.index >= Z.index.max() - pd.Timedelta(days=182)]
    hrs = recent.groupby("hour_et").agg(ist=("hour_ist", lambda s: s.mode()[0]), n=("y2", "size"),
                                        net_R_1to2=("y2", "mean"), next4h_range=("fwd_range", "mean"),
                                        green_share=("tier", lambda s: (s == "GREEN").mean() * 100))
    out_md += ["## Hour of day (last 6 months, decision time in ET / IST)", "", md_table(hrs.round(3)), ""]
    res["hours"] = json.loads(hrs.round(4).to_json(orient="index"))
    # the weeks in question
    tl = Z.loc["2026-09-20":, ["score", "move", "edge", "trend_q", "tier", "y2", "y1", "fwd_range"]]
    tl = tl.assign(day=tl.index.tz_convert(ET).strftime("%a %d %b"))
    prime = tl[(tl.index.tz_convert(ET).hour >= 3) & (tl.index.tz_convert(ET).hour <= 13)]
    daily = prime.groupby("day", sort=False).agg(score=("score", "mean"), green=("tier", lambda s: (s == "GREEN").sum()),
                                                 amber=("tier", lambda s: (s == "AMBER").sum()), red=("tier", lambda s: (s == "RED").sum()),
                                                 realized_R_1to2=("y2", "mean"), realized_R_1to1=("y1", "mean"),
                                                 range4h=("fwd_range", "mean"))
    print("\n== 21 Sep -> now, London+NY hours (03-13 ET)")
    print(daily.round(2).to_string())
    out_md += ["## 21 Sep -> now (London + NY hours, 03:00-13:00 ET = 12:30-22:30 IST)", "",
               "Counts are hourly signals; realized columns are what happened in the 4h after each signal.", "",
               md_table(daily.round(2)), ""]
    res["recent_days"] = json.loads(daily.round(4).to_json(orient="index"))
    REPORTS_DIR.mkdir(exist_ok=True)
    (REPORTS_DIR / "backtest.md").write_text("\n".join(out_md))
    (REPORTS_DIR / "backtest.json").write_text(json.dumps(res, indent=1, default=str))
    X.to_pickle(REPORTS_DIR / "backtest_signals.pkl")
    print(f"\nwrote reports/backtest.md ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
