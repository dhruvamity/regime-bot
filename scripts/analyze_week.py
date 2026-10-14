"""Deep comparison of a trading week vs the previous 3 weeks and the last 6 months.

Usage: python3 scripts/analyze_week.py [YYYY-MM-DD of the Monday]   (default: last full week)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from gold import metrics, report, session, store  # noqa: E402
from gold.config import BASELINE_DAYS, IST, REPORTS_DIR  # noqa: E402
from gold.signal import Engine  # noqa: E402
from gold.util import md_table  # noqa: E402

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 40)
pd.set_option("display.max_rows", 200)


def tf_compare(eng: Engine, D: pd.DataFrame, wk, prev_wks, base_start) -> pd.DataFrame:
    """Per-timeframe structure + outcome comparison."""
    h1 = metrics.bar_features(eng.tfs["1h"])
    h1.index = h1.index + pd.Timedelta("60min")
    rows = []
    for tf in ("1m", "5m", "15m", "1h"):
        f = eng.bar[tf] if tf != "1h" else h1
        wkey = session.week_key(f.sdate.values)
        wkey.index = f.index
        for k in ("er", "chop", "wick", "vr", "atr", "y2", "y1"):
            if k in ("y2", "y1") and tf == "1h":
                continue
            if k == "vr":
                g = f.groupby(wkey.values)
                ser = g["rk"].var() / (metrics.VR_K * g["r"].var())
            else:
                ser = f[k].groupby(wkey.values).mean()
            base = ser[(ser.index < wk) & (ser.index >= base_start)]
            rows.append({"tf": tf, "metric": report.LABELS[k], "key": k,
                         "last_week": ser.get(wk, np.nan),
                         "prev_3_weeks": ser.reindex(prev_wks).mean(),
                         "median_6m": base.median(),
                         "pct_vs_6m": report.pct_rank(base, ser.get(wk, np.nan))})
    return pd.DataFrame(rows)


def main():
    con = store.connect()
    eng = Engine(store.load(con))
    D = report.daily_table(eng)
    W = report.weekly_table(D)
    full = W[W.days >= 4]
    if len(sys.argv) > 1:
        wk = pd.Timestamp(sys.argv[1]).date()
    else:
        wk = full.index[-1] if full.index[-1] < session.week_key([D.index[-1].date()]).iloc[0] else full.index[-2]
    prev_wks = [w for w in full.index if w < wk][-3:]
    base_start = (pd.Timestamp(wk) - pd.Timedelta(days=BASELINE_DAYS)).date()
    base = full[(full.index < wk) & (full.index >= base_start)]
    md = [f"# Gold (XAUUSDT) week of {wk:%d %b %Y} - deep comparison", "",
          f"Generated {pd.Timestamp.now(tz=IST):%d %b %Y %H:%M} IST. Data: Binance XAUUSDT 1m, forex.com session hours only "
          f"(Sun 18:00 ET -> Fri 17:00 ET). Baseline = {len(base)} weeks from {base_start:%d %b %Y}.", ""]

    # 1. per timeframe
    tfc = tf_compare(eng, D, wk, prev_wks, base_start)
    print(f"\n=== Week {wk} vs previous 3 weeks {prev_wks} vs 6-month median ===")
    print(tfc.drop(columns="key").round(3).to_string(index=False))
    md += ["## 1. Every timeframe: last week vs previous 3 weeks vs 6 months", "",
           "pct_vs_6m = percentile of last week among the previous 6 months of weeks (0 = lowest, 100 = highest).", "",
           md_table(tfc.drop(columns="key").set_index(["tf"]).round(3)), ""]

    # 2. HTF / movement picture
    cols = ["days", "week_range", "net_move", "avg_day_range", "overlap", "path_eff_1h", "atr_5m", "er_15m", "chop_15m",
            "wick_5m", "vr_15m", "y2_ltf", "y1_ltf"]
    show = full.loc[[*prev_wks, wk], cols]
    med = base[cols].median().rename("6m median")
    show = pd.concat([show, med.to_frame().T])
    print("\n=== Weekly movement & structure ===")
    print(show.round(3).to_string())
    md += ["## 2. Movement and structure, week by week", "",
           "overlap = share of each day's range inside the previous day's range (high = going nowhere). "
           "path_eff_1h = |net move| / total 1h path. y2/y1_ltf = average net R of 1:2 / 1:1 trend-following entries "
           "on 1m+5m+15m in the 1h-bias direction (after a $0.40 cost per trade).", "",
           md_table(show.round(3)), ""]
    verdict = report.week_verdict(W, wk)

    # 3. day by day
    days = D[(D.index >= pd.Timestamp(prev_wks[0])) & (D.index < pd.Timestamp(wk) + pd.Timedelta(days=7))]
    dcols = ["range", "overlap", "body", "path_eff_1h", "atr_1m", "atr_5m", "er_5m", "chop_5m", "wick_5m", "vr_5m",
             "y2_1m", "y2_5m", "y2_15m", "y1_5m"]
    dd = days[dcols].copy()
    dd.index = dd.index.strftime("%a %d %b")
    print("\n=== Day by day ===")
    print(dd.round(3).to_string())
    md += ["## 3. Day by day (last 4 weeks)", "", md_table(dd.round(3)), ""]

    # 4. ranking + frequency
    rk = full[(full.index >= base_start) & (full.index <= wk)]
    order = rk.avg_day_range.rank()
    print(f"\nLast week avg daily range ${full.loc[wk, 'avg_day_range']:.1f}: rank {int(order[wk])} of {len(rk)} (1 = quietest)")
    bad = report.bad_week_mask(full)
    bad6 = bad[(bad.index >= base_start) & (bad.index < wk)]
    like = [str(w) for w, v in bad6.items() if v is True]
    allbad = [str(w) for w, v in bad.items() if v is True]
    d_base = D[(D.index >= pd.Timestamp(base_start)) & (D.index < pd.Timestamp(wk))]
    lw_days = D[(D.index >= pd.Timestamp(wk)) & (D.index < pd.Timestamp(wk) + pd.Timedelta(days=7))]
    thr_range = lw_days.range.mean()
    quiet_days = d_base[(d_base.range <= thr_range)]
    print(f"'Like last week' weeks in prior 6 months: {len(like)} of {bad6.notna().sum()} -> {like}")
    print(f"All flagged weeks in full history: {allbad}")
    print(f"Days in prior 6 months with range <= last week's average (${thr_range:.0f}): {len(quiet_days)} of {len(d_base)}")
    md += ["## 4. How often does a week like this happen?", "",
           f"* Last week's average daily range was **${full.loc[wk, 'avg_day_range']:.1f}**: rank **{int(order[wk])} of {len(rk)}** weeks "
           f"in the last 6 months (1 = quietest). 6-month median: ${base.avg_day_range.median():.1f}.",
           f"* Definition of 'like last week': average daily range in the bottom 20% of the trailing 6 months **and** "
           f"below-median LTF trend-following results.",
           f"* Weeks matching in the prior 6 months: **{len(like)} of {int(bad6.notna().sum())}** ({', '.join(like) or 'none'}).",
           f"* All matching weeks in the full 10-month history: {', '.join(allbad) or 'none'}.",
           f"* Individual days in the prior 6 months with a range at or below last week's average (${thr_range:.0f}): "
           f"**{len(quiet_days)} of {len(d_base)}** ({len(quiet_days) / max(1, len(d_base)) * 100:.0f}%).", ""]

    # 5. today vs last week (time-matched)
    tv = report.today_vs_last_week(eng)
    keys = ["range", "net", "atr_1m", "atr_5m", "er_1m", "er_5m", "er_15m", "chop_5m", "wick_5m", "vr_5m", "y2_1m", "y2_5m",
            "y1_1m", "y1_5m"]
    cmp = pd.DataFrame({
        "today": tv["table_today"].iloc[0][keys] if len(tv["table_today"]) else np.nan,
        "last_week_avg": tv["table_last_week"][keys].mean(),
        "last_6m_median": tv["table_6m"][keys].median(),
    })
    cmp["today_pct_vs_6m"] = [report.pct_rank(tv["table_6m"][k], cmp.loc[k, "today"]) for k in keys]
    print(f"\n=== Today {tv['today']} vs last week, first {tv['elapsed_hours']}h of each session ===")
    print(cmp.round(3).to_string())
    lw_tbl = tv["table_last_week"][keys].copy()
    lw_tbl.index = pd.to_datetime(lw_tbl.index).strftime("%a %d %b")
    md += [f"## 5. Today ({tv['today']}) vs last week, same {tv['elapsed_hours']}h into each session", "",
           md_table(cmp.round(3)), "", "Last week's sessions at the same point:", "", md_table(lw_tbl.round(3)), ""]

    REPORTS_DIR.mkdir(exist_ok=True)
    (REPORTS_DIR / "week_report.md").write_text("\n".join(md))
    js = {"week": str(wk), "prev_weeks": [str(w) for w in prev_wks], "verdict": verdict,
          "rank_quietest": int(order[wk]), "weeks_in_rank": int(len(rk)), "like_last_week_6m": like,
          "like_last_week_all": allbad, "quiet_days": int(len(quiet_days)), "base_days": int(len(d_base)),
          "today_vs_last_week": json.loads(cmp.round(4).to_json(orient="index"))}
    (REPORTS_DIR / "week_report.json").write_text(json.dumps(js, indent=1, default=str))
    print("\nwrote reports/week_report.md")


if __name__ == "__main__":
    main()
