# Trading Pairs (Yahoo Finance Tickers) — first is default for backtest/CLI
# GBPUSD=X : GBP/USD (default)
# GC=F : Gold Futures
# BTC-USD : Bitcoin
# ^NDX : Nasdaq 100 Index
SYMBOLS = [ 'GC=F', 'GBPUSD=X', 'BTC-USD', '^NDX']

KINGSLEY_AGGRESSIVE = False  # True = swing=2 + disp=0.5 (more trades, sweep-tuned)
# Generic 4H/Daily bias filters — apply to all strategies that use H1 or 4H
USE_4H_BIAS_FILTER = False   # When True, require 4H bias to match H1/entry timeframe (Kingsley, H1-M5 BOS, etc.)
USE_DAILY_BIAS_FILTER = False  # When True, require Daily bias to match H1/4H (Kingsley, H1-M5 BOS)

TP1_SL_TO_ENTRY_ENABLED = False   # True = move SL to entry when TP1 hit
TP1_RATIO = 0.3   

# Timeframe settings
TIMEFRAME = '15m'
DAILY_TIMEFRAME = '1d'

# Risk Management
RISK_REWARD_RATIO = 3.0  # 1:5 Risk:Reward (win = 5× risk)

# Backtesting
INITIAL_BALANCE = 100
RISK_PER_TRADE = 0.10  # 10% risk per trade
BACKTEST_MAX_TRADES = None  # Stop after N trades (None = no limit)
BACKTEST_PERIOD = '60d'  # Data period: 12d, 60d, 6mo (set before run)
BACKTEST_SPREAD_PIPS = 2.0       # e.g. 2.0 for gold, 1.0 for forex
BACKTEST_COMMISSION_PER_LOT = 7.0  # round-trip per lot (e.g. 7.0)
BACKTEST_SLIPPAGE_PIPS = 0.5     # e.g. 0.5
# Filters
USE_EMA_FILTER = False
EMA_PERIOD = 50 

# Kill Zones (UTC Hour) - Full sessions for better sample size
# London: 07:00 - 10:00  
# NY: 13:00 - 16:00
USE_KILL_ZONES = True
KILL_ZONE_HOURS = [7, 8, 9, 10, 13, 14, 15, 16]

# Advanced Filters for higher win rate  
REQUIRE_BOTH_FVG_AND_OB = False  # FVG OR OB (requiring both is too strict)
USE_DISPLACEMENT_FILTER = False   # Require strong institutional move  
USE_MARKET_STRUCTURE_FILTER = False  # Degraded performance when enabled

# Live Trading Settings
import os
from dotenv import load_dotenv

load_dotenv()  # Load from .env file

LIVE_MODE = True   # True = real money, False = paper trading
MANUAL_APPROVAL = False   # Require confirmation before each trade; False = bot auto-approves (for server/headless)
LIVE_CONFIRM_ON_START = True   # When live: require typing 'yes' before loop starts
MAX_LOT_LIVE = None   # Cap lot size in live mode (safety)
MAX_TRADES_PER_DAY = 6
MAX_TRADES_PER_SESSION = 2   # Per session (London, NY); divides daily limit across sessions
MAX_TRADES_PER_DAY_PER_PAIR = True   # True = limits apply per symbol; False = global (legacy)
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

# H1-M5 BOS: filters to reduce trades and improve win rate
BOS_USE_KILL_ZONES = True   # Only trade during London/NY sessionsf
BOS_USE_EMA_FILTER = True   # Require price in direction of EMA
BOS_DISPLACEMENT_RATIO = 0.7  # Candle body must be 70% of range (stricter than 0.6)
BOS_M5_WINDOW_HOURS = 2    # Max hours to wait for M5 entry after H1 BOS (was 4)

# Generic 4H/Daily bias filters — apply to all strategies that use H1 or 4H
USE_4H_BIAS_FILTER = False   # When True, require 4H bias to match H1/entry timeframe (Kingsley, H1-M5 BOS, etc.)
USE_DAILY_BIAS_FILTER = False  # When True, require Daily bias to match H1/4H (Kingsley, H1-M5 BOS)

# ICT indicator source: False = Kingsley fractal, True = LuxAlgo-style pivot
USE_LUXALGO_ICT = False
LUXALGO_SWING_LENGTH = 5      # Pivot left/right (LuxAlgo default: 5)
LUXALGO_OB_USE_BODY = True   # Use candle body for OB range (LuxAlgo default)

# Kingsley Gold: 4H + H1 trend + 15m BOS/ChoCH + zone→LQ + OB test (XAUUSD/GC=F only)

KINGSLEY_USE_KILL_ZONES = True
KINGSLEY_USE_ASIAN_SESSION = True   # When True, also allow trades during Asian session
KINGSLEY_ASIAN_SESSION_HOURS = [0, 1, 2, 3, 4]   # Tokyo session (UTC): 00:00-04:00
KINGSLEY_USE_EMA_FILTER = False
KINGSLEY_15M_WINDOW_HOURS = 8   # Max hours to wait for 15m setup after H1 BOS
KINGSLEY_DISPLACEMENT_RATIO = 0.6
# Option A fine-tuning (swing detection, liquidity, TP target)
KINGSLEY_SWING_LENGTH = 3        # Fractal lookback: 2=more swings, 5=fewer/cleaner
KINGSLEY_LIQ_SWEEP_LOOKBACK = 5  # Recent swing highs/lows for liquidity sweep
KINGSLEY_TP_SWING_LOOKAHEAD = 3  # Next N swing points for TP target
KINGSLEY_OB_LOOKBACK = 20       # Bars to look back for order block before BOS
KINGSLEY_BACKTEST_SYMBOL = 'GC=F'   # Yahoo Finance
KINGSLEY_LIVE_SYMBOL = 'XAUUSDm'    # MT5
KINGSLEY_SL_BUFFER = 1.0   # Price units buffer below/above lq_level for live execution (reduces "Stop loss invalid" when market moves)
KINGSLEY_USE_SL_FALLBACK = True   # When True: use fallback SL when live price invalidates lq_level. When False: reject invalid signals.
KINGSLEY_SL_FALLBACK_DISTANCE = 5.0  # Price units for fallback (e.g. $5 for gold). Only used when KINGSLEY_USE_SL_FALLBACK=True.
# H1 zone confirmation (Marvellous-style): require FVG/OB zone respected before accepting H1 BOS
KINGSLEY_REQUIRE_H1_ZONE_CONFIRMATION = True
KINGSLEY_H1_ZONE_LOOKBACK_HOURS = 48
KINGSLEY_H1_ZONE_WICK_PCT = 0.5
KINGSLEY_H1_ZONE_BODY_PCT = 0.3

# Test strategy (gold, verify live execution - takes trade immediately)
TEST_SL_DISTANCE = 5.0   # Price units (e.g. $5 for gold)
TEST_TP_DISTANCE = 15.0  # Price units
TEST_USE_KILL_ZONES = False  # False = always emit, take trade on first run
TEST_SINGLE_RUN = True   # True = run once, take one trade, exit (verify bot can execute)
TEST_FIXED_LOT = 0.01    # Fixed lot for test (avoids lot calc issues; 0.01 = min for most brokers)
TEST_BACKTEST_SYMBOL = 'GC=F'
TEST_LIVE_SYMBOL = 'XAUUSDm'

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
MARVELLOUS_ENTRY_TIMEFRAME = '5m'
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

# Extra filters: when True, both Kingsley and Marvellous apply news/session/ATR/spread/liquidity filters.
# When False, both skip them. Config comes from MARVELLOUS_* above.
USE_EXTRA_FILTERS = True

# Marvellous symbol: None = gold (GC=F / XAUUSDm). Set to Yahoo symbol (e.g. 'GBPUSD=X') to run on that pair.
MARVELLOUS_SYMBOL = None
# Yahoo ticker -> MT5 symbol for Marvellous live trading
MARVELLOUS_YAHOO_TO_MT5 = {'GC=F': 'XAUUSDm', 'GBPUSD=X': 'GBPUSDm', 'BTC-USD': 'BTCUSDm', '^NDX': 'NAS100m'}
