"""
NAS-STRATEGY configuration for NAS100 (Nasdaq Index).
Optimized for volatility, liquidity behavior, and session characteristics.
"""
import os

try:
    import config
except ImportError:
    config = None


def _get(key, default):
    """Get from config or NAS defaults."""
    if config and hasattr(config, key):
        return getattr(config, key)
    return default


# Instrument
INSTRUMENT = _get("NAS_INSTRUMENT", "NAS100")

# Bias settings
REQUIRE_H1_BIAS = _get("NAS_REQUIRE_H1_BIAS", True)
REQUIRE_4H_BIAS = _get("NAS_REQUIRE_4H_BIAS", False)
REQUIRE_DAILY_BIAS = _get("NAS_REQUIRE_DAILY_BIAS", False)
LOOKBACK_H1_HOURS = _get("NAS_LOOKBACK_H1_HOURS", 48)
LOOKBACK_4H_BARS = _get("NAS_LOOKBACK_4H_BARS", 24)
REACTION_THRESHOLDS = _get("NAS_REACTION_THRESHOLDS", {"wick_pct": 0.5, "body_pct": 0.3})

# Session filter
ENABLE_ASIA = _get("NAS_ENABLE_ASIA", False)
ENABLE_LONDON = _get("NAS_ENABLE_LONDON", True)
ENABLE_NEWYORK = _get("NAS_ENABLE_NEWYORK", True)

# Kill zones (UTC): London 08:00-10:00, NY 14:30-16:30 (EST 09:30-11:30)
LONDON_KZ = _get("NAS_LONDON_KZ", ("08:00", "10:00"))
NY_KZ = _get("NAS_NY_KZ", ("14:30", "16:30"))
TRADE_ONLY_KILLZONES = _get("NAS_TRADE_ONLY_KILLZONES", True)

# Volatility & spread
MIN_ATR = _get("NAS_MIN_ATR", 40)
MAX_SPREAD = _get("NAS_MAX_SPREAD", 2.5)

# Entry sequence thresholds
MIN_SWEEP_POINTS = _get("NAS_MIN_SWEEP_POINTS", 25)
MIN_FVG_SIZE = _get("NAS_MIN_FVG_SIZE", 15)
MAX_FVG_AGE = _get("NAS_MAX_FVG_AGE", 20)

# News filter
AVOID_NEWS = _get("NAS_AVOID_NEWS", True)
NEWS_BUFFER_BEFORE = _get("NAS_NEWS_BUFFER_BEFORE", 20)
NEWS_BUFFER_AFTER = _get("NAS_NEWS_BUFFER_AFTER", 20)
NEWS_COUNTRIES = _get("NAS_NEWS_COUNTRIES", ["United States", "Euro Zone"])
NEWS_API = _get("NAS_NEWS_API", "investpy")
FCSAPI_KEY = _get("FCSAPI_KEY", os.getenv("FCSAPI_KEY"))

# Risk & TP
RISK_PER_TRADE = _get("NAS_RISK_PER_TRADE", 0.005)
TP_MODEL = _get("NAS_TP_MODEL", "ladder")
SL_BUFFER = _get("NAS_SL_BUFFER", 5)

# Symbols
BACKTEST_SYMBOL = _get("NAS_BACKTEST_SYMBOL", "^NDX")
LIVE_SYMBOL = _get("NAS_LIVE_SYMBOL", "NAS100m")

# Swing / structure
SWING_LENGTH = _get("NAS_SWING_LENGTH", 3)
OB_LOOKBACK = _get("NAS_OB_LOOKBACK", 20)
LIQ_SWEEP_LOOKBACK = _get("NAS_LIQ_SWEEP_LOOKBACK", 5)
ENTRY_WINDOW_HOURS = _get("NAS_ENTRY_WINDOW_HOURS", 8)
ENTRY_TIMEFRAME = _get("NAS_ENTRY_TIMEFRAME", "5m")
