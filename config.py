# Trading Pairs (Yahoo Finance Tickers) — first is default for backtest/CLI
# GBPUSD=X : GBP/USD (default)
# GC=F : Gold Futures
# BTC-USD : Bitcoin
# ^NDX : Nasdaq 100 Index
SYMBOLS = [ 'GC=F', 'GBPUSD=X', 'BTC-USD', '^NDX']

LIVE_MODE = True   # True = real money, False = paper trading
MAX_TRADES_PER_DAY_PER_PAIR = False   # True = limits apply per symbol; False = global (legacy)
MAX_TRADES_PER_DAY = 12
MAX_TRADES_PER_SESSION = 4 
MANUAL_APPROVAL = False   # Require confirmation before each trade; False = bot auto-approves (for server/headless)
LIVE_CONFIRM_ON_START = True   # When live: require typing 'yes' before loop starts
MAX_LOT_LIVE = None   # Cap lot size in live mode (safety)
  # Per session (London, NY); divides daily limit across sessions
# Session hours (UTC) for per-session limit: London 7-10, NY 13-16, Asian 0-4
TRADE_SESSION_HOURS = {
    7: 'london', 8: 'london', 9: 'london', 10: 'london',
    13: 'ny', 14: 'ny', 15: 'ny', 16: 'ny',
    0: 'asian', 1: 'asian', 2: 'asian', 3: 'asian', 4: 'asian',
}
MAX_POSITION_SIZE = 0.04  # Fallback lot size when dynamic calc fails
USE_DYNAMIC_POSITION_SIZING = True  # Risk % of current balance per trade (matches backtest)
PAPER_TRADING_LOG = 'paper_trades.json'
LIVE_TRADE_LOG = True   # Append trades to logs/trades_YYYYMMDD.json
TP1_SL_TO_ENTRY_ENABLED = False   # True = move SL to entry when TP1 hit
TP1_RATIO = 0.3   

# Risk Management
RISK_REWARD_RATIO =5.0  # 1:5 Risk:Reward (win = 5× risk)

# Backtesting
INITIAL_BALANCE = 100
RISK_PER_TRADE = 0.10  # 10% risk per trade
BACKTEST_MAX_TRADES = None  # Stop after N trades (None = no limit)
BACKTEST_APPLY_TRADE_LIMITS = False  # When True, apply trade limits in backtest (both strategies)
BACKTEST_MAX_TRADES_PER_DAY = 6   # Backtest daily limit (used when BACKTEST_APPLY_TRADE_LIMITS=True)
BACKTEST_MAX_TRADES_PER_SESSION = 2  # Backtest session limit (used when BACKTEST_APPLY_TRADE_LIMITS=True)
BACKTEST_PERIOD = '60d'  # Data period: 12d, 60d, 6mo (set before run)
BACKTEST_SPREAD_PIPS = 2.0       # e.g. 2.0 for gold, 1.0 for forex
BACKTEST_COMMISSION_PER_LOT = 7.0  # round-trip per lot (e.g. 7.0)
BACKTEST_SLIPPAGE_PIPS = 0.5     # e.g. 0.5

# Kill zone hours (UTC) — used by strategies for session filtering
KILL_ZONE_HOURS = [7, 8, 9, 10, 13, 14, 15, 16]

# Live Trading Settings
import os
from dotenv import load_dotenv

load_dotenv()  # Load from .env file


# MT5 Settings (loaded from environment variables for security)
MT5_LOGIN = os.getenv('MT5_LOGIN')  # Your MT5 account number
MT5_PASSWORD = os.getenv('MT5_PASSWORD')  # Your MT5 password
MT5_SERVER = os.getenv('MT5_SERVER', 'Exness-MT5Trial')  # Your Exness MT5 server
# Full path to Exness MetaTrader 5 terminal64.exe (e.g. C:/Program Files/MetaTrader 5 EXNESS/terminal64.exe). Use forward slashes in .env.
MT5_PATH = os.getenv('MT5_PATH')  # None = auto-detect
# When True and MT5_PATH is set, the bot starts Exness MT5 automatically when you run paper/live.
MT5_AUTO_START = os.getenv('MT5_AUTO_START', 'true').lower() in ('true', '1', 'yes')
# Connection retries and logging
MT5_CONNECT_RETRIES = 5       # Max attempts for initialize + login
MT5_CONNECT_DELAY = 5         # Seconds between retries
MT5_VERBOSE = True            # Log connection steps, data fetches, etc.
# Optional: fixed order comment (max 31 chars, alphanumeric + space hyphen underscore).
# None = use strategy reason; '' (set MT5_ORDER_COMMENT= in .env) = send empty; 'ICT' = fixed comment.
MT5_ORDER_COMMENT = os.getenv('MT5_ORDER_COMMENT')  # None if key missing, '' if empty, else value
if MT5_ORDER_COMMENT is not None:
    MT5_ORDER_COMMENT = MT5_ORDER_COMMENT.strip()

# Telegram: notify setup before trade when TELEGRAM_ENABLED=true (live/paper only)
TELEGRAM_ENABLED = os.getenv('TELEGRAM_ENABLED', 'false').lower() in ('true', '1', 'yes')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')  # From @BotFather
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')     # Your chat/group ID

# Live Trading Symbols (MT5 format) — first is default for paper/live
LIVE_SYMBOLS = {
     'XAUUSD': 'XAUUSDm',  # Exness gold symbol
    'GBPUSD': 'GBPUSDm',
    'BTCUSD': 'BTCUSDm',
    'NAS100': 'NAS100m'
}


# Trading Loop Settings
LIVE_CHECK_INTERVAL = 15  # Seconds between strategy checks
SKIP_WHEN_MARKET_CLOSED = True   # When True, skip strategy run and execution on weekend or when symbol trade_mode is disabled
PRINT_CHECKLIST_ON_START = True  # When True, print real-money checklist at live startup (paper mode: no)
USE_MARGIN_CHECK = True   # Pre-trade margin check for live mode (skip if insufficient free margin)
LIVE_DEBUG = True         # Log when no signals (data range, bar counts) to diagnose why live misses trades
# Same symbol: do not take a new trade if we already have an open position on that pair, except when adding at TP1/TP2
ALLOW_SAME_SYMBOL_AT_TP = True   # If True, allow new entry on same symbol only when price is at/near existing position's TP
AT_TP_POINTS = 5.0               # Consider "at TP" when entry price is within this many points of position's TP (e.g. 5 for XAUUSD)

# Breakeven: when position is in profit by BREAKEVEN_PIPS, move SL to half that (lock in half the pips)
BREAKEVEN_ENABLED = False         # If True, move SL to half breakeven once profit reaches BREAKEVEN_PIPS
BREAKEVEN_PIPS = 10.0            # Trigger when trade is in profit by this many pips; SL moves to entry + half (e.g. 10 → 5 pips locked)


# Bias of the day (ICT-style): show Daily + H1 BOS bias in live loop when True
SHOW_BIAS_OF_DAY = True          # If True, print [BIAS OF DAY] Daily: X | H1: Y each cycle

# ICT indicator source: False = Kingsley fractal, True = LuxAlgo-style pivot (used by Marvellous via indicators_bos)
USE_LUXALGO_ICT = False
LUXALGO_SWING_LENGTH = 5      # Pivot left/right (LuxAlgo default: 5)
LUXALGO_OB_USE_BODY = True   # Use candle body for OB range (LuxAlgo default)

# Replay mode: run strategy every N bars (1 = every bar, most trades; 4 = faster, may miss some)
REPLAY_STEP_BARS = 1

# AI (OpenAI key from .env OPENAI_API_KEY)
AI_ENABLED = False
AI_CONFIDENCE_THRESHOLD = 2.0  # 1-5 scale; skip trade if confidence below this
AI_EXPLAIN_TRADES = False

# Voice alerts (pyttsx3)
VOICE_ALERTS = False
VOICE_ALERT_ON_SIGNAL = True   # speak when trade found / about to take
VOICE_ALERT_ON_REJECT = True   # speak when trade rejected and why

# Marvellous Strategy (XAUUSD gold, ICT-style with bias + zone validation)
# NOTE: REQUIRE_*_ZONE_CONFIRMATION only applies when that timeframe's REQUIRE_*_BIAS is True.
#       E.g. REQUIRE_4H_ZONE_CONFIRMATION has no effect when REQUIRE_4H_BIAS=False.
MARVELLOUS_INSTRUMENT = 'XAUUSD'
MARVELLOUS_ONE_SIGNAL_PER_SETUP = False  # True = first qualifying bar only (fair 1m vs 5m comparison) # True = one signal per 5M setup (no multiple 1M entries)
MARVELLOUS_REQUIRE_H1_BIAS = True
MARVELLOUS_REQUIRE_4H_BIAS = False
MARVELLOUS_REQUIRE_DAILY_BIAS = False
MARVELLOUS_REQUIRE_H1_ZONE_CONFIRMATION = True   # Only H1 is used when 4H/Daily bias are off
MARVELLOUS_REQUIRE_4H_ZONE_CONFIRMATION = False   # Only used when REQUIRE_4H_BIAS=True
MARVELLOUS_REQUIRE_DAILY_ZONE_CONFIRMATION = False  # Only used when REQUIRE_DAILY_BIAS=True
MARVELLOUS_LOOKBACK_H1_HOURS = 48
MARVELLOUS_LOOKBACK_4H_BARS = 24
MARVELLOUS_LOOKBACK_DAILY_BARS = 10
MARVELLOUS_REACTION_THRESHOLDS = {'wick_pct': 0.5, 'body_pct': 0.3}
MARVELLOUS_BIAS_COMBINATION_METHOD = 'unanimous'
MARVELLOUS_ENABLE_ASIA_SESSION = True   # Asian (Tokyo) session UTC 00:00-04:00
MARVELLOUS_ASIAN_SESSION_HOURS = [0, 1, 2, 3, 4]
MARVELLOUS_ENABLE_LONDON_SESSION = True
MARVELLOUS_ENABLE_NEWYORK_SESSION = True
MARVELLOUS_AVOID_NEWS = True
MARVELLOUS_NEWS_BUFFER_BEFORE_MINUTES = 15
MARVELLOUS_NEWS_BUFFER_AFTER_MINUTES = 15
MARVELLOUS_NEWS_API = 'investpy'
MARVELLOUS_NEWS_COUNTRIES = ['United States', 'Euro Zone']
FCSAPI_KEY = os.getenv('FCSAPI_KEY')  # For FCS API economic calendar fallback
MARVELLOUS_MIN_ATR_THRESHOLD = 0.5
MARVELLOUS_MAX_SPREAD_POINTS = 50.0

MARVELLOUS_USE_LIQUIDITY_MAP = False
MARVELLOUS_LIQUIDITY_ZONE_STRENGTH_THRESHOLD = 0.5
# Entry timeframe: '5m' (default), '15m', or '1m' — precision entry bar after M15 signal
MARVELLOUS_ENTRY_TIMEFRAME = '1m'
MARVELLOUS_BACKTEST_SYMBOL = 'GC=F'
MARVELLOUS_LIVE_SYMBOL = 'XAUUSDm'
MARVELLOUS_SWING_LENGTH = 3
MARVELLOUS_OB_LOOKBACK = 20
MARVELLOUS_LIQ_SWEEP_LOOKBACK = 5
MARVELLOUS_TP_SWING_LOOKAHEAD = 3
MARVELLOUS_ENTRY_WINDOW_HOURS = 8
MARVELLOUS_ENTRY_WINDOW_MINUTES = 60   # Minutes after M15 signal to allow 5m entry (15=strict, 60=more trades)
MARVELLOUS_SL_BUFFER = 1.0
MARVELLOUS_USE_SL_FALLBACK = True
MARVELLOUS_SL_FALLBACK_DISTANCE = 5.0
# SL method: 'OB' = M15 liquidity level (default), 'HYBRID' = swing + ATR buffer (tighter with 1m)
MARVELLOUS_SL_METHOD = 'OB'
MARVELLOUS_SL_ATR_MULT = 1.0   # Buffer = ATR × this (HYBRID only)
MARVELLOUS_SL_MICRO_TF = '1m'  # Micro-structure timeframe: '1m' or '5m' (HYBRID only)

# Extra filters: when True, Marvellous applies news/session/ATR/spread/liquidity filters.
# When False, both skip them. Config comes from MARVELLOUS_* above.
USE_EXTRA_FILTERS = True

# Marvellous symbol: None = gold (GC=F / XAUUSDm). Set to Yahoo symbol (e.g. 'GBPUSD=X') to run on that pair.
MARVELLOUS_SYMBOL = None
# Yahoo ticker -> MT5 symbol for Marvellous live trading
MARVELLOUS_YAHOO_TO_MT5 = {'GC=F': 'XAUUSDm', 'GBPUSD=X': 'GBPUSDm', 'BTC-USD': 'BTCUSDm', '^NDX': 'NAS100m'}


# VesterStrategy: multi-timeframe smart-money (1H bias -> 5M setup -> 1M entry)
VESTER_ONE_SIGNAL_PER_SETUP = False 
VESTER_BACKTEST_SYMBOL = 'GC=F'
VESTER_LIVE_SYMBOL = 'XAUUSDm'
VESTER_YAHOO_TO_MT5 = {'GC=F': 'XAUUSDm', 'GBPUSD=X': 'GBPUSDm', 'BTC-USD': 'BTCUSDm', '^NDX': 'NAS100m'}
# Structure detection
VESTER_SWING_LENGTH = 3
VESTER_OB_LOOKBACK = 20
VESTER_FVG_LOOKBACK = 30
VESTER_LIQUIDITY_LOOKBACK = 5
# HTF bias (1H)
VESTER_HTF_LOOKBACK_HOURS = 48
VESTER_REQUIRE_HTF_ZONE_CONFIRMATION = True  # False = BOS-only bias (more trades)
# 4H confirmation: when True, use 4H. AS_FILTER=True = only block when 4H opposes 1H (allow neutral).
# AS_FILTER=False = gate: require 4H to match 1H (skip when 4H neutral or opposite)
VESTER_REQUIRE_4H_BIAS = True
VESTER_4H_AS_FILTER = True  # True = block only when 4H opposite; False = require 4H to match
VESTER_REQUIRE_4H_ZONE_CONFIRMATION = False
VESTER_4H_LOOKBACK_BARS = 24  # 4H bars to look back (~4 days)
VESTER_REJECTION_WICK_RATIO = 0.5
VESTER_REJECTION_BODY_RATIO = 0.3
# 5M setup window (hours to look back for sweep + BOS + zone)
VESTER_M5_WINDOW_HOURS = 12
# When no 5M FVG/OB found, use liquidity sweep level as entry zone (wider zone = more trades)
VESTER_USE_LIQ_LEVEL_AS_ZONE = True
VESTER_LIQ_ZONE_ATR_MULT = 0.5  # Zone width = ± this * ATR around sweep level
# Allow 1M entry on price-in-zone + same-direction candle (no BOS/displacement required)
VESTER_ALLOW_SIMPLE_ZONE_ENTRY = True
# Require 5M liquidity sweep before entry (False = more trades, sweep optional)
VESTER_REQUIRE_5M_SWEEP = False
# Filters
VESTER_MAX_SPREAD_POINTS = 50.0
VESTER_MAX_CANDLE_VOLATILITY_ATR_MULT = 4.0
VESTER_USE_NEWS_FILTER = False
VESTER_NEWS_BUFFER_MINUTES = 15
# Risk management
VESTER_RISK_PER_TRADE = 0.10
VESTER_MAX_TRADES_PER_SESSION = 2
VESTER_DAILY_LOSS_LIMIT_PCT = 5.0
VESTER_USE_TRAILING_STOP = False
VESTER_MIN_RR = 3.0
# Displacement candle threshold (body vs range ratio)
VESTER_DISPLACEMENT_RATIO = 0.5
VESTER_SL_BUFFER = 1.0
# SL method: 'HYBRID' = micro-structure swing + ATR buffer; 'OB' = OB/zone + fixed pip buffer
VESTER_SL_METHOD = 'OB'
VESTER_SL_ATR_MULT = 1.0  # Buffer = ATR × this (HYBRID only)
VESTER_SL_MICRO_TF = '1m'  # Micro-structure timeframe: '1m' or '5m' (HYBRID only)


# Symbol-specific config overrides. When the bot trades this pair, it uses these values instead of defaults.
# Keys: BACKTEST_SPREAD_PIPS, BACKTEST_SLIPPAGE_PIPS, PIP_SIZE, MARVELLOUS_MIN_ATR_THRESHOLD,
#       MARVELLOUS_SL_BUFFER, MARVELLOUS_SL_FALLBACK_DISTANCE, MARVELLOUS_MAX_SPREAD_POINTS
SYMBOL_CONFIGS = {
    "NAS100m": {
        "BACKTEST_SPREAD_PIPS": 2.5,
        "PIP_SIZE": 1.0,                     # Index points
        "MARVELLOUS_MIN_ATR_THRESHOLD": 40,
    },
}


def cli_symbol_to_mt5(cli_symbol):
    """Map CLI/Yahoo symbol (e.g. 'BTC-USD', 'GC=F') to MT5 symbol for live/paper. Returns None if not resolved."""
    if not cli_symbol:
        return None
    s = str(cli_symbol).strip()
    if s in MARVELLOUS_YAHOO_TO_MT5:
        return MARVELLOUS_YAHOO_TO_MT5[s]
    normalized = s.upper().replace("-", "").replace("=", "").replace("^", "")
    for key, mt5_val in LIVE_SYMBOLS.items():
        if key.upper().replace("M", "") == normalized or key.upper() == normalized:
            return mt5_val
    return None


def _normalize_symbol_for_config(symbol):
    """Map symbol to config key (BTCUSDm, BTC-USD, BTCUSD -> 'BTCUSDm')."""
    if not symbol:
        return None
    s = str(symbol).upper().replace("-", "").replace("=", "").replace("^", "")
    if "BTC" in s and "USD" in s:
        return "BTCUSDm"
    if "XAU" in s or "GC" in s or "GOLD" in s:
        return "XAUUSDm"
    if "NAS" in s or "NDX" in s:
        return "NAS100m"
    return None


def get_symbol_config(symbol, key, default=None):
    """Return symbol-specific config value, or default. Used when pair is BTCUSDm etc."""
    norm = _normalize_symbol_for_config(symbol)
    if norm is None:
        return default
    overrides = SYMBOL_CONFIGS.get(norm)
    if overrides is None:
        overrides = SYMBOL_CONFIGS.get("BTCUSDm") if "BTC" in norm else {}
    if not overrides:
        return default
    val = overrides.get(key)
    if val is not None:
        return val
    return default
