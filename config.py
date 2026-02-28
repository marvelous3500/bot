#VESTER_REQUIRE_HTF_ZONE_CONFIRMATION = False  # False = BOS-only bias (more trades) (key)
SYMBOLS = [ 'GC=F', 'GBPUSD=X', 'BTC-USD', '^NDX']

LIVE_MODE = True   # True = real money, False = paper trading
MAX_TRADES_PER_DAY_PER_PAIR = False   # True = limits apply per symbol; False = global (legacy)

MAX_TRADES_PER_DAY = 9
MAX_TRADES_PER_SESSION = 3 

MANUAL_APPROVAL = False   # Require confirmation before each trade; False = bot auto-approves (for server/headless)
LIVE_CONFIRM_ON_START = True   # When live: require typing 'yes' before loop starts
MAX_LOT_LIVE = None  # Cap lot size in live mode (safety). 0.02 = ~6% risk on $140 gold.
MAX_RISK_PCT_LIVE = 0.10   # Never risk more than this % of balance (safety net if broker tick_value wrong)
  # Per session (London, NY); divides daily limit across sessions
# Session hours (UTC) for per-session limit: London 7-10, NY 13-16, Asian 0-4
TRADE_SESSION_HOURS = {
    7: 'london', 8: 'london', 9: 'london', 10: 'london',
    13: 'ny', 14: 'ny', 15: 'ny', 16: 'ny',
    0: 'asian', 1: 'asian', 2: 'asian', 3: 'asian', 4: 'asian',
}

MAX_POSITION_SIZE = 0.02  # Fixed lot when gold uses manual; fallback when calc fails
USE_DYNAMIC_POSITION_SIZING = True   # True = risk-based for non-gold; gold uses manual when GOLD_USE_MANUAL_LOT=True
GOLD_USE_MANUAL_LOT = False   # Gold (XAUUSDm etc): use MAX_POSITION_SIZE; other pairs: risk-based sizing
# Gold manual: fixed SL distance (points). 5.0 points = 50 pips = $10 risk with 0.02 lots

GOLD_MANUAL_SL_POINTS = 5.0
PAPER_TRADING_LOG = 'paper_trades.json'
LIVE_TRADE_LOG = True   # Append trades to logs/trades_YYYYMMDD.json
# Risk Management
RISK_REWARD_RATIO = 5.0  # 1:5 Risk:Reward (TP = 5× risk)
# Breakeven: move SL to entry when price reaches BREAKEVEN_TRIGGER_RR (e.g. 1R)
BREAKEVEN_ENABLED = True
BREAKEVEN_TRIGGER_RR = 1.0   # Move SL to entry when price reaches this (1R = 1× SL dist in profit)
# Lock-in: when price reaches LOCK_IN_TRIGGER_RR, move SL to LOCK_IN_AT_RR (e.g. 3.3R trigger → SL to 3R)
LOCK_IN_ENABLED = True
LOCK_IN_TRIGGER_RR = 3.3   # When price reaches this (e.g. 3.3× SL dist), activate lock-in
LOCK_IN_AT_RR = 3.0       # Move SL to this level (e.g. 3R = lock in 3× profit)
# Trailing SL: after price moves in favor by ACTIVATION_R, trail SL by DISTANCE (only tightens, never loosens)
TRAILING_SL_ENABLED = False
TRAILING_SL_ACTIVATION_R = 1.0   # Start trailing after price reaches this R in profit
TRAILING_SL_DISTANCE_PIPS = 20.0  # Trail SL this many pips behind price (or use TRAILING_SL_ATR_MULT)
TRAILING_SL_ATR_MULT = None       # If set, trail distance = ATR * this (overrides PIPS when set)
# Partial TP: close part of position at TP1, rest runs to TP2/SL
PARTIAL_TP_ENABLED = False
PARTIAL_TP_TP1_R = 1.5           # First target in R (e.g. 1.5R)
PARTIAL_TP_TP2_R = 3.0           # Second target in R (final TP from strategy used if larger)
PARTIAL_TP_CLOSE_PCT = 50        # Close this % of position at TP1 (e.g. 50 = half)
# Entry: retry and slippage (market orders)
ENTRY_RETRY_COUNT = 2            # Retry order up to this many times on failure (0 = no retry)
ENTRY_RETRY_DELAY_SEC = 1        # Seconds between retries
ENTRY_SLIPPAGE_PIPS = 3.0        # Max slippage in pips for market order (MT5 deviation)
MAX_SL_PIPS = 50        # Max SL distance in pips for all pairs (converted per symbol's pip size)
DAILY_LOSS_LIMIT_PCT = 1.0 # Stop new trades when today's closed P&L loss >= balance × this %
ENABLE_DAILY_LOSS_LIMIT = False # Toggle daily loss limit safety check
# Backtesting
BACKTEST_EXCLUDE_WEEKENDS = True
INITIAL_BALANCE = 100
RISK_PER_TRADE = 0.10  # 10% risk per trade
BACKTEST_MAX_TRADES = None  # Stop after N trades (None = no limit)
BACKTEST_APPLY_TRADE_LIMITS = True  # When True, apply trade limits in backtest (both strategies)
BACKTEST_MAX_TRADES_PER_DAY = 9  # Backtest daily limit (used when BACKTEST_APPLY_TRADE_LIMITS=True)
BACKTEST_MAX_TRADES_PER_SESSION = 3  # Backtest session limit (used when BACKTEST_APPLY_TRADE_LIMITS=True)
BACKTEST_APPLY_SIGNAL_MAX_AGE = True  # When True, reject backtest entries where (entry_time - signal_time) > strategy's SIGNAL_MAX_AGE_MINUTES
# Confirmed BOS (real vs fake): confirm on entry TF (1m). When True, skip entry if any 1m bar after BOS closed back through the broken level.
VESTER_USE_CONFIRMED_BOS_ONLY = False
VEE_USE_CONFIRMED_BOS_ONLY = False

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
MT5_MAGIC_NUMBER = int(os.getenv('MT5_MAGIC_NUMBER', '234000'))  # Unique ID for orders; essential for copy trading identifiers
# Connection retries and logging
MT5_CONNECT_RETRIES = 5       # Max attempts for initialize + login
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
LIVE_CHECK_INTERVAL = 5  # Seconds between strategy checks
# Live only: consider only the last N bars (1 = current bar only, best practice). None = full history (backtest)
VESTER_LIVE_ONLY_LAST_N_BARS =8
VEE_LIVE_ONLY_LAST_N_BARS =8
# Backtest only: max minutes between setup bar and entry bar (used when BACKTEST_APPLY_SIGNAL_MAX_AGE=True)
VESTER_SIGNAL_MAX_AGE_MINUTES = 3
VEE_SIGNAL_MAX_AGE_MINUTES = 10
SKIP_WHEN_MARKET_CLOSED = True   # When True, skip strategy run and execution on weekend or when symbol trade_mode is disabled
PRINT_CHECKLIST_ON_START = True  # When True, print real-money checklist at live startup (paper mode: no)
USE_MARGIN_CHECK = True   # Pre-trade margin check for live mode (skip if insufficient free margin)
LIVE_DEBUG = True         # Log when no signals (data range, bar counts) to diagnose why live misses trades
# Same symbol: do not take a new trade if we already have an open position on that pair, except when adding at TP1/TP2
ALLOW_MULTIPLE_SAME_SYMBOL = True  # If True, allow multiple positions on same symbol (skips same-symbol check)
ALLOW_SAME_SYMBOL_AT_TP = True   # If True, allow new entry on same symbol only when price is at/near existing position's TP (ignored if ALLOW_MULTIPLE_SAME_SYMBOL=True)
AT_TP_POINTS = 5.0               # Consider "at TP" when entry price is within this many points of position's TP (e.g. 5 for XAUUSD)

# Bias of the day (ICT-style): show Daily + H1 BOS bias in live loop when True
SHOW_BIAS_OF_DAY = True          # If True, print [BIAS OF DAY] Daily: X | H1: Y each cycle

# ICT indicator source: False = Kingsley fractal, True = LuxAlgo-style pivot (used by strategies via indicators_bos)
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
# Extra filters (news/session/ATR/spread when enabled in strategies)
USE_EXTRA_FILTERS = True

# Zone-direction filter: don't buy into Buyside liquidity (bearish FVG/supply), don't sell into Sellside (bullish FVG/demand).
USE_ZONE_DIRECTION_FILTER = True
ZONE_DIRECTION_FVG_LOOKBACK = 20
ZONE_DIRECTION_BUFFER_PCT = 0.001
ZONE_DIRECTION_USE_EQUILIBRIUM = False # False = only FVG zones (looser); True = also block by Premium/Discount


# VesterStrategy: multi-timeframe smart-money (1H bias -> 5M setup -> 1M entry)
VESTER_ONE_SIGNAL_PER_SETUP = True  # Deprecated: use VESTER_MAX_TRADES_PER_SETUP
VESTER_MAX_TRADES_PER_SETUP = 2    # Max entries per 5M setup (1 = one per setup, avoids cluster losses)
VESTER_MAX_TRADES_PER_SL_LEVEL = 1  # Max entries per unique SL level (1 = avoid multiple trades sharing same SL/zone)

VESTER_BACKTEST_SYMBOL = 'GC=F'
VESTER_LIVE_SYMBOL = 'XAUUSDm'
VESTER_YAHOO_TO_MT5 = {'GC=F': 'XAUUSDm', 'GBPUSD=X': 'GBPUSDm', 'GBPJPY=X': 'GBPJPYm', 'BTC-USD': 'BTCUSDm', '^NDX': 'NAS100m'}
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
VESTER_REQUIRE_4H_BIAS = False
VESTER_4H_AS_FILTER = False  # True = block only when 4H opposite; False = require 4H to match
VESTER_REQUIRE_4H_ZONE_CONFIRMATION = False
VESTER_4H_LOOKBACK_BARS = 24  # 4H bars to look back (~4 days)
# Breaker block: failed OB that aligns with bias; used as HTF filter, not entry
VESTER_REQUIRE_BREAKER_BLOCK = False
VESTER_BREAKER_BLOCK_4H = False  # When REQUIRE_4H_BIAS=True, also require breaker on 4H
# H1 liquidity sweep as confirmation (PDH, PDL, session high/low, internal LQ). False = current behaviour; set True to require.
VESTER_REQUIRE_H1_LIQUIDITY_SWEEP = True
VESTER_H1_LQ_USE_PDH_PDL = True
VESTER_H1_LQ_USE_SESSION = True
VESTER_H1_LQ_USE_INTERNAL = True
VESTER_H1_LQ_INTERNAL_LOOKBACK = 10
VESTER_REJECTION_WICK_RATIO = 0.5
VESTER_REJECTION_BODY_RATIO = 0.3
# 5M setup window (hours to look back for sweep + BOS + zone)
VESTER_M5_WINDOW_HOURS = 12
# When no 5M FVG/OB found, use liquidity sweep level as entry zone (wider zone = more trades)
VESTER_USE_LIQ_LEVEL_AS_ZONE = True
VESTER_LIQ_ZONE_ATR_MULT = 0.5  # Zone width = ± this * ATR around sweep level
# Allow 1M entry on price-in-zone + same-direction candle (no BOS/displacement required). False = require 1M BOS or sweep+displacement (fewer, higher-quality entries).
VESTER_ALLOW_SIMPLE_ZONE_ENTRY = True
# Require 5M liquidity sweep before entry (False = more trades, sweep optional)
VESTER_REQUIRE_5M_SWEEP = False
# Premium/Discount (ICT): only buy in discount, sell in premium. False = disabled.
VESTER_USE_PREMIUM_DISCOUNT = False
VESTER_EQUILIBRIUM_LOOKBACK = 24   # Bars for range (H1=24h, 4H=~4 days)
VESTER_EQUILIBRIUM_TF = 'H1'       # H1 or 4H (Vester has no daily data)
# Filters
VESTER_MAX_SPREAD_POINTS = 50.0
VESTER_MAX_CANDLE_VOLATILITY_ATR_MULT = 4.0
VESTER_USE_NEWS_FILTER = True
VESTER_NEWS_BUFFER_MINUTES = 15
# Risk management
VESTER_RISK_PER_TRADE = 0.10
VESTER_MAX_TRADES_PER_SESSION = 3
VESTER_DAILY_LOSS_LIMIT_PCT = 1.0
VESTER_USE_TRAILING_STOP = True
VESTER_MIN_RR = 3.0
# Displacement candle threshold (body vs range ratio)
VESTER_DISPLACEMENT_RATIO = 0.5
VESTER_SL_BUFFER = 1.0
# Minimum SL distance in pips (avoids ultra-tight SL that gets hit by spread/noise). Gold: 5 pips = 0.05; forex: 5 pips = 0.0005.
VESTER_MIN_SL_PIPS = 5.0
# SL method: 'HYBRID' = micro-structure swing + ATR buffer; 'OB' = OB/zone + fixed pip buffer
VESTER_SL_METHOD = 'OB'
VESTER_SL_ATR_MULT = 1.0  # Buffer = ATR × this (HYBRID only)
VESTER_SL_MICRO_TF = '1m'  # Micro-structure timeframe: '1m' or '5m' (HYBRID only)


# TrendVesterStrategy: H1 trend (BOS only) + vester 1M entry. No H1 zone/sweep, no 5M sweep required — more signals.
TREND_VESTER_BACKTEST_SYMBOL = 'GC=F'
TREND_VESTER_LIVE_SYMBOL = 'XAUUSDm'
TREND_VESTER_MAX_TRADES_PER_SETUP = 3
TREND_VESTER_MAX_TRADES_PER_SESSION = 5
TREND_VESTER_LIVE_ONLY_LAST_N_BARS = 3

# VeeStrategy: 1H bias -> 15m CHOCH -> OB+FVG -> entry on return to OB zone; SL beyond OB, TP 3R
VEE_BACKTEST_SYMBOL = 'GC=F'
VEE_LIVE_SYMBOL = 'XAUUSDm'
VEE_RISK_PER_TRADE = 0.10
VEE_MAX_TRADES_PER_SESSION = 5
VEE_MAX_TRADES_PER_SETUP = 1    # Max entries per 15m CHOCH/OB setup (1 = one trade per zone)
VEE_MAX_TRADES_PER_SL_LEVEL = 1  # Max entries per unique SL level (1 = avoid multiple trades sharing same SL/zone)
VEE_MIN_RR = 3.0
VEE_SWING_LENGTH = 3
VEE_OB_LOOKBACK = 20
VEE_HTF_LOOKBACK_HOURS = 48
# H1 liquidity sweep as confirmation (PDH, PDL, session high/low, internal). False = current behaviour.
VEE_REQUIRE_H1_LIQUIDITY_SWEEP = False
VEE_H1_LQ_USE_PDH_PDL = True
VEE_H1_LQ_USE_SESSION = True
VEE_H1_LQ_USE_INTERNAL = True
VEE_H1_LQ_INTERNAL_LOOKBACK = 10
VEE_USE_PREMIUM_DISCOUNT = False
VEE_ENTRY_WINDOW_MINUTES = 120   # Minutes after 15m CHOCH to allow entry (120 = more trades)
VEE_SL_BUFFER_POINTS = 2.0
VEE_USE_1M_CONFIRMATION = False   # Require 1m BOS or FVG in zone for entry
VEE_1M_REQUIRE_BOS_ONLY = True   # False = BOS or FVG (more trades); True = BOS only (fewer, stricter)
VEE_ALLOWED_SESSIONS = []        # [] = all sessions (more trades); ["ny","london"] = fewer, higher quality
# Vee breakeven/lock-in (live/paper)
VEE_BREAKEVEN_TRIGGER_RR = 1.5   # Move SL to entry when price reaches this many R
VEE_LOCK_IN_TRIGGER_RR = 3.3    # When price reaches this R, activate lock-in
VEE_LOCK_IN_AT_RR = 3.0         # Move SL to this R (lock in profit)



# Symbol-specific config overrides. When the bot trades this pair, it uses these values instead of defaults.
# Keys: BACKTEST_SPREAD_PIPS, BACKTEST_SLIPPAGE_PIPS, PIP_SIZE, etc.
SYMBOL_CONFIGS = {
    "NAS100m": {
        "BACKTEST_SPREAD_PIPS": 2.5,
        "PIP_SIZE": 1.0,                     # Index points
    },
    # Gold: 1 lot = 100 oz, $1 move = $100 per 1 lot. Override when broker tick_value is wrong.
    # VESTER_MIN_SL_PIPS: 50 = minimum 50 pips SL distance (0.50 in price) so ultra-tight SLs are widened.
    "XAUUSDm": {"LOSS_PER_LOT_PER_POINT": 100, "VESTER_MIN_SL_PIPS": 50},
    "XAUUSD": {"LOSS_PER_LOT_PER_POINT": 100, "VESTER_MIN_SL_PIPS": 50},
}


def cli_symbol_to_mt5(cli_symbol):
    """Map CLI/Yahoo symbol (e.g. 'BTC-USD', 'GC=F') to MT5 symbol for live/paper. Returns None if not resolved."""
    if not cli_symbol:
        return None
    s = str(cli_symbol).strip()
    if s in VESTER_YAHOO_TO_MT5:
        return VESTER_YAHOO_TO_MT5[s]
    normalized = s.upper().replace("-", "").replace("=", "").replace("^", "")
    for key, mt5_val in LIVE_SYMBOLS.items():
        if key.upper().replace("M", "") == normalized or key.upper() == normalized:
            return mt5_val
    return None


def is_gold_symbol(symbol):
    """Return True if symbol is gold (XAUUSD, XAUUSDm, GC=F, etc.)."""
    if not symbol:
        return False
    s = str(symbol).upper()
    return "XAU" in s or "GC" in s or "GOLD" in s


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
