# Regime Bot: Gold Trade Filter + Telegram Alert Bot (XAUUSDT)

A local website and Telegram bot that answer one question for an intraday gold trader (1m / 5m / 15m entries,
1h / 4h / 1d bias): **is gold worth trading right now?**

* **Website** (`http://localhost:8787`): a live **✓ TRADE / ! SELECTIVE / ✕ NO TRADE** signal with reasons. It also
  shows the 1h/4h/1d bias, live LTF structure, today vs last week, best hours of the day, a 6-week strip and a 6-month
  calendar of daily signals, plus backtest and data-accuracy reports.
* **Telegram bot**: bold alerts when trade conditions switch on or off and when the 1h trend shifts, plus 4h/1d bias
  changes and a daily brief. It also tracks **quiet mode**: when the last 2 sessions moved less than 80% of a normal
  day, it warns you to cap targets at $9 (1:3 on a $3 stop). Commands: `/status`, `/bias`, `/mode` and more.
* **Research scripts**: a walk-forward backtest of the signal, a backtest of every alert, a deep week-vs-history
  report, and a check that every timeframe matches the exchange.

Everything runs from one Python process. Data comes from the **Binance USD-M `XAUUSDT` perpetual** (free public API,
no key needed), filtered to **forex.com XAUUSD trading hours**.

> Not financial advice. The backtests below show the filter shifts the odds modestly; it is not a crystal ball.

---

## 1. Requirements

| | |
|---|---|
| OS | macOS or Linux. Windows works for the Python parts; use `python` and `.venv\Scripts\activate`, and skip the macOS autostart script. |
| Python | **3.10 or newer** (the code uses `X \| None` type hints). Tested on Python 3.14.5 with pandas 3.0, numpy 2.4, fastapi 0.139, uvicorn 0.51, websockets 16, aiohttp 3.14. |
| Network | `fapi.binance.com` (REST) and `fstream.binance.com` (websocket) for candles. **Binance blocks US IP addresses**, so use a non-US connection or server. `api.telegram.org` for the bot. The dashboard page loads its chart and Markdown libraries from `unpkg.com` and `cdnjs.cloudflare.com`. |
| Disk | About 30 MB (the 1m candle database is ~25 MB and grows ~2–3 MB a month). |

No API keys are needed for market data. The only secret is your Telegram bot token, which is optional.

---

## 2. First-time setup

Run everything **from the project folder** (the server module path `server.app:app` is relative to it).

```bash
cd ~/Downloads/regime-bot
```

**2.1 Create a virtual environment and install dependencies**

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

Every later command assumes the venv is active. In a new terminal, run `source .venv/bin/activate` again.

**2.2 Download the full candle history (about 1 minute)**

```bash
python scripts/backfill.py
```

This downloads every 1-minute XAUUSDT candle since the contract listed (11 Dec 2025) into `data/candles.db`:
about 440,000 candles, ~25 MB. Re-running it only adds what's missing.

**2.3 Build the reports (about 10 seconds)**

```bash
python scripts/backtest.py
```

```bash
python scripts/analyze_week.py
```

```bash
python scripts/backtest_alerts.py
```

```bash
python scripts/backtest_regime.py
```

```bash
python scripts/verify_candles.py
```

The website shows these reports and the bot quotes their numbers in alert messages. The last script should end with
`ALL CHECKS PASSED`.

**2.4 Start the website + bot**

```bash
python -m uvicorn server.app:app --host 127.0.0.1 --port 8787
```

Open **http://localhost:8787**. The first page load after a start takes a few seconds while the signal is computed.
Stop the server with `Ctrl+C`.

> **Shortcut:** you can skip 2.2 and 2.3. On first start the server downloads the history and builds the backtest,
> week and alert reports itself, so the page is ready after about 80 seconds. Only the candle-accuracy report
> (`verify_candles.py`) is never built automatically.

---

## 3. Telegram bot (optional)

Without a token everything still works: alerts are computed and appended to `data/alerts.log`, and the website shows
"Telegram not set up yet".

**3.1 Create the bot**

1. In Telegram, open **@BotFather**, send `/newbot`, choose a name and username, and copy the token.
2. Create your settings file:

```bash
cp .env.example .env
```

3. Open `.env` and paste the token after `TELEGRAM_BOT_TOKEN=`. Never share or commit this file (`.gitignore`
   already excludes it).
4. Restart the server (`Ctrl+C`, then the command from 2.4).
5. Open your bot in Telegram and send **`/start`**.

**Who can use it:** if `TELEGRAM_ALLOWED_CHATS` is empty, the **first chat that sends `/start` becomes the owner**
and every other chat gets "⛔ This bot is private". The owner is stored in `data/telegram.json`. Delete that file and
restart to hand the bot to a different chat. To allow several chats, list their numeric chat ids in
`TELEGRAM_ALLOWED_CHATS` (comma-separated).

**3.2 Settings in `.env`**

| Variable | Default | Meaning |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | *(empty)* | Bot token from @BotFather. Empty means the bot is off and alerts are only logged. |
| `TELEGRAM_ALLOWED_CHATS` | *(empty)* | Comma-separated chat ids. Empty means first `/start` = owner. |
| `QUIET_HOURS_IST` | `01:00-08:00` | Alerts in this IST window arrive **silently** (no sound). Wraps past midnight if needed. Empty = always loud. |
| `BRIEF_TIME_IST` | `12:00` | Time (IST, HH:MM) of the weekday daily brief. Empty = off. |
| `TELEGRAM_API_BASE` | `https://api.telegram.org` | For testing against a mock Telegram server only. |
| `GOLD_STATE_DIR` | `data/` | Where bot/alert state and `alerts.log` live. For testing only. |

Real environment variables override `.env`. Changes take effect after a restart.

**3.3 What it sends**

| Message | When | Sound |
|---|---|---|
| 🟢🟢 **TRADE CONDITIONS ON** | Score ≥ 58 for two consecutive 15-minute checks | loud |
| 🔴 **STOP TRADING** | Score < 32 for two consecutive 15-minute checks | loud |
| 🟡 Tradable (selective) / downgraded | Score moves into the 32–58 band | silent |
| 🔄 **1H TREND SHIFT** | A closed 1h candle breaks the last swing high/low (BOS/CHoCH), tagged with/against the 4h trend | loud |
| 🔄 **4H / 1D BIAS CHANGE** | The same on 4h or 1d candles (information, not an entry signal) | loud |
| 🌙 **QUIET MODE ON** / ☀️ OFF | The 2-session average daily range drops below 80% of the 60-session median (off again at 90%). Checked once per closed session | loud |
| ⚠️ Feed stalled / ✅ restored | No candles for 3 minutes during market hours, and when they return | loud |
| ☀️ Daily brief | `BRIEF_TIME_IST` on weekdays | loud |
| 🔁 Bot restarted | When the server restarts and someone is subscribed | silent |

Each alert includes the score, price, structure trend on 15m/1h/4h/1d, the time in IST and ET, and the backtested
hit rate for that alert type, read from `reports/alert_stats.json`. For trend-shift alerts the hit rate is left out
when the backtest has fewer than 15 examples. Expect roughly **8 loud alerts a week**, plus the weekday brief.

**3.4 Commands**

| Command | Reply |
|---|---|
| `/start` | Subscribe (or resume) and show the current signal |
| `/status` | Signal right now with reasons |
| `/bias` | Trend on 15m / 1h / 4h / 1d (market structure + EMA20/50 + ADX) |
| `/brief` | The daily brief, right now |
| `/mode` | Quiet mode check: last 3 daily ranges vs normal, the target cap, and the backtest behind it |
| `/alerts` | The last 10 alerts sent |
| `/stop` | Pause alerts for this chat |

---

## 4. Running 24/7

The server must keep running for the bot to watch candles. Use one of these options.

**macOS (LaunchAgent).** It starts at login, restarts if it crashes, and keeps the Mac awake while plugged in via
`caffeinate -s`. **Activate the venv first** so the agent uses the venv's Python:

```bash
source .venv/bin/activate
```

```bash
scripts/install_autostart.sh
```

Logs go to `data/server.log`. To remove it:

```bash
launchctl unload ~/Library/LaunchAgents/com.gold.tradefilter.plist && rm ~/Library/LaunchAgents/com.gold.tradefilter.plist
```

A MacBook with the lid closed and no external display still sleeps, and while it sleeps there are no alerts.

**Linux server (systemd).** This is the most reliable option for true 24/7 on any small VPS outside the US.
Copy the folder, do the setup in section 2, then edit `deploy/gold-filter.service`:

* set `User`
* set `WorkingDirectory` to the project folder
* point `ExecStart` at your venv's Python, e.g. `/home/ubuntu/regime-bot/.venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port 8787`

Then install and start it:

```bash
sudo cp deploy/gold-filter.service /etc/systemd/system/
```

```bash
sudo systemctl enable --now gold-filter
```

**Viewing the dashboard from your phone.** The server listens on `127.0.0.1` only. You can start it with
`--host 0.0.0.0` to reach it on your local network, but the site has **no login**, so don't expose that port to the
internet. Telegram works without opening any port.

---

## 5. What the server does while running

* **On start:** downloads any candles missed while it was off. If any report is missing or older than 20 hours, it
  rebuilds the backtest, week and alert reports. The first start on an empty folder downloads the whole history.
* **Live feed:** subscribes to `wss://fstream.binance.com/market/ws/xauusdt@kline_1m` and stores every closed 1m
  candle. Binance moved futures streams under `/market`; the old `/ws` path connects but sends nothing. On a
  disconnect it reconnects with backoff and back-fills the gap over REST.
* **Accuracy:** every 5 minutes it re-downloads the last 2 hours over REST and overwrites them, so stored candles
  always equal the exchange's final values.
* **Signal:** recomputed on every closed in-session 1m candle (~4 s), then pushed to the browser over a websocket.
  Alerts are checked on the same pass, at most once per 15-minute slot and per closed 1h/4h/1d candle.
* **No repeats:** alert state lives in `data/alert_state.json`. After a restart the bot neither re-sends old alerts
  nor sends anything older than 30 minutes.
* **Daily:** at 17:00 ET (forex.com daily close) it rebuilds the backtest, week, alert and quiet-mode reports.
* **Market hours:** Binance trades XAUUSDT 24/7, but forex.com gold doesn't. Candles outside forex.com hours are
  ignored: Fri 17:00 → Sun 18:00 ET, the 17:00–18:00 ET daily break, Christmas, New Year and Good Friday, plus
  early closes on US holidays. When the market is closed the site doesn't block; it shows the reading from the final
  in-session candle and the next open time.

---

## 6. The dashboard, section by section

| Section | What it shows |
|---|---|
| Signal right now | TRADE / SELECTIVE / NO TRADE, the 0–100 score (65% movement + 35% recent edge), reasons, and what would lift a RED reading |
| Higher-timeframe bias | 1h / 4h / 1d EMA20/50 direction, price vs EMA20, ADX strength (closed candles only) |
| Price + hourly signal | Session candles on 1m/5m/15m/1h with a live forming candle, and the hourly score as coloured bars (last ~8 days) |
| LTF structure (last 4h) | Efficiency, Choppiness, wick share, follow-through and ATR on 1m/5m/15m, with each value's percentile vs 6 months. Context only, not a forecast. |
| Today vs last week | Today's session so far vs the same number of hours of last week's sessions and of every session in 6 months |
| When gold usually moves | Each hour of the day (your local time), coloured by how trades went in the 4h after it over the last 6 months |
| Last 6 weeks / Last 6 months | Each trading day coloured by its average London+NY (03–13 ET) score. Hover a day for its range and realised results. The table shows what green, amber and red days actually delivered. |
| How reliable is this? | Walk-forward backtest by signal tier (test / train / all) |
| Last week in context | How the most recent full week ranks against the previous 6 months |
| Telegram alerts | Bot connection status and the last alerts |
| Reports | Week report, backtest report, alert backtest and candle-accuracy report, rendered from `reports/*.md` |

---

## 7. Scripts

| Command | Takes | Output | What it does |
|---|---|---|---|
| `python scripts/backfill.py` | ~1 min first time | `data/candles.db` | Downloads or tops up all 1m candles |
| `python scripts/backtest.py` | ~3 s | `reports/backtest.md/.json`, `reports/backtest_signals.pkl` | Hourly walk-forward test of the signal. First 60% of history = train, the rest = untouched test |
| `python scripts/analyze_week.py [YYYY-MM-DD]` | ~3 s | `reports/week_report.md/.json` | A week (give its Monday; default = last full week) vs the previous 3 weeks and 6 months, on every timeframe, plus today vs last week |
| `python scripts/backtest_alerts.py` | ~3 s | `reports/alerts_backtest.md/.json`, `reports/alert_stats.json` | Replays every alert through the bot's own code. **`alert_stats.json` is what the bot quotes in messages** |
| `python scripts/backtest_regime.py` | ~70 s | `reports/regime_backtest.md/.json` | Replays the quiet-mode flag session by session and judges the next evening (17:00–24:00 IST). **The bot quotes these numbers in `/mode` and quiet-mode alerts** |
| `python scripts/verify_alerts.py [--days 30]` | ~30 min | `reports/alert_check.md` | Replays the live bot's code at every 15-minute candle close (only the candles it would have had), with a restart and a 3-hour outage, and checks every alert and quiet-mode flip against the backtests: nothing missing, extra, duplicated, late or stale. Exit code 1 on any mismatch |
| `python scripts/verify_candles.py` | ~3 s | `reports/candle_check.md` | Checks for missing minutes; stored 1m vs Binance; our 5m/15m/1h vs Binance native klines; our 4h/1d vs Binance 1h aggregated over the same windows. Exit code 1 on any mismatch |

## 8. HTTP endpoints

| Endpoint | Returns |
|---|---|
| `GET /` | The dashboard |
| `GET /api/state` | Everything the dashboard shows, as JSON |
| `GET /api/candles?tf=5m&n=400` | Session candles (`tf` = 1m, 5m, 15m, 1h, 4h, 1d; `n` ≤ 2000) |
| `GET /reports/{name}` | `week_report.md`, `backtest.md`, `alerts_backtest.md`, `regime_backtest.md` or `candle_check.md` |
| `GET /healthz` | Feed status, Telegram status, whether a signal exists, whether the feed is stalled |
| `WS /ws` | Live pushes: `state` on every recompute, `tick` (live price) about once a second |

---

## 9. How the signal and alerts were built (and how well they hold up)

Numbers below are from the reports generated on 12 Oct 2026. The reports regenerate daily, so check them for
current figures.

**The signal.** 10 months of 1m data was tested at every hour, using only information available at that moment.
* Whether the next hours trend or chop **could not** be predicted from past candles (rank correlation ≈ 0).
* How much gold **will move** could be predicted, because quiet and busy periods cluster. Net LTF results are clearly
  worse when movement is low relative to normal for that hour.
* So the score is **65% movement vs normal + 35% how recent trades in the 1h-bias direction resolved**.
  Tiers: < 35 NO TRADE, 35–55 SELECTIVE, ≥ 55 TRADE.
* **Results (test period, after 22 Jun 2026):** next-4h results averaged −0.18R per entry in NO TRADE hours vs about
  −0.10R in TRADE and SELECTIVE hours. TRADE beat NO TRADE in **9 of 10 months**, but TRADE and SELECTIVE were about
  equal in the test period, so treat **RED as the dependable part**.
* **Reading R figures:** they're for mechanical entries on every candle (1-ATR stop, $0.40 cost), so all are negative.
  Compare between tiers, not to zero.
* **1:1 targets:** 1:1 never beat 1:2 in any movement × chop bucket, which is why the middle tier says "selective,
  half size" rather than "1:1 only".

**The alerts.** Rules were chosen on 5 Jan – 12 Apr 2026 and tested on 13 Apr – today.
* 🟢 TRADE-ON alerts: the next 4 hours were better than median **64%** of the time (55% in the selection period).
  Coin flip = 50%.
* 🔴 STOP alerts: the next 4 hours were worse than median **55%** of the time (59%).
* 🟡 "Selective ON" alerts were below 50% in both periods, which is why they're silent.
* 1h structure shifts: price reached +1R before −1R **54%** of the time vs 48% for random entries, and 1:2 trades
  averaged **+0.11R** vs −0.04R. With-4h shifts: 63% / +0.19R. Against-4h: 47% / +0.05R. That split reversed in
  the selection period, so both kinds are sent.
* 15m trend shifts were coin flips under every definition tested (structure, EMA, Supertrend, Donchian), so they're
  not alerted. 4h/1d shifts are too rare (≤ 20 in 6 months) to prove an edge.
* The live bot sends exactly the alerts the backtest replays: `scripts/verify_alerts.py` replays the live code every
  15 minutes for 30 days, with a restart and a 3-hour outage (69 of 69 alerts on 14 Oct 2026; none missing,
  duplicated, late or leaked after the outage).
* What the states mean in practice (last 6 months, from each 15-minute check): in TRADE, a $9 move happened within an
  hour 79% of the time, in SELECTIVE 67%, in STOP 62% (TRADE vs STOP p=0.004), and the next-4h range was $38.6 /
  $36.3 / $32.0. So the tiers sort **how much gold moves**. They don't significantly sort the direction-following
  result (next-4h 1:2 R −0.06 vs −0.17, p=0.33), and quiet mode and STOP agree: in quiet mode the state was STOP 94%
  of the time and never TRADE.

**Quiet mode** (`gold/regime.py`, added 14 Oct 2026, rule changed the same day). Average daily range of the last 2
complete sessions divided by the median of the last 60. Below 0.80 = QUIET; it switches back at 0.90, so a reading
hovering near the line doesn't flip every day.
* **Why 2 sessions at 0.80/0.90.** The first version (3 sessions, 0.75/0.80) caught too few quiet days. Settings were
  compared on Sep 2023 – Jun 2025 and confirmed on Jul 2025 – Oct 2026 (PAXG before Dec 2025, then the perp). The new
  rule flagged 34–43% of the sessions that turned out quiet (old: 19–31%). Of the sessions it flagged, about 46% were
  quiet vs a 20–23% base rate, the same precision as before. It caught all 18 quiet stretches since Sep 2023
  (3+ sessions in a row under 80% of normal), usually 1–2 sessions in. The old rule caught 15, usually 2–3 sessions in.
* **On the bot's own data** (Mar–Oct 2026, 43 quiet sessions): after a QUIET reading the next 17:00–24:00 IST evening
  was quiet (movement under 80% of normal) **40%** of the time vs 21% after a NORMAL one. From any evening 5m close,
  $16.5 was reached within an hour 40% of the time vs 45%, and $9 75% vs 82%. The old rule's split on the same months
  was 48% vs 22% on fewer days (25), so the change trades a little precision for coverage.
* What it does **not** show: random entries aiming at $16.5 did not lose more in quiet mode (the stop gets hit less
  often too). Since Sep 2023 random entries ranked 1:2 > 1:3 > 1:5.5 by a few hundredths of R in both modes alike.
  The $9 cap is a hit-rate rule for a quiet market, not a proven expectancy gain. On your own
  entries 1:3 was the best target in normal markets; too few of your trades fell in quiet mode to test the cap.
* It describes today, not the week: quiet stretches are short, and the 3 sessions after a QUIET ON alert averaged a
  normal range (1.02× since Sep 2023). Read the mode as "today is likely quieter than usual".
* Alerts: about 12–15 flips per 100 sessions since 2023, and 33 in the bot's 156 sessions (Mar–Oct 2026), so roughly
  one every 5 trading days in choppy months. Each flip is sent once, loud, at the session close (02:30 IST in summer,
  so it usually lands in your quiet hours). The current mode is also in `/status`, `/mode` and the daily brief.
* Verified on 14 Oct 2026 with `scripts/verify_alerts.py`: every flip over 120 days (19 with this rule) was sent
  once, at the close of the session that caused it. That check caught and fixed a bug where 13:29 ET was treated as
  a session close on every day, not only on early-close days.

**Candle accuracy** (`reports/candle_check.md`): no missing minutes in 30 days. Stored 1m and our 5m/15m/1h are
identical to Binance's own candles, and our forex.com-anchored 4h/1d match Binance 1h data aggregated over the same
windows.

---

## 10. Configuration you might change

| What | Where |
|---|---|
| Cost per trade used in all R figures (`COST_USD = 0.40`) | `gold/config.py` |
| Market holidays (`CLOSED_SESSION_DATES`, `EARLY_CLOSE_DATES`). **Only filled in through Dec 2026; add 2027 dates.** | `gold/config.py` |
| Session hours (18:00 → 17:00 ET) | `gold/config.py` |
| Signal tiers (`TIER_RED = 35`, `TIER_GREEN = 55`), score weights | `gold/signal.py` |
| Alert thresholds (`VIABLE_ON/OFF = 38/32`, `GREEN_ON/OFF = 58/52`, `CONFIRM_SLOTS = 2`), shift timeframes | `gold/alerts.py` |
| Quiet mode (`QUIET_BELOW = 0.80`, `QUIET_EXIT = 0.90`, `LOOKBACK = 2`, `NORMAL_WINDOW = 60`, `QUIET_TARGET_CAP = 9`) | `gold/regime.py` |
| Port | the `--port` in your start command, `scripts/install_autostart.sh` and `deploy/gold-filter.service` |

After changing signal, alert or quiet-mode rules, re-run `scripts/backtest.py`, `scripts/backtest_alerts.py` and
`scripts/backtest_regime.py` and check the
results before trusting them. Note that `backtest_alerts.py` uses **fixed dates**: selection 5 Jan – 12 Apr 2026,
test 13 Apr 2026 → today (`START` and `CUT` at the top of the script).

---

## 11. Files

```
regime-bot/
├── README.md
├── requirements.txt            Python dependencies
├── .env.example                Template for .env (Telegram token + settings)
├── .gitignore                  Ignores .env, data/, caches
├── .claude/launch.json         Launch config used by the Claude desktop app's preview pane
├── deploy/gold-filter.service  systemd unit for a Linux server
├── gold/                       The engine (shared by server, bot and scripts)
│   ├── config.py               Symbol, Binance endpoints, session hours, holidays, cost, timeframes
│   ├── env.py                  Reads .env (environment variables win)
│   ├── store.py                SQLite store of 1m candles (WAL mode)
│   ├── fetch.py                Binance REST backfill (rate-limit aware, closed candles only)
│   ├── session.py              forex.com session filter; builds 5m/15m/1h, and 4h/1d anchored to 18:00 ET
│   ├── metrics.py              Efficiency, Choppiness, wick, variance ratio, ATR, ADX, vectorised trade simulator
│   ├── signal.py               The trade/no-trade engine; identical for backtest and live
│   ├── report.py               Day/week tables, week verdicts, time-matched "today vs last week"
│   ├── live.py                 Builds the dashboard state (incl. 6-week / 6-month daily views)
│   ├── trend.py                Trend definitions (structure, EMA, Supertrend, Donchian), 1m follow-through tester
│   ├── alerts.py               Alert rules + Telegram message formatting
│   ├── alert_runner.py         Persistent live wrapper (no duplicates or stale alerts after restarts)
│   ├── regime.py               Quiet mode: 2-session range vs normal, target cap, bot texts
│   ├── telegram.py             Telegram client: retrying sender, command polling, owner-only access
│   └── util.py                 Markdown table helper
├── scripts/
│   ├── backfill.py             Download/top up candles
│   ├── backtest.py             Signal backtest
│   ├── analyze_week.py         Week vs history report
│   ├── backtest_alerts.py      Alert backtest + stats the bot quotes
│   ├── backtest_regime.py      Quiet-mode backtest + stats the bot quotes
│   ├── verify_candles.py       Candle accuracy check
│   └── install_autostart.sh    macOS LaunchAgent installer (zsh)
├── server/
│   ├── app.py                  FastAPI app: live feed, recompute loop, Telegram, watchdog, endpoints
│   └── static/index.html       The dashboard (single file)
├── data/                       Created at runtime (not committed)
│   ├── candles.db (+ -wal, -shm)   All 1m candles
│   ├── alert_state.json        Alert engine state
│   ├── telegram.json           Bot owner, subscribed chats, update offset (only once a token is set)
│   ├── alerts.log              Every alert ever generated (JSON lines)
│   └── server.log              Only when run by the macOS LaunchAgent
└── reports/                    Generated by the scripts and by the server daily
    ├── backtest.md / .json, backtest_signals.pkl
    ├── week_report.md / .json
    ├── alerts_backtest.md / .json, alert_stats.json
    ├── regime_backtest.md / .json
    └── candle_check.md
```

---

## 12. Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'server'` | Run uvicorn from the project folder |
| `ModuleNotFoundError` for pandas, aiohttp, etc. | Activate the venv (`source .venv/bin/activate`), then `pip install -r requirements.txt` |
| Page doesn't load for a minute on first start | Normal: it's downloading the full history (~80 s). Watch the terminal for `startup backfill` and `signal ...` |
| `address already in use` | Another copy is running (perhaps the LaunchAgent). Stop it, or use another `--port` |
| Feed dot red / "reconnecting", or HTTP 451 in the log | Binance isn't reachable from your network (Binance blocks US IPs). Use a non-US connection or server. Gaps are back-filled automatically once it reconnects |
| Bot says "⛔ This bot is private" | Another chat already owns it. Delete `data/telegram.json` and restart, or add your chat id to `TELEGRAM_ALLOWED_CHATS` |
| No Telegram messages | Check `GET /healthz` → `telegram.status`. Make sure you sent `/start`, and that `.env` has the token and the server was restarted. Messages during `QUIET_HOURS_IST` arrive without sound |
| Chart area is empty | The chart library loads from a CDN, so check your internet connection. The signal still works |
| "Candle accuracy" tab says not generated | Run `python scripts/verify_candles.py` |
| Want to start completely fresh | Stop the server, delete `data/` and `reports/`, then follow section 2 again. All history re-downloads in about a minute |
| A holiday in 2027+ shows strange candles | Add the date to `CLOSED_SESSION_DATES` / `EARLY_CLOSE_DATES` in `gold/config.py` |
