# Trading Pairs (Yahoo Finance Tickers) — first is default for backtest/CLI
# GBPUSD=X : GBP/USD (default)
# GC=F : Gold Futures
# BTC-USD : Bitcoin
# ^NDX : Nasdaq 100 Index
SYMBOLS = ['GBPUSD=X', 'GC=F', 'BTC-USD', '^NDX']

# Timeframe settings
TIMEFRAME = '15m'
DAILY_TIMEFRAME = '1d'

# Risk Management
RISK_REWARD_RATIO =3.0  # 1:3 Risk:Reward

# Backtesting
INITIAL_BALANCE = 100
RISK_PER_TRADE = 0.10  # 10% risk per trade
BACKTEST_MAX_TRADES = None  # Stop after N trades (None = no limit)
BACKTEST_PERIOD = '60d'  # Data period: 12d, 60d, 6mo (set before run)

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
MAX_TRADES_PER_DAY = 3
MAX_POSITION_SIZE = 0.10  # Fallback lot size when dynamic calc fails
USE_DYNAMIC_POSITION_SIZING = True  # Risk % of current balance per trade (matches backtest)
PAPER_TRADING_LOG = 'paper_trades.json'

# MT5 Settings (loaded from environment variables for security)
MT5_LOGIN = os.getenv('MT5_LOGIN')  # Your MT5 account number
MT5_PASSWORD = os.getenv('MT5_PASSWORD')  # Your MT5 password
MT5_SERVER = os.getenv('MT5_SERVER', 'Exness-MT5Trial')  # Your Exness MT5 server
# Full path to Exness MetaTrader 5 terminal64.exe (e.g. C:/Program Files/MetaTrader 5 EXNESS/terminal64.exe). Use forward slashes in .env.
MT5_PATH = os.getenv('MT5_PATH')  # None = auto-detect
# When True and MT5_PATH is set, the bot starts Exness MT5 automatically when you run paper/live.
MT5_AUTO_START = os.getenv('MT5_AUTO_START', 'true').lower() in ('true', '1', 'yes')

# Live Trading Symbols (MT5 format) — first is default for paper/live
LIVE_SYMBOLS = {
    'GBPUSD': 'GBPUSD',
    'XAUUSD': 'XAUUSDm',  # Exness gold symbol
    'BTCUSD': 'BTCUSD',
    'NAS100': 'NAS100'
}


# Trading Loop Settings
LIVE_CHECK_INTERVAL = 30  # Seconds between strategy checks
USE_MARGIN_CHECK = True   # Pre-trade margin check for live mode (skip if insufficient free margin)
LIVE_DEBUG = True         # Log when no signals (data range, bar counts) to diagnose why live misses trades

# Confluence strategy: fixed stop loss in pips (4H structure + 15m OB entry)
CONFLUENCE_SL_PIPS = 50

# Liquidity sweep (4H → 1H → 15m): max 1H bars to wait for confirmation after 4H sweep; max 15m bars for entry after 1H confirm
LIQUIDITY_1H_CONFIRM_BARS = 12
LIQUIDITY_15M_ENTRY_BARS = 12
# Liquidity-specific: set False to ignore kill zone / EMA for more trades
LIQUIDITY_USE_KILL_ZONES = True
LIQUIDITY_USE_EMA_FILTER = True
# Require 15m FVG/OB/rejection for entry; False = enter on any 15m candle in direction
LIQUIDITY_REQUIRE_15M_CONFIRM = True
# Require 1H sweep or rejection (not just any candle); True = stricter, fewer but higher-quality trades
LIQUIDITY_STRICT_1H_CONFIRM = True

# H1-M5 BOS: filters to reduce trades and improve win rate
BOS_USE_KILL_ZONES = True   # Only trade during London/NY sessions
BOS_USE_EMA_FILTER = True   # Require price in direction of EMA
BOS_DISPLACEMENT_RATIO = 0.7  # Candle body must be 70% of range (stricter than 0.6)
BOS_M5_WINDOW_HOURS = 2    # Max hours to wait for M5 entry after H1 BOS (was 4)

# Kingsley Gold: H1 trend + 15m BOS/ChoCH + zone→LQ + OB test (XAUUSD/GC=F only)
KINGSLEY_USE_KILL_ZONES = True
KINGSLEY_USE_EMA_FILTER = False
KINGSLEY_15M_WINDOW_HOURS = 8   # Max hours to wait for 15m setup after H1 BOS
KINGSLEY_DISPLACEMENT_RATIO = 0.6
KINGSLEY_BACKTEST_SYMBOL = 'GC=F'   # Yahoo Finance
KINGSLEY_LIVE_SYMBOL = 'XAUUSDm'    # MT5
KINGSLEY_SL_BUFFER = 1.0   # Price units buffer below/above lq_level for live execution (reduces "Stop loss invalid" when market moves)
KINGSLEY_USE_SL_FALLBACK = True   # When True: use fallback SL when live price invalidates lq_level. When False: reject invalid signals.
KINGSLEY_SL_FALLBACK_DISTANCE = 5.0  # Price units for fallback (e.g. $5 for gold). Only used when KINGSLEY_USE_SL_FALLBACK=True.

# Test strategy (gold, verify live execution - takes trade immediately)
TEST_SL_DISTANCE = 5.0   # Price units (e.g. $5 for gold)
TEST_TP_DISTANCE = 15.0  # Price units
TEST_USE_KILL_ZONES = False  # False = always emit, take trade on first run
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
