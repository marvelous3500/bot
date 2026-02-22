"""
Marvellous Strategy configuration for XAUUSD (gold).
Fully configurable bias validation, session/news/volatility filters, and entry timeframe.
"""
import os

try:
    import config
except ImportError:
    config = None


def _get(key, default):
    """Get from config or marvellous defaults."""
    if config and hasattr(config, key):
        return getattr(config, key)
    return default


# Instrument
INSTRUMENT = _get("MARVELLOUS_INSTRUMENT", "XAUUSD")

# Timeframe bias settings
REQUIRE_H1_BIAS = _get("MARVELLOUS_REQUIRE_H1_BIAS", True)
REQUIRE_4H_BIAS = _get("MARVELLOUS_REQUIRE_4H_BIAS", False)
REQUIRE_DAILY_BIAS = _get("MARVELLOUS_REQUIRE_DAILY_BIAS", False)
REQUIRE_H1_ZONE_CONFIRMATION = _get("MARVELLOUS_REQUIRE_H1_ZONE_CONFIRMATION", True)
REQUIRE_4H_ZONE_CONFIRMATION = _get("MARVELLOUS_REQUIRE_4H_ZONE_CONFIRMATION", True)
REQUIRE_DAILY_ZONE_CONFIRMATION = _get("MARVELLOUS_REQUIRE_DAILY_ZONE_CONFIRMATION", True)
LOOKBACK_H1_HOURS = _get("MARVELLOUS_LOOKBACK_H1_HOURS", 48)
LOOKBACK_4H_BARS = _get("MARVELLOUS_LOOKBACK_4H_BARS", 24)
LOOKBACK_DAILY_BARS = _get("MARVELLOUS_LOOKBACK_DAILY_BARS", 10)
REACTION_THRESHOLDS = _get(
    "MARVELLOUS_REACTION_THRESHOLDS",
    {"wick_pct": 0.5, "body_pct": 0.3},
)
BIAS_COMBINATION_METHOD = _get("MARVELLOUS_BIAS_COMBINATION_METHOD", "unanimous")

# Session filter settings
ENABLE_ASIA_SESSION = _get("MARVELLOUS_ENABLE_ASIA_SESSION", True)
ASIAN_SESSION_HOURS = _get("MARVELLOUS_ASIAN_SESSION_HOURS", [0, 1, 2, 3, 4])
ENABLE_LONDON_SESSION = _get("MARVELLOUS_ENABLE_LONDON_SESSION", True)
ENABLE_NEWYORK_SESSION = _get("MARVELLOUS_ENABLE_NEWYORK_SESSION", True)

# News filter settings
AVOID_NEWS = _get("MARVELLOUS_AVOID_NEWS", True)
NEWS_BUFFER_BEFORE_MINUTES = _get("MARVELLOUS_NEWS_BUFFER_BEFORE_MINUTES", 15)
NEWS_BUFFER_AFTER_MINUTES = _get("MARVELLOUS_NEWS_BUFFER_AFTER_MINUTES", 15)
MARVELLOUS_NEWS_API = _get("MARVELLOUS_NEWS_API", "investpy")
MARVELLOUS_NEWS_COUNTRIES = _get(
    "MARVELLOUS_NEWS_COUNTRIES",
    ["United States", "Euro Zone"],
)
FCSAPI_KEY = _get("FCSAPI_KEY", os.getenv("FCSAPI_KEY"))

# Volatility & spread filter settings
MIN_ATR_THRESHOLD = _get("MARVELLOUS_MIN_ATR_THRESHOLD", 0.5)
MAX_SPREAD_POINTS = _get("MARVELLOUS_MAX_SPREAD_POINTS", 50.0)

# Liquidity map filter settings
USE_LIQUIDITY_MAP = _get("MARVELLOUS_USE_LIQUIDITY_MAP", True)
LIQUIDITY_ZONE_STRENGTH_THRESHOLD = _get(
    "MARVELLOUS_LIQUIDITY_ZONE_STRENGTH_THRESHOLD", 0.5
)

# Entry timeframe: "5m" (default), "15m", or "1m" — precision entry bar after M15 signal
ENTRY_TIMEFRAME = _get("MARVELLOUS_ENTRY_TIMEFRAME", "5m")

# Backtest / live symbols — MARVELLOUS_SYMBOL overrides when set (Yahoo ticker); None = gold
def _resolve_marvellous_symbols():
    override = _get("MARVELLOUS_SYMBOL", None)
    if override:
        backtest = override
        yahoo_to_mt5 = _get("MARVELLOUS_YAHOO_TO_MT5", {})
        live = yahoo_to_mt5.get(override)
        if not live and config:
            live_syms = getattr(config, "LIVE_SYMBOLS", {})
            key = override.replace("=X", "").replace("-", "").replace("^", "")
            if key == "GC":
                live = live_syms.get("XAUUSD", "XAUUSDm")
            elif key == "NDX":
                live = live_syms.get("NAS100", "NAS100m")
            elif key in live_syms:
                live = live_syms[key]
            else:
                live = live_syms.get(key, "XAUUSDm")
        return backtest, live or "XAUUSDm"
    return _get("MARVELLOUS_BACKTEST_SYMBOL", "GC=F"), _get("MARVELLOUS_LIVE_SYMBOL", "XAUUSDm")


MARVELLOUS_BACKTEST_SYMBOL, MARVELLOUS_LIVE_SYMBOL = _resolve_marvellous_symbols()

# Swing detection
MARVELLOUS_SWING_LENGTH = _get("MARVELLOUS_SWING_LENGTH", 3)
MARVELLOUS_OB_LOOKBACK = _get("MARVELLOUS_OB_LOOKBACK", 20)
MARVELLOUS_LIQ_SWEEP_LOOKBACK = _get("MARVELLOUS_LIQ_SWEEP_LOOKBACK", 5)
MARVELLOUS_TP_SWING_LOOKAHEAD = _get("MARVELLOUS_TP_SWING_LOOKAHEAD", 3)
MARVELLOUS_ENTRY_WINDOW_HOURS = _get("MARVELLOUS_ENTRY_WINDOW_HOURS", 8)
MARVELLOUS_ENTRY_WINDOW_MINUTES = _get("MARVELLOUS_ENTRY_WINDOW_MINUTES", 15)
MARVELLOUS_ONE_SIGNAL_PER_SETUP = _get("MARVELLOUS_ONE_SIGNAL_PER_SETUP", True)
MARVELLOUS_MAX_TRADES_PER_SETUP = _get("MARVELLOUS_MAX_TRADES_PER_SETUP", None)  # None = unlimited, 1 = one per setup, 3 = up to 3

# SL buffer (gold)
MARVELLOUS_SL_BUFFER = _get("MARVELLOUS_SL_BUFFER", 1.0)
MARVELLOUS_USE_SL_FALLBACK = _get("MARVELLOUS_USE_SL_FALLBACK", True)
MARVELLOUS_SL_FALLBACK_DISTANCE = _get("MARVELLOUS_SL_FALLBACK_DISTANCE", 5.0)
# SL method: OB = M15 lq_level, HYBRID = swing + ATR buffer (tighter with 1m entry)
MARVELLOUS_SL_METHOD = _get("MARVELLOUS_SL_METHOD", "OB")
MARVELLOUS_SL_ATR_MULT = _get("MARVELLOUS_SL_ATR_MULT", 1.0)
MARVELLOUS_SL_MICRO_TF = _get("MARVELLOUS_SL_MICRO_TF", "1m")
