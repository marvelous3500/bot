"""
Connector interface and factory for live/paper trading.
Uses MT5 only. String timeframes are used by live_trading; MT5 connector maps them to MT5 constants.
"""
# String timeframes used by live_trading (MT5 connector maps these to MT5 constants)
TIMEFRAME_M1 = '1m'
TIMEFRAME_M5 = '5m'
TIMEFRAME_M15 = '15m'
TIMEFRAME_H1 = '1h'
TIMEFRAME_H4 = '4h'
TIMEFRAME_D1 = '1d'


def get_connector(login=None, password=None, server=None):
    """
    Return MT5Connector for live/paper trading.
    Requires MetaTrader 5 (Windows). Raises ImportError if MT5 package is not available.
    """
    try:
        from .mt5_connector import MT5Connector
        return MT5Connector(login=login, password=password, server=server)
    except ImportError as e:
        raise ImportError(
            "MetaTrader5 package is not available on this platform (MT5 is Windows-only). "
            "Run paper/live on a Windows machine or Windows VPS with MT5 installed."
        ) from e
