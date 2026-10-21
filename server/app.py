"""Live gold trade-filter server + Telegram alert bot.

* keeps data/candles.db up to date: REST backfill on start, Binance websocket for live 1m
  candles, and every 5 minutes re-downloads the last 2 hours over REST and overwrites them, so
  stored candles always equal the exchange's final candles
* recomputes the signal (same engine as the backtest) on every closed in-session candle
* runs the alert rules (gold/alerts.py, same code as scripts/backtest_alerts.py) and sends
  them to Telegram; pushes state + live price ticks to the browser over /ws

Run:  python3 -m uvicorn server.app:app --port 8787      (from the project root)
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import pandas as pd
import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gold import alerts, env, fetch, live, regime, session, smc_alerts, store  # noqa: E402
from gold.alert_runner import AlertRunner  # noqa: E402
from gold.config import DATA_DIR, ET, IST, REPORTS_DIR, WS_URL  # noqa: E402
from gold.telegram import Telegram  # noqa: E402

log = logging.getLogger("gold")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
STATIC = Path(__file__).resolve().parent / "static"
STATE_DIR = Path(env.load().get("GOLD_STATE_DIR") or DATA_DIR)   # alert/telegram state (tests use a temp dir)
ALERT_LOG = STATE_DIR / "alerts.log"
STALL_SECONDS = 180


class Hub:
    def __init__(self):
        self.clients: set[WebSocket] = set()
        self.state: dict | None = None
        self.tick: dict | None = None
        self.tick_sent: dict | None = None
        self.feed = {"status": "starting", "since": time.time(), "last_msg": None}
        self.dirty = asyncio.Event()
        self.con = store.connect()  # writer connection (event loop only)
        self.cfg = env.load()
        self.runner = AlertRunner(STATE_DIR / "alert_state.json")
        self.ctx: dict = {}
        self.stalled = False
        token = self.cfg.get("TELEGRAM_BOT_TOKEN", "")
        self.tg = Telegram(token, STATE_DIR / "telegram.json", self.cfg.get("TELEGRAM_ALLOWED_CHATS", ""),
                           self.cfg.get("TELEGRAM_API_BASE") or "https://api.telegram.org") if token else None

    async def broadcast(self, msg: dict):
        data = json.dumps(msg, default=str)
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    def quiet_now(self) -> bool:
        q = self.cfg.get("QUIET_HOURS_IST", "")
        if "-" not in q:
            return False
        a, b = [x.strip() for x in q.split("-", 1)]
        now = pd.Timestamp.now(tz=IST).strftime("%H:%M")
        return (a <= now < b) if a <= b else (now >= a or now < b)

    def notify(self, text: str, loud: bool = True, kind: str = "info"):
        ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with ALERT_LOG.open("a") as f:
            f.write(json.dumps({"t": pd.Timestamp.now(tz=IST).isoformat(), "kind": kind, "loud": loud, "text": text}) + "\n")
        if self.tg:
            self.tg.enqueue(text, silent=(not loud) or self.quiet_now())


hub: Hub | None = None


def _compute():
    con = store.connect()
    try:
        state, eng = live.build_state(con, return_engine=True)
        new = hub.runner.process(eng)
        new += hub.runner.smc_process(con)
        ctx = hub.runner.context(eng, state)
        ctx["bias_stats"] = hub.runner.bias_stats
        msgs = [(alerts.format_alert(a, ctx, hub.runner.stats), a.loud, a.kind) for a in new]
        flip = hub.runner.regime_change(state.get("regime"))
        if flip:
            msgs.append((flip, True, "REGIME"))
        state["recent_alerts"] = hub.runner.history[-15:][::-1]
        state["structure_bias"] = ctx.get("bias")
        state["smc"] = hub.runner.smc_snap
        return state, msgs, ctx
    finally:
        con.close()


def _backfill(recheck_minutes: int = 0) -> int:
    con = store.connect()
    try:
        start = None
        if recheck_minutes:
            last = store.last_ts(con)
            start = last - recheck_minutes * 60_000 if last else None
        return fetch.backfill(con, start_ms=start)
    finally:
        con.close()


async def recompute_loop():
    while True:
        await hub.dirty.wait()
        hub.dirty.clear()
        try:
            st, msgs, ctx = await asyncio.to_thread(_compute)
            st["feed"] = hub.feed
            st["telegram"] = telegram_status()
            hub.state, hub.ctx = st, ctx
            for text, loud, kind in msgs:
                hub.notify(text, loud, kind)
                log.info("ALERT %s (%s)", kind, "loud" if loud else "silent")
            await hub.broadcast({"type": "state", "data": st})
            log.info("signal %s score=%s (%.1fs)", st["signal"]["tier"], st["signal"]["score"], st["compute_seconds"])
        except Exception:
            log.exception("recompute failed")


async def feed_loop():
    backoff = 1
    while True:
        try:
            async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=20, open_timeout=15) as ws:
                hub.feed.update(status="connected", since=time.time())
                backoff = 1
                n = await asyncio.to_thread(_backfill)  # close any gap left while disconnected
                if n:
                    log.info("gap filled: %d candles", n)
                hub.dirty.set()
                async for raw in ws:
                    m = json.loads(raw)
                    k = m.get("k")
                    if not k:
                        continue
                    hub.feed["last_msg"] = time.time()
                    hub.tick = {"price": float(k["c"]), "t": int(k["t"]) // 1000, "o": float(k["o"]),
                                "h": float(k["h"]), "l": float(k["l"])}
                    if k["x"]:
                        row = (int(k["t"]), float(k["o"]), float(k["h"]), float(k["l"]), float(k["c"]),
                               float(k["v"]), int(k["n"]))
                        store.upsert(hub.con, [row])
                        ts = pd.DatetimeIndex([pd.Timestamp(int(k["t"]), unit="ms", tz="UTC")])
                        if session.in_session(ts)[0]:
                            hub.dirty.set()
        except Exception as e:  # network drop, Binance 24h disconnect, etc.
            hub.feed.update(status=f"reconnecting: {type(e).__name__}", since=time.time())
            log.warning("feed error %r, retry in %ds", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(60, backoff * 2)


async def tick_loop():
    while True:
        await asyncio.sleep(1)
        if hub.tick and hub.tick != hub.tick_sent and hub.clients:
            hub.tick_sent = hub.tick
            await hub.broadcast({"type": "tick", "data": hub.tick, "feed": hub.feed})


async def watchdog_loop():
    """Feed health + daily brief."""
    brief_sent = None
    while True:
        await asyncio.sleep(30)
        now = pd.Timestamp.now(tz="UTC")
        open_now = bool(session.in_session(pd.DatetimeIndex([now]))[0])
        last = hub.feed.get("last_msg") or hub.feed.get("since")
        silent_for = time.time() - last if last else 0
        if open_now and silent_for > STALL_SECONDS and not hub.stalled:
            hub.stalled = True
            hub.notify(f"⚠️ <b>GOLD DATA FEED STALLED</b>\nNo candles for {silent_for / 60:.0f} min "
                       f"({html.escape(hub.feed.get('status', ''))}). Reconnecting automatically. "
                       f"<b>Don't trust signals until it recovers.</b>", True, "FEED_STALL")
        elif hub.stalled and silent_for < 90:
            hub.stalled = False
            hub.notify("✅ <b>Gold data feed restored.</b> Missing candles were back-filled.", True, "FEED_OK")
        bt = hub.cfg.get("BRIEF_TIME_IST", "")
        ist = now.tz_convert(IST)
        if bt and ist.strftime("%H:%M") == bt and ist.dayofweek < 5 and brief_sent != ist.date() and hub.state:
            brief_sent = ist.date()
            hub.notify(brief_text(), True, "BRIEF")


async def housekeeping_loop():
    """Every 5 min: re-download the last 2h of candles (overwrites = exchange-final values) and
    refresh state; regenerate reports daily right after the 17:00 ET close."""
    last_reports_day = None
    i = 0
    while True:
        await asyncio.sleep(300)
        i += 1
        try:
            await asyncio.to_thread(_backfill, 120)
        except Exception:
            log.exception("reconcile failed")
        if i % 2 == 0:
            hub.dirty.set()
        now_et = pd.Timestamp.now(tz="America/New_York")
        key = now_et.date()
        if now_et.hour == 17 and last_reports_day != key:
            last_reports_day = key
            await regenerate_reports()


async def regenerate_reports():
    for script in ("backtest.py", "analyze_week.py", "backtest_alerts.py", "backtest_regime.py", "backtest_bias.py"):
        proc = await asyncio.create_subprocess_exec(sys.executable, str(ROOT / "scripts" / script),
                                                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        _, err = await proc.communicate()
        if proc.returncode:
            log.warning("%s failed: %s", script, err.decode()[-500:])
    hub.runner.stats = AlertRunner.load_stats()
    hub.runner.bias_stats = smc_alerts.load_stats()
    log.info("reports regenerated")
    hub.dirty.set()


# ---------------------------------------------------------------------- Telegram texts
TIER_EMOJI = {"GREEN": "🟢", "AMBER": "🟡", "RED": "🔴"}
ARROW = {1: "▲", -1: "▼"}


def telegram_status() -> dict:
    if not hub.tg:
        return {"configured": False, "status": "not configured (add TELEGRAM_BOT_TOKEN to .env)"}
    return {"configured": True, "status": hub.tg.status, "subscribers": len(hub.tg.chats),
            "bot": (hub.tg.me or {}).get("username"), "last_error": hub.tg.last_error}


def status_text() -> str:
    s = hub.state
    if not s:
        return "Still loading candles, try again in a few seconds."
    g = s["signal"]
    e = lambda x: html.escape(str(x), quote=False)
    lines = [f"{TIER_EMOJI[g['tier']]} <b>GOLD: {e(g['title'])}</b>  (score <b>{g['score']:.0f}</b>/100)",
             f"<b>{e(g['advice'])}</b>", ""]
    lines += [f"• {e(r)}" for r in g["reasons"]]
    if g.get("how_to_exit_red"):
        lines.append(f"• {e(g['how_to_exit_red'])}")
    rl = regime.summary_line(s.get("regime"))
    if rl:
        lines += ["", rl]
    sb = s.get("structure_bias") or {}
    if sb:
        lines += ["", "Structure trend: " + " · ".join(f"{tf} {ARROW.get(v, '•')}" for tf, v in sb.items())]
    lines.append(f"EMA bias: {s['bias']} · LTF: {s['ltf_label']} (trend quality {s['trend_q']:.0f})")
    if s.get("session_note"):
        lines += ["", f"ℹ️ {e(s['session_note'])}"]
    lines += ["", f"Price {s['price']:.2f} · as of {s['as_of']['ist']}"]
    return "\n".join(lines)


def bias_text() -> str:
    s = hub.state
    if not s:
        return "Still loading."
    lines = ["<b>Gold trend by timeframe (closed candles)</b>", ""]
    sb = s.get("structure_bias") or {}
    for tf in ("15m", "1h", "4h", "1d"):
        st = sb.get(tf)
        word = {1: "Bullish ▲", -1: "Bearish ▼"}.get(st, "n/a")
        ema = s["htf"].get(tf, {})
        extra = f" · EMA20/50 {ema['label']} · ADX {ema['adx']:.0f}" if ema else ""
        lines.append(f"<b>{tf}</b>: structure {word}{extra}")
    return "\n".join(lines)


def brief_text() -> str:
    s = hub.state
    if not s:
        return "Still loading."
    rows = {r["key"]: r for r in s["today_vs_last_week"]["rows"]}
    def row(k, name, d=2, sign=False):
        r = rows.get(k)
        if not r or r["today"] is None:
            return ""
        f = (lambda x: f"{x:+.{d}f}") if sign else (lambda x: f"{x:.{d}f}")
        lw = f(r["last_week"]) if r["last_week"] is not None else "–"
        return f"• {name}: today <b>{f(r['today'])}</b> · last week {lw} · {r['pct_6m']:.0f}th pct of 6m"
    prime = [h["ist"] for h in sorted(s.get("hours", []), key=lambda h: h["ist"]) if h["quality"] == "prime"]
    lines = ["☀️ <b>GOLD DAILY BRIEF</b>", "", status_text(), "",
             f"<b>Today vs last week</b> (first {s['today_vs_last_week']['elapsed_hours']:.1f}h of the session):",
             row("range", "Range so far $", 1), row("atr_5m", "5m ATR $"), row("y2_5m", "5m 1:2 trades R", 2, True),
             "", f"Best hours (IST, last 6m): {', '.join(prime) or 'n/a'}"]
    return "\n".join(x for x in lines if x is not None)


HELP = ("<b>Gold alert bot</b>\n"
        "/status: signal right now (trade / selective / no trade)\n"
        "/bias: trend on 15m · 1h · 4h · 1d\n"
        "/smc: SMC structure on 5m to 1w (CHoCH levels, IDM, internal bias)\n"
        "/brief: daily brief now\n"
        "/mode: quiet mode check (target cap)\n"
        "/alerts: last alerts sent\n"
        "/stop: pause alerts · /start: resume\n\n"
        "You get: 🟢 TRADE conditions ON, 🔴 STOP, 🔄 1h trend shifts, 4h/1d bias changes (loud); "
        "🌙 quiet mode on/off (loud); 🟡 selective/downgrade (silent); "
        "🧭 SMC trend switch on any timeframe (loud, 5m silent); ↪️ SMC internal shift on 1h+ (silent).")


async def handle_command(chat: int, cmd: str, args: list[str]) -> str | None:
    tg = hub.tg
    if cmd == "/start":
        if not tg.subscribe(chat):
            return "⛔ This bot is private."
        return "✅ <b>Subscribed to gold alerts.</b>\n\n" + HELP + "\n\n" + status_text()
    if not tg.is_allowed(chat):
        return "⛔ This bot is private."
    if cmd == "/stop":
        tg.unsubscribe(chat)
        return "🔕 Alerts paused. Send /start to resume."
    if cmd == "/status":
        return status_text()
    if cmd == "/bias":
        return bias_text()
    if cmd == "/brief":
        return brief_text()
    if cmd == "/smc":
        return smc_alerts.map_text(hub.runner.smc_snap)
    if cmd == "/mode":
        return regime.detail_text(hub.state.get("regime")) if hub.state else "Still loading."
    if cmd == "/alerts":
        h = hub.runner.history[-10:][::-1]
        if not h:
            return "No alerts yet."
        return "<b>Last alerts</b>\n" + "\n".join(
            f"• {pd.Timestamp(x['time']).tz_convert(IST):%a %H:%M} IST: {x['kind'].replace('CONDITIONS_', '')}"
            f"{' ' + x['tf'] + ' ' + ARROW.get(x['dir'], '') if x.get('tf') else ''}"
            f"{' (' + x['tag'].lower() + ' higher TF)' if x.get('tag') else ''}" for x in h)
    return HELP


async def telegram_start():
    tg = hub.tg
    ok = await tg.check()
    log.info("telegram: %s", tg.status)
    if ok:
        try:
            await tg._call("setMyCommands", commands=[
                {"command": "status", "description": "Trade or not, right now"},
                {"command": "bias", "description": "Trend on 15m/1h/4h/1d"},
                {"command": "smc", "description": "SMC structure on 5m to 1w"},
                {"command": "brief", "description": "Daily brief"},
                {"command": "mode", "description": "Quiet mode check (target cap)"},
                {"command": "alerts", "description": "Last alerts"},
                {"command": "stop", "description": "Pause alerts"},
                {"command": "start", "description": "Subscribe / resume"}])
        except Exception as e:
            log.warning("setMyCommands failed: %s", e)
        if tg.chats:
            tg.enqueue("🔁 <b>Gold alert bot restarted</b> and is watching the candles again.", silent=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global hub
    hub = Hub()
    n = await asyncio.to_thread(_backfill)
    log.info("startup backfill: %d candles", n)
    stale = [p for p in (REPORTS_DIR / "backtest.json", REPORTS_DIR / "week_report.json", REPORTS_DIR / "alert_stats.json",
                         REPORTS_DIR / "regime_backtest.json", REPORTS_DIR / "bias_stats.json")
             if not p.exists() or time.time() - p.stat().st_mtime > 20 * 3600]
    if stale:
        await regenerate_reports()
    loops = [recompute_loop, feed_loop, tick_loop, housekeeping_loop, watchdog_loop]
    tasks = [asyncio.create_task(f()) for f in loops]
    if hub.tg:
        await telegram_start()
        tasks += [asyncio.create_task(hub.tg.sender_loop()), asyncio.create_task(hub.tg.poll_loop(handle_command))]
    else:
        log.info("Telegram not configured: alerts go to data/alerts.log only")
    hub.dirty.set()
    yield
    for t in tasks:
        t.cancel()
    if hub.tg and hub.tg.session:
        await hub.tg.session.close()


app = FastAPI(title="Gold trade filter", lifespan=lifespan)


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/state")
async def api_state():
    for _ in range(100):
        if hub.state:
            break
        await asyncio.sleep(0.1)
    return JSONResponse(hub.state or {"loading": True})


@app.get("/api/candles")
async def api_candles(tf: str = "5m", n: int = 400):
    def run():
        con = store.connect()
        try:
            return live.candles(con, tf, min(n, 2000))
        finally:
            con.close()
    return JSONResponse(await asyncio.to_thread(run))


@app.get("/reports/{name}")
async def reports(name: str):
    if name not in ("week_report.md", "backtest.md", "alerts_backtest.md", "candle_check.md", "regime_backtest.md"):
        return PlainTextResponse("not found", status_code=404)
    p = REPORTS_DIR / name
    return PlainTextResponse(p.read_text() if p.exists() else "Report not generated yet.")


@app.get("/healthz")
async def healthz():
    return {"feed": hub.feed, "has_state": hub.state is not None, "clients": len(hub.clients),
            "telegram": telegram_status(), "stalled": hub.stalled}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    hub.clients.add(ws)
    try:
        if hub.state:
            await ws.send_text(json.dumps({"type": "state", "data": hub.state}, default=str))
        while True:
            await ws.receive_text()  # keepalive pings from the page
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.discard(ws)
