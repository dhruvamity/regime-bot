"""Draw the mapped structure for a window so events can be checked by eye against the guide.

python scripts/plot_bias.py 1h 2026-01-20 2026-03-30 [out.png] [--paxg]

Candles, plus: CHoCH point (orange step: a close beyond it flips the trend), confirmed HH/LL (blue step, only
after the inducement is taken), inducement (grey dots), and the events: CHoCH (big triangle), BOS (small
triangle), IDM taken (x), MSS (diamond). Background: green = bullish trend, red = bearish; the thin strip at the
bottom is the internal bias.
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gold import bias, session, store  # noqa: E402


def load(paxg: bool):
    if paxg:
        df = bias.paxg_clean(pd.read_parquet(Path(__file__).resolve().parent.parent / "data/paxg_1m.parquet"))
        return bias.frames(session.build_all(session.session_filter(df)))
    return bias.load_frames(store.connect())[0]          # exactly the live bot's frames


def plot(df, bars, E, a, b, out, title):
    m = (df.index >= a) & (df.index < b)
    d, B = df[m], bars[m]
    x = np.arange(len(d))
    fig, ax = plt.subplots(figsize=(16, 8), dpi=110)
    fig.patch.set_facecolor("#0b0c0f"); ax.set_facecolor("#0b0c0f")
    for k in range(len(d)):
        t = B.trend.iloc[k]
        if np.isfinite(t):
            ax.axvspan(k - .5, k + .5, color="#089981" if t > 0 else "#f23645", alpha=.06, lw=0)
    up = d.c >= d.o
    ax.vlines(x, d.l, d.h, color=np.where(up, "#089981", "#f23645"), lw=.8)
    ax.bar(x, (d.c - d.o).abs().clip(lower=1e-6), bottom=np.minimum(d.o, d.c), color=np.where(up, "#089981", "#f23645"), width=.7)
    ax.step(x, B.choch, where="mid", color="#ff9800", lw=1.4, label="CHoCH point")
    ax.step(x, B.ext, where="mid", color="#2962ff", lw=1.4, label="confirmed HH / LL")
    ax.plot(x, B.idm, ".", color="#9aa0aa", ms=2.5, label="inducement")
    pos = {t: k for k, t in enumerate(d.index)}
    for t, e in E.iterrows():
        if t not in pos:
            continue
        k = pos[t]; y = d.h.iloc[k] if e.dir < 0 else d.l.iloc[k]
        off = (d.h.max() - d.l.min()) * .015 * (1 if e.dir < 0 else -1)
        col = "#089981" if e.dir > 0 else "#f23645"
        if e.kind == "CHOCH":
            ax.plot(k, y + off * 2, "v" if e.dir < 0 else "^", color=col, ms=13, mec="white", mew=1)
            ax.annotate(f"CHoCH {e.level:.1f}", (k, y + off * 4), color="white", fontsize=8, ha="center")
        elif e.kind == "BOS":
            ax.plot(k, y + off, "v" if e.dir < 0 else "^", color=col, ms=7)
            ax.annotate("BOS", (k, y + off * 2.6), color=col, fontsize=7, ha="center")
        elif e.kind == "IDM":
            ax.plot(k, e.level, "x", color="#e0e0e0", ms=6)
        elif e.kind == "MSS":
            ax.plot(k, y + off, "D", color=col, ms=6, mec="white", mew=.6)
            ax.annotate("MSS", (k, y + off * 2.6), color=col, fontsize=7, ha="center")
    lo, hi = d.l.min(), d.h.max()
    ax.set_ylim(lo - (hi - lo) * .08, hi + (hi - lo) * .08)
    for k in range(len(d)):
        v = B.internal.iloc[k]
        if np.isfinite(v):
            ax.axvspan(k - .5, k + .5, ymin=0, ymax=.015, color="#089981" if v > 0 else "#f23645", lw=0)
    step = max(1, len(d) // 12)
    ax.set_xticks(x[::step]); ax.set_xticklabels([t.tz_convert("Asia/Kolkata").strftime("%d %b %H:%M") for t in d.index[::step]],
                                                   color="#b2b5be", fontsize=8, rotation=20)
    ax.tick_params(colors="#b2b5be"); ax.grid(color="#1a1c22")
    ax.set_title(title, color="white"); ax.legend(loc="upper left", facecolor="#14171c", labelcolor="white", fontsize=8)
    fig.tight_layout(); fig.savefig(out); plt.close(fig)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    tf, a, b = args[0], pd.Timestamp(args[1], tz="UTC"), pd.Timestamp(args[2], tz="UTC")
    out = args[3] if len(args) > 3 else f"bias_{tf}.png"
    fr = load("--paxg" in sys.argv)
    df = fr[tf]
    bars, E = bias.map_structure(df)
    plot(df, bars, E, a, b, out, f"{tf} structure  {a:%d %b %Y} → {b:%d %b %Y}")
    print(out)
