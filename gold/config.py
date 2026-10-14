"""Central settings for the gold signal filter."""
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
DB_PATH = DATA_DIR / "candles.db"

SYMBOL = "XAUUSDT"
REST_BASE = "https://fapi.binance.com"
# Binance moved USD-M market streams under /market; the old /ws path no longer pushes klines.
WS_URL = "wss://fstream.binance.com/market/ws/xauusdt@kline_1m"
LISTING_MS = 1765440300000  # XAUUSDT perpetual onboard date (2025-12-11)

ET = ZoneInfo("America/New_York")
IST = ZoneInfo("Asia/Kolkata")

# forex.com XAUUSD hours: Sun 18:00 ET -> Fri 17:00 ET, daily break 17:00-18:00 ET.
SESSION_OPEN_HOUR_ET = 18
SESSION_CLOSE_HOUR_ET = 17

# Session dates (ET trade date) on which forex.com metals are fully closed.
CLOSED_SESSION_DATES = {"2025-12-25", "2026-01-01", "2026-04-03"}
# US holidays where metals stop trading early (13:30 ET) and reopen at 18:00 ET.
EARLY_CLOSE_DATES = {
    "2025-12-24": 13.5, "2025-12-31": 13.5, "2026-01-19": 13.5, "2026-02-16": 13.5,
    "2026-05-25": 13.5, "2026-06-19": 13.5, "2026-07-03": 13.5, "2026-09-07": 13.5,
    "2026-11-26": 13.5, "2026-12-24": 13.5, "2026-12-31": 13.5,
}

# Assumed round-trip cost per trade in USD (typical forex.com XAUUSD spread + slippage).
COST_USD = 0.40

# Baseline window (calendar days) used for "vs last 6 months" comparisons.
BASELINE_DAYS = 182

# Timeframes in minutes. 4h and 1d are anchored to the 18:00 ET session open like forex.com charts.
TIMEFRAMES = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
LTF = ["1m", "5m", "15m"]
HTF = ["1h", "4h", "1d"]
