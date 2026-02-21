"""
NAS Judas Strategy configuration.
Optimized for institutional Judas Swing manipulation setups on NAS100.
Trade ONLY after liquidity trap + displacement + confirmation.
"""
import os

try:
    import config
except ImportError:
    config = None


def _get(key, default):
    """Get from config or Judas defaults."""
    if config and hasattr(config, key):
        return getattr(config, key)
    return default


# Instrument
INSTRUMENT = _get("JUDAS_INSTRUMENT", "NAS100")

# Timeframes
ENTRY_TF = _get("JUDAS_ENTRY_TF", "M15")
BIAS_TF = _get("JUDAS_BIAS_TF", "H1")

# Entry sequence thresholds
MIN_SWEEP_POINTS = _get("JUDAS_MIN_SWEEP_POINTS", 35)
MIN_DISPLACEMENT_RATIO = _get("JUDAS_MIN_DISPLACEMENT_RATIO", 1.8)
MIN_FVG_SIZE = _get("JUDAS_MIN_FVG_SIZE", 18)

# Filters
MIN_ATR = _get("JUDAS_MIN_ATR", 45)
MAX_SPREAD = _get("JUDAS_MAX_SPREAD", 2.8)

# Sessions
ENABLE_LONDON = _get("JUDAS_ENABLE_LONDON", True)
ENABLE_NEWYORK = _get("JUDAS_ENABLE_NEWYORK", True)
LONDON_KZ = _get("JUDAS_LONDON_KZ", ("03:00", "05:00"))
NY_KZ = _get("JUDAS_NY_KZ", ("09:30", "11:30"))

# Risk & TP
SL_BUFFER = _get("JUDAS_SL_BUFFER", 8)
RISK_PER_TRADE = _get("JUDAS_RISK_PER_TRADE", 0.5) / 100.0  # 0.5% -> 0.005
TP_MODEL = _get("JUDAS_TP_MODEL", "ladder")

# Symbols
BACKTEST_SYMBOL = _get("JUDAS_BACKTEST_SYMBOL", "^NDX")
LIVE_SYMBOL = _get("JUDAS_LIVE_SYMBOL", "NAS100m")

# Swing / structure
SWING_LENGTH = _get("JUDAS_SWING_LENGTH", 3)
LIQ_SWEEP_LOOKBACK = _get("JUDAS_LIQ_SWEEP_LOOKBACK", 5)
ENTRY_WINDOW_HOURS = _get("JUDAS_ENTRY_WINDOW_HOURS", 8)

# Logging
VERBOSE = _get("JUDAS_VERBOSE", False)
