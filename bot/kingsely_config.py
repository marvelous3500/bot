"""
KingselyStrategy configuration: multi-timeframe smart-money (1H bias -> 5M setup -> 1M entry).
Reads from config.KINGSELY_* with fallback defaults.
"""
try:
    import config
except ImportError:
    config = None

try:
    import sys
    import os
    # Add root to sys.path if not there
    root_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    if root_path not in sys.path:
        sys.path.append(root_path)
    import kingsely_config as root_kc
except ImportError:
    root_kc = None


def _get(key, default):
    """Get from root kingsely_config, then main config, then default."""
    if root_kc and hasattr(root_kc, key):
        return getattr(root_kc, key)
    if config and hasattr(config, key):
        return getattr(config, key)
    return default


# MT5 Credentials
MT5_LOGIN = _get("MT5_LOGIN", None)
MT5_PASSWORD = _get("MT5_PASSWORD", None)
MT5_SERVER = _get("MT5_SERVER", None)

# Telegram (optional)
TELEGRAM_BOT_TOKEN = _get("TELEGRAM_BOT_TOKEN", None)
TELEGRAM_CHAT_ID = _get("TELEGRAM_CHAT_ID", None)
TELEGRAM_ENABLED = _get("TELEGRAM_ENABLED", None)


# Symbols
KINGSELY_BACKTEST_SYMBOL = _get("KINGSELY_BACKTEST_SYMBOL", "GC=F")
KINGSELY_LIVE_SYMBOL = _get("KINGSELY_LIVE_SYMBOL", "XAUUSDm")
KINGSELY_YAHOO_TO_MT5 = _get("KINGSELY_YAHOO_TO_MT5", {"GC=F": "XAUUSDm", "GBPUSD=X": "GBPUSDm", "BTC-USD": "BTCUSDm", "^NDX": "NAS100m"})

# Structure detection
SWING_LENGTH = _get("KINGSELY_SWING_LENGTH", 3)
OB_LOOKBACK = _get("KINGSELY_OB_LOOKBACK", 20)
FVG_LOOKBACK = _get("KINGSELY_FVG_LOOKBACK", 30)
LIQUIDITY_LOOKBACK = _get("KINGSELY_LIQUIDITY_LOOKBACK", 5)

# HTF bias (1H)
HTF_LOOKBACK_HOURS = _get("KINGSELY_HTF_LOOKBACK_HOURS", 48)
REQUIRE_HTF_ZONE_CONFIRMATION = _get("KINGSELY_REQUIRE_HTF_ZONE_CONFIRMATION", False)
REJECTION_WICK_RATIO = _get("KINGSELY_REJECTION_WICK_RATIO", 0.5)
REJECTION_BODY_RATIO = _get("KINGSELY_REJECTION_BODY_RATIO", 0.3)

# 4H confirmation (same logic as 1H)
REQUIRE_4H_BIAS = _get("KINGSELY_REQUIRE_4H_BIAS", False)
H4_AS_FILTER = _get("KINGSELY_4H_AS_FILTER", True)  # True = block only when 4H opposite; False = require match
REQUIRE_4H_ZONE_CONFIRMATION = _get("KINGSELY_REQUIRE_4H_ZONE_CONFIRMATION", True)
H4_LOOKBACK_BARS = _get("KINGSELY_4H_LOOKBACK_BARS", 24)
REQUIRE_BREAKER_BLOCK = _get("KINGSELY_REQUIRE_BREAKER_BLOCK", False)
BREAKER_BLOCK_4H = _get("KINGSELY_BREAKER_BLOCK_4H", False)

# 5M setup window (hours)
M5_WINDOW_HOURS = _get("KINGSELY_M5_WINDOW_HOURS", 12)
USE_LIQ_LEVEL_AS_ZONE = _get("KINGSELY_USE_LIQ_LEVEL_AS_ZONE", True)
LIQ_ZONE_ATR_MULT = _get("KINGSELY_LIQ_ZONE_ATR_MULT", 0.5)
ALLOW_SIMPLE_ZONE_ENTRY = _get("KINGSELY_ALLOW_SIMPLE_ZONE_ENTRY", True)
REQUIRE_5M_SWEEP = _get("KINGSELY_REQUIRE_5M_SWEEP", False)

# Premium/Discount (ICT)
USE_PREMIUM_DISCOUNT = _get("KINGSELY_USE_PREMIUM_DISCOUNT", False)
EQUILIBRIUM_LOOKBACK = _get("KINGSELY_EQUILIBRIUM_LOOKBACK", 24)
EQUILIBRIUM_TF = _get("KINGSELY_EQUILIBRIUM_TF", "H1").upper()  # H1 or 4H

# Filters
MAX_SPREAD_POINTS = _get("KINGSELY_MAX_SPREAD_POINTS", 50.0)
MAX_CANDLE_VOLATILITY_ATR_MULT = _get("KINGSELY_MAX_CANDLE_VOLATILITY_ATR_MULT", 4.0)
USE_NEWS_FILTER = _get("KINGSELY_USE_NEWS_FILTER", False)
NEWS_BUFFER_MINUTES = _get("KINGSELY_NEWS_BUFFER_MINUTES", 15)

# Risk management
RISK_PER_TRADE = _get("KINGSELY_RISK_PER_TRADE", 0.10)
MAX_TRADES_PER_SESSION = _get("KINGSELY_MAX_TRADES_PER_SESSION", 2)
DAILY_LOSS_LIMIT_PCT = _get("KINGSELY_DAILY_LOSS_LIMIT_PCT", 5.0)
USE_TRAILING_STOP = _get("KINGSELY_USE_TRAILING_STOP", False)
MIN_RR = _get("KINGSELY_MIN_RR", 3.0)

# Displacement candle
DISPLACEMENT_RATIO = _get("KINGSELY_DISPLACEMENT_RATIO", 0.5)
SL_BUFFER = _get("KINGSELY_SL_BUFFER", 1.0)
SL_METHOD = _get("KINGSELY_SL_METHOD", "HYBRID")
SL_ATR_MULT = _get("KINGSELY_SL_ATR_MULT", 0.5)
SL_MICRO_TF = _get("KINGSELY_SL_MICRO_TF", "1m")
KINGSELY_ONE_SIGNAL_PER_SETUP = _get("KINGSELY_ONE_SIGNAL_PER_SETUP", True)
KINGSELY_MAX_TRADES_PER_SETUP = _get("KINGSELY_MAX_TRADES_PER_SETUP", None)  # None = unlimited, 1 = one per setup, 3 = up to 3
