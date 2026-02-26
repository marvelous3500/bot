"""
V1 Strategy configuration: 4H Bias (FVG/OB/Sweep) -> 15M Confirmation (FVG/OB) -> Retest Entry.
Reads from config.V1_* with fallback defaults.
"""
try:
    import config
except ImportError:
    config = None


def _get(key, default):
    """Get from config or V1 defaults."""
    if config and hasattr(config, key):
        return getattr(config, key)
    return default


# Symbols
V1_BACKTEST_SYMBOL = _get("V1_BACKTEST_SYMBOL", "GC=F")
V1_LIVE_SYMBOL = _get("V1_LIVE_SYMBOL", "XAUUSDz")

# 4H Bias Zone settings
V1_HTF_LOOKBACK_BARS = _get("V1_HTF_LOOKBACK_BARS", 50)  # Bars to look back for FVG/OB
V1_LIQUIDITY_LOOKBACK = _get("V1_LIQUIDITY_LOOKBACK", 20)  # For PDH/PDL sweeps

# 15M Confirmation settings
V1_CONFIRMATION_LOOKBACK = _get("V1_CONFIRMATION_LOOKBACK", 48)  # ~12 hours of 15m bars

# Risk management
V1_RISK_PER_TRADE = _get("V1_RISK_PER_TRADE", 0.10)
V1_MIN_RR = _get("V1_MIN_RR", 3.0)
V1_MAX_TRADES_PER_SESSION = _get("V1_MAX_TRADES_PER_SESSION", 3)

# Filter settings
V1_USE_NEWS_FILTER = _get("V1_USE_NEWS_FILTER", True)
V1_MAX_SPREAD_POINTS = _get("V1_MAX_SPREAD_POINTS", 50.0)
