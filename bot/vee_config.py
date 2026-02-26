"""
VeeStrategy configuration: 1H bias -> 15M setup -> 1M entry (AMN / vee).
Reads from config.VEE_* with fallback defaults.
"""

try:
    import config  # type: ignore
except ImportError:
    config = None


def _get(key, default):
    """Get from config or vee defaults."""
    if config and hasattr(config, key):
        return getattr(config, key)
    return default


# Symbols
VEE_BACKTEST_SYMBOL = _get("VEE_BACKTEST_SYMBOL", "GC=F")
VEE_LIVE_SYMBOL = _get("VEE_LIVE_SYMBOL", "XAUUSDm")

# Structure detection
SWING_LENGTH = _get("VEE_SWING_LENGTH", 3)
OB_LOOKBACK = _get("VEE_OB_LOOKBACK", 20)
LIQUIDITY_LOOKBACK = _get("VEE_LIQUIDITY_LOOKBACK", 5)

# HTF bias (1H)
HTF_LOOKBACK_HOURS = _get("VEE_HTF_LOOKBACK_HOURS", 48)

# M15 setup window (hours)
M15_WINDOW_HOURS = _get("VEE_M15_WINDOW_HOURS", 12)

# SL buffer beyond OB (points, e.g. gold ~2 = $2)
SL_BUFFER_POINTS = _get("VEE_SL_BUFFER_POINTS", 2.0)

# Premium/Discount (optional)
USE_PREMIUM_DISCOUNT = _get("VEE_USE_PREMIUM_DISCOUNT", False)
EQUILIBRIUM_LOOKBACK = _get("VEE_EQUILIBRIUM_LOOKBACK", 24)

# Filters
MAX_SPREAD_POINTS = _get("VEE_MAX_SPREAD_POINTS", 50.0)

# Risk management
RISK_PER_TRADE = _get("VEE_RISK_PER_TRADE", 0.10)
MAX_TRADES_PER_SESSION = _get("VEE_MAX_TRADES_PER_SESSION", 5)
MIN_RR = _get("VEE_MIN_RR", 3.0)

