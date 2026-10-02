from __future__ import annotations

import os
from pathlib import Path


# ============================================================
# PROJECT PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"
LOGS_DIR = BASE_DIR / "logs"
CACHE_DIR = DATA_DIR / "cache"
STATE_DIR = DATA_DIR / "state"

for folder in (
    DATA_DIR,
    REPORTS_DIR,
    LOGS_DIR,
    CACHE_DIR,
    STATE_DIR,
):
    folder.mkdir(
        parents=True,
        exist_ok=True,
    )


def _env_bool(
    name: str,
    default: bool,
) -> bool:
    raw = os.getenv(
        name,
        "true" if default else "false",
    )
    return raw.strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
    }


def _env_float(
    name: str,
    default: float,
) -> float:
    raw = os.getenv(
        name,
        str(default),
    )
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(
    name: str,
    default: int,
) -> int:
    raw = os.getenv(
        name,
        str(default),
    )
    try:
        return int(raw)
    except ValueError:
        return default


# ============================================================
# DATA PROVIDER
# ============================================================

DATA_SOURCE = os.getenv(
    "DATA_SOURCE",
    "upstox",
).strip().lower()

ALLOW_YAHOO_FALLBACK = _env_bool(
    "ALLOW_YAHOO_FALLBACK",
    True,
)


# ============================================================
# UPSTOX
# ============================================================

UPSTOX_API_KEY = os.getenv(
    "UPSTOX_API_KEY",
    "",
).strip()

UPSTOX_API_SECRET = os.getenv(
    "UPSTOX_API_SECRET",
    "",
).strip()

def _streamlit_secret(name: str) -> str:
    try:
        import streamlit as st
        value = st.secrets.get(name, "")
        return str(value).strip() if value is not None else ""
    except Exception:
        return ""


UPSTOX_ACCESS_TOKEN = (
    os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
    or _streamlit_secret("UPSTOX_ACCESS_TOKEN")
)

UPSTOX_REDIRECT_URI = os.getenv(
    "UPSTOX_REDIRECT_URI",
    "http://127.0.0.1:8000",
).strip()

UPSTOX_API_BASE_URL = (
    "https://api.upstox.com"
)

UPSTOX_NSE_INSTRUMENTS_URL = (
    "https://assets.upstox.com/"
    "market-quote/instruments/exchange/NSE.json.gz"
)

UPSTOX_INSTRUMENT_CACHE_FILE = (
    CACHE_DIR
    / "upstox_nse_instruments.json"
)

UPSTOX_INSTRUMENT_CACHE_HOURS = 18
UPSTOX_REQUEST_TIMEOUT_SECONDS = 30
UPSTOX_MAX_RETRIES = 3
UPSTOX_RETRY_BACKOFF_SECONDS = 1.0
UPSTOX_WS_RECONNECT_SECONDS = _env_float("UPSTOX_WS_RECONNECT_SECONDS", 5.0)
UPSTOX_WS_MAX_INSTRUMENTS = _env_int("UPSTOX_WS_MAX_INSTRUMENTS", 1500)
UPSTOX_WS_MODE = os.getenv("UPSTOX_WS_MODE", "full").strip().lower()

# Live terminal scanner. Full V3 mode supports up to 1500 combined
# instrument keys for a normal user; the scanner deliberately uses a smaller
# working set by default to keep candle warm-up and memory predictable.
LIVE_SCANNER_MAX_SYMBOLS = _env_int("LIVE_SCANNER_MAX_SYMBOLS", 100)
LIVE_SCANNER_TIMEFRAME = os.getenv("LIVE_SCANNER_TIMEFRAME", "5m").strip()
LIVE_SCANNER_STALE_SECONDS = _env_int("LIVE_SCANNER_STALE_SECONDS", 15)
UPSTOX_HISTORY_UNIT = "days"
UPSTOX_HISTORY_INTERVAL = 1
UPSTOX_HISTORY_CALENDAR_DAYS = 1100
UPSTOX_INCLUDE_CURRENT_INTRADAY = False


# ============================================================
# STOCK UNIVERSE
# ============================================================

STOCK_UNIVERSE_NAME = os.getenv(
    "STOCK_UNIVERSE_NAME",
    "Nifty Total Market",
).strip()

SCANNER_NAME = "Momentum & Breakout Scanner V1.0"

STOCK_UNIVERSE_CSV_URL = os.getenv(
    "STOCK_UNIVERSE_CSV_URL",
    (
        "https://www.niftyindices.com/"
        "IndexConstituent/"
        "ind_niftytotalmarket_list.csv"
    ),
).strip()

# Backward-compatible alias for older imports. The scanner itself uses the
# generic STOCK_UNIVERSE_CSV_URL setting.
NIFTY_500_CSV_URL = STOCK_UNIVERSE_CSV_URL

MAX_STOCKS: int | None = None
REQUEST_DELAY_SECONDS = 0.20

DOWNLOAD_PERIOD = "3y"
DOWNLOAD_INTERVAL = "1d"

BENCHMARK_SYMBOL = "^NSEI"
DISTRIBUTION_VOLUME_SYMBOL = "NIFTYBEES"
MARKET_REQUIRE_BULLISH = False


# ============================================================
# OUTPUTS
# ============================================================

OUTPUT_FILE = (
    REPORTS_DIR
    / "momentum_breakout_results.xlsx"
)

WATCHLIST_TEXT_FILE = (
    REPORTS_DIR
    / "momentum_breakout_watchlist.txt"
)

LOG_FILE = (
    LOGS_DIR
    / "scanner.log"
)


# ============================================================
# RELATIVE AND SECTOR STRENGTH
# ============================================================

RS_THRESHOLD = 70
RS_WEIGHT_3M = 0.40
RS_WEIGHT_6M = 0.30
RS_WEIGHT_12M = 0.30

SECTOR_RS_THRESHOLD = 60


# ============================================================
# LIQUIDITY GATE
# ============================================================

# Hard eligibility rules for the momentum scanner. Average daily
# traded value is calculated as current price multiplied by the
# 20-session average volume.
MIN_PRICE = _env_float(
    "MIN_PRICE",
    50.0,
)

MIN_AVG_TURNOVER_VALUE = _env_float(
    "MIN_AVG_TURNOVER_VALUE",
    20000000.0,
)


# ============================================================
# HISTORICAL VOLUME ANALYSIS
# ============================================================

VOLUME_DRY_UP_THRESHOLD = 0.75
BREAKOUT_VOLUME_THRESHOLD = 1.50
UP_DOWN_VOLUME_THRESHOLD = 1.00
VOLUME_SCORE_THRESHOLD = 60


# ============================================================
# VCP AND PIVOT
# ============================================================

VCP_LOOKBACK_DAYS = 120
VCP_SWING_WINDOW = 5
VCP_MIN_CONTRACTIONS = 2
VCP_MAX_BASE_DEPTH_PCT = 35.0
VCP_SCORE_THRESHOLD = 60

PIVOT_LOOKBACK_DAYS = 20
NEAR_PIVOT_THRESHOLD_PCT = 3.0
MAX_PIVOT_EXTENSION_PCT = 5.0


# ============================================================
# SWING SETUP ENGINE
# ============================================================

SWING_LOOKBACK_DAYS = _env_int("SWING_LOOKBACK_DAYS", 120)
SWING_SUPPORT_ZONE_PCT = _env_float("SWING_SUPPORT_ZONE_PCT", 1.5)
SWING_NEAR_SUPPORT_PCT = _env_float("SWING_NEAR_SUPPORT_PCT", 3.0)
SWING_NEAR_PIVOT_PCT = _env_float("SWING_NEAR_PIVOT_PCT", 3.0)
SWING_MIN_SCORE = _env_float("SWING_MIN_SCORE", 65.0)
SWING_MIN_TREND_SCORE = _env_float("SWING_MIN_TREND_SCORE", 60.0)
SWING_MAX_BASE_DEPTH_PCT = _env_float("SWING_MAX_BASE_DEPTH_PCT", 35.0)
SWING_WATCHLIST_SIZE = _env_int("SWING_WATCHLIST_SIZE", 10)


# ============================================================
# NOTIFICATIONS
# ============================================================

TOP_WATCHLIST_SIZE = 10
DECISION_WATCHLIST_SIZE = 12

NOTIFICATION_PROVIDER = os.getenv(
    "NOTIFICATION_PROVIDER",
    "telegram",
).strip().lower()

TELEGRAM_ENABLED = _env_bool(
    "TELEGRAM_ENABLED",
    True,
)

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    "",
).strip()

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID",
    "",
).strip()

WHATSAPP_ENABLED = _env_bool(
    "WHATSAPP_ENABLED",
    False,
)


# ============================================================
# ACCOUNT AND TRADE PLANNER
# ============================================================

ACCOUNT_CAPITAL = _env_float(
    "ACCOUNT_CAPITAL",
    100000.0,
)

RISK_PER_TRADE_PCT = _env_float(
    "RISK_PER_TRADE_PCT",
    1.0,
)

ENTRY_BUFFER_PCT = 0.10

STOP_LOOKBACK_DAYS = 10
ATR_PERIOD = 14
ATR_STOP_MULTIPLIER = 1.50
MIN_STOP_LOSS_PCT = 3.0
MAX_STOP_LOSS_PCT = 7.0

MIN_TRADE_SCORE = 80.0
TOP_TRADE_SCORE = 90.0


# ============================================================
# DASHBOARD
# ============================================================

DASHBOARD_TITLE = "Minervini Scanner V3"
DASHBOARD_DEFAULT_ROWS = 25


# ============================================================
# UPSTOX LTP OVERLAY
# ============================================================

LTP_OVERLAY_ENABLED = _env_bool(
    "LTP_OVERLAY_ENABLED",
    True,
)

LTP_OVERLAY_REQUIRED = _env_bool(
    "LTP_OVERLAY_REQUIRED",
    False,
)

LTP_BATCH_SIZE = 500

LTP_VOLUME_UPDATE_AFTER_HOUR = 15
LTP_VOLUME_UPDATE_AFTER_MINUTE = 31


# ============================================================
# V3.3 LIVE TRADING MODE
# ============================================================

# Price/action thresholds.
LIVE_NEAR_TRIGGER_PCT = _env_float(
    "LIVE_NEAR_TRIGGER_PCT",
    2.0,
)

LIVE_WATCH_BELOW_ENTRY_PCT = _env_float(
    "LIVE_WATCH_BELOW_ENTRY_PCT",
    5.0,
)

LIVE_WAIT_MAX_BELOW_ENTRY_PCT = _env_float(
    "LIVE_WAIT_MAX_BELOW_ENTRY_PCT",
    12.0,
)

MAX_BUY_EXTENSION_PCT = _env_float(
    "MAX_BUY_EXTENSION_PCT",
    2.0,
)

MAX_ALLOWED_EXTENSION_PCT = _env_float(
    "MAX_ALLOWED_EXTENSION_PCT",
    5.0,
)

BUY_ENTRY_TOLERANCE_PCT = _env_float(
    "BUY_ENTRY_TOLERANCE_PCT",
    0.25,
)

MIN_BUY_CONFIDENCE = _env_float(
    "MIN_BUY_CONFIDENCE",
    80.0,
)

MIN_WATCH_CONFIDENCE = _env_float(
    "MIN_WATCH_CONFIDENCE",
    70.0,
)

# Live volume confirmation.
LIVE_VOLUME_CONFIRMATION_ENABLED = _env_bool(
    "LIVE_VOLUME_CONFIRMATION_ENABLED",
    True,
)

LIVE_BUY_REQUIRES_VOLUME = _env_bool(
    "LIVE_BUY_REQUIRES_VOLUME",
    True,
)

LIVE_VOLUME_MIN_ELAPSED_MINUTES = _env_int(
    "LIVE_VOLUME_MIN_ELAPSED_MINUTES",
    15,
)

LIVE_VOLUME_ACCEPTABLE_RATIO = _env_float(
    "LIVE_VOLUME_ACCEPTABLE_RATIO",
    1.20,
)

LIVE_VOLUME_GOOD_RATIO = _env_float(
    "LIVE_VOLUME_GOOD_RATIO",
    1.50,
)

LIVE_VOLUME_STRONG_RATIO = _env_float(
    "LIVE_VOLUME_STRONG_RATIO",
    2.00,
)

# NSE cash-market session.
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 30
MARKET_SESSION_MINUTES = 375

# Confidence weighting.
CONFIDENCE_WEIGHT_QUALITY = 0.30
CONFIDENCE_WEIGHT_RS = 0.20
CONFIDENCE_WEIGHT_SECTOR = 0.15
CONFIDENCE_WEIGHT_VCP = 0.15
CONFIDENCE_WEIGHT_VOLUME = 0.10
CONFIDENCE_WEIGHT_PROXIMITY = 0.10

CAUTIOUS_MARKET_CONFIDENCE_PENALTY = 5.0
BEARISH_MARKET_CONFIDENCE_PENALTY = 12.0

LOW_RISK_STOP_PCT = 4.0
HIGH_RISK_STOP_PCT = 6.0

SHOW_EMA_PANEL = True
SHOW_VOLUME_PANEL = True


# ============================================================
# CIRCUIT-LIMIT EXECUTION GUARD
# ============================================================

CIRCUIT_GUARD_ENABLED = _env_bool(
    "CIRCUIT_GUARD_ENABLED",
    True,
)

UPPER_CIRCUIT_BLOCK_DISTANCE_PCT = _env_float(
    "UPPER_CIRCUIT_BLOCK_DISTANCE_PCT",
    0.50,
)

UPPER_CIRCUIT_CAUTION_DISTANCE_PCT = _env_float(
    "UPPER_CIRCUIT_CAUTION_DISTANCE_PCT",
    1.00,
)


# ============================================================
# FUNDAMENTALS GATE
# ============================================================

FUNDAMENTALS_GATE_MODE = os.getenv(
    "FUNDAMENTALS_GATE_MODE",
    "advisory",
).strip().lower()


# ============================================================
# BREAKOUT AND MOMENTUM CLASSIFICATION
# ============================================================

BREAKOUT_RECENT_SESSIONS = _env_int(
    "BREAKOUT_RECENT_SESSIONS",
    5,
)
BREAKOUT_MIN_VOLUME_RATIO = _env_float(
    "BREAKOUT_MIN_VOLUME_RATIO",
    1.20,
)
BREAKOUT_NEAR_PCT = _env_float(
    "BREAKOUT_NEAR_PCT",
    3.0,
)
BREAKOUT_MAX_EXTENSION_PCT = _env_float(
    "BREAKOUT_MAX_EXTENSION_PCT",
    5.0,
)
BREAKOUT_MIN_DAILY_GAIN_PCT = _env_float(
    "BREAKOUT_MIN_DAILY_GAIN_PCT",
    3.0,
)
MOMENTUM_MIN_5D_RETURN_PCT = _env_float(
    "MOMENTUM_MIN_5D_RETURN_PCT",
    8.0,
)
BREAKOUT_MIN_RS_SCORE = _env_float(
    "BREAKOUT_MIN_RS_SCORE",
    60.0,
)

FUNDAMENTALS_CSV_PATH = Path(
    os.getenv(
        "FUNDAMENTALS_CSV_PATH",
        str(DATA_DIR / "fundamentals.csv"),
    )
)

FUNDAMENTALS_CSV_URL = os.getenv(
    "FUNDAMENTALS_CSV_URL",
    "",
).strip()

FUNDAMENTALS_MAX_AGE_DAYS = _env_int(
    "FUNDAMENTALS_MAX_AGE_DAYS",
    120,
)
FUNDAMENTALS_MIN_EPS_GROWTH_PCT = _env_float(
    "FUNDAMENTALS_MIN_EPS_GROWTH_PCT",
    20.0,
)
FUNDAMENTALS_MIN_SALES_GROWTH_PCT = _env_float(
    "FUNDAMENTALS_MIN_SALES_GROWTH_PCT",
    15.0,
)
FUNDAMENTALS_REQUIRE_EPS_ACCELERATION = _env_bool(
    "FUNDAMENTALS_REQUIRE_EPS_ACCELERATION",
    True,
)
FUNDAMENTALS_REQUIRE_MARGIN_EXPANSION = _env_bool(
    "FUNDAMENTALS_REQUIRE_MARGIN_EXPANSION",
    True,
)


# ============================================================
# RS LINE / MARKET DISTRIBUTION / BASE STAGE
# ============================================================

RS_LINE_LOOKBACK_DAYS = 252
RS_LINE_SLOPE_DAYS = 20

DISTRIBUTION_LOOKBACK_DAYS = 25
DISTRIBUTION_MIN_DECLINE_PCT = 0.20
DISTRIBUTION_CAUTION_COUNT = 5
DISTRIBUTION_PRESSURE_COUNT = 7

BASE_STAGE_ENABLED = _env_bool(
    "BASE_STAGE_ENABLED",
    False,
)
BASE_STAGE_MAX_ELIGIBLE = _env_int(
    "BASE_STAGE_MAX_ELIGIBLE",
    2,
)
BASE_STAGE_NEW_PIVOT_PCT = _env_float(
    "BASE_STAGE_NEW_PIVOT_PCT",
    5.0,
)
BASE_STAGE_MIN_DAYS_BETWEEN = _env_int(
    "BASE_STAGE_MIN_DAYS_BETWEEN",
    20,
)
BASE_STAGE_STATE_FILE = (
    STATE_DIR / "base_stage_state.json"
)


# ============================================================
# V4 MULTI-PATTERN ENGINE
# ============================================================

PATTERN_ENGINE_ENABLED = _env_bool(
    "PATTERN_ENGINE_ENABLED",
    True,
)

PATTERN_MIN_CONFIDENCE = _env_float(
    "PATTERN_MIN_CONFIDENCE",
    70.0,
)

# Episodic Pivot
EP_GAP_MIN_PCT = 5.0
EP_VOLUME_MIN_RATIO = 2.0
EP_PRIOR_BASE_DAYS = 40
EP_PRIOR_BASE_MAX_DEPTH_PCT = 25.0

# Cup with Handle
CUP_LOOKBACK_DAYS = 180
CUP_MIN_DURATION_DAYS = 30
CUP_MAX_DURATION_DAYS = 150
CUP_MIN_DEPTH_PCT = 12.0
CUP_MAX_DEPTH_PCT = 40.0
CUP_RIGHT_LIP_TOLERANCE_PCT = 8.0
HANDLE_MIN_DAYS = 5
HANDLE_MAX_DAYS = 25
HANDLE_MAX_DEPTH_PCT = 15.0
HANDLE_VOLUME_DRYUP_RATIO = 0.90
CUP_MIN_CONFIDENCE = 70.0

# Flat Base
FLAT_BASE_MIN_DAYS = 25
FLAT_BASE_MAX_DAYS = 50
FLAT_BASE_MAX_DEPTH_PCT = 16.0
FLAT_BASE_MIN_PRIOR_RISE_PCT = 12.0
FLAT_BASE_VOLUME_DRYUP_RATIO = 0.90
FLAT_BASE_MAX_DISTANCE_TO_PIVOT_PCT = 6.0

# Double Bottom
DOUBLE_BOTTOM_LOOKBACK_DAYS = 140
DOUBLE_BOTTOM_MIN_SEPARATION_DAYS = 15
DOUBLE_BOTTOM_MAX_LOW_DIFFERENCE_PCT = 6.0
DOUBLE_BOTTOM_MAX_DEPTH_PCT = 40.0
DOUBLE_BOTTOM_UNDERCUT_TOLERANCE_PCT = 5.0

# Pocket Pivot and Volume Dry-Up
POCKET_PIVOT_LOOKBACK_DAYS = 10
POCKET_PIVOT_RECENT_DAYS = 5
POCKET_PIVOT_MIN_VOLUME_RATIO = 1.05
POCKET_PIVOT_MAX_DISTANCE_PCT = 6.0
VDU_RECENT_DAYS = 5
VDU_BASELINE_DAYS = 50
VDU_MAX_RATIO = 0.60

# Bull Flag
BULL_FLAG_ENABLED = _env_bool(
    "BULL_FLAG_ENABLED",
    False,
)
BULL_FLAG_POLE_DAYS = 20
BULL_FLAG_MIN_POLE_GAIN_PCT = 15.0
BULL_FLAG_MAX_POLE_GAIN_PCT = 80.0
BULL_FLAG_MIN_DAYS = 5
BULL_FLAG_MAX_DAYS = 20
BULL_FLAG_MAX_DEPTH_PCT = 16.0
BULL_FLAG_VOLUME_DRYUP_RATIO = 0.90
BULL_FLAG_MIN_SLOPE_PCT = -0.80
BULL_FLAG_MAX_SLOPE_PCT = 0.15
BULL_FLAG_MAX_DISTANCE_TO_PIVOT_PCT = 6.0

# Ascending Triangle
ASC_TRIANGLE_LOOKBACK_DAYS = 60
ASC_TRIANGLE_RESISTANCE_TOLERANCE_PCT = 3.0
ASC_TRIANGLE_MIN_TOUCHES = 2
ASC_TRIANGLE_MIN_LOW_SLOPE_PCT = 0.05
ASC_TRIANGLE_MAX_RESISTANCE_SLOPE_PCT = 0.05

# IPO Base
IPO_BASE_MIN_HISTORY_DAYS = 35
IPO_BASE_MAX_HISTORY_DAYS = 300
IPO_BASE_MIN_DAYS = 15
IPO_BASE_MAX_DAYS = 80
IPO_BASE_MIN_DEPTH_PCT = 8.0
IPO_BASE_MAX_DEPTH_PCT = 40.0

# Young IPOs do not yet have 200 sessions of history.  Sixty-five
# completed sessions are enough for the IPO-base, volume and 3M-RS logic.
MIN_PRICE_HISTORY_RECORDS = 65

# High Tight Flag
HTF_RISE_DAYS = 40
HTF_MIN_RISE_PCT = 70.0
HTF_FLAG_MIN_DAYS = 5
HTF_FLAG_MAX_DAYS = 20
HTF_MAX_FLAG_DEPTH_PCT = 25.0
HTF_FLAG_VOLUME_DRYUP_RATIO = 0.85
HTF_FLAG_MIN_SLOPE_PCT = -1.00
HTF_FLAG_MAX_SLOPE_PCT = 0.15
HTF_MAX_DISTANCE_TO_PIVOT_PCT = 6.0


# ============================================================
# BACKWARD-COMPATIBILITY ALIASES
# ============================================================

# Existing modules may still import these names.
BUY_ZONE_BELOW_ENTRY_PCT = BUY_ENTRY_TOLERANCE_PCT
BUY_NOW_MAX_EXTENSION_PCT = MAX_BUY_EXTENSION_PCT
HOLD_MAX_EXTENSION_PCT = MAX_ALLOWED_EXTENSION_PCT
WATCH_BELOW_ENTRY_PCT = LIVE_WATCH_BELOW_ENTRY_PCT
DECISION_MIN_BUY_SCORE = MIN_BUY_CONFIDENCE
DECISION_MIN_WATCH_SCORE = MIN_WATCH_CONFIDENCE
