"""
Connector interface and factory for live/paper trading.
Use string timeframes so both MT5 (Windows) and MetaApi (Mac/Linux) connectors work.
"""
# String timeframes used by live_trading and both connectors (MetaApi uses these directly; MT5 maps to constants)
TIMEFRAME_M1 = '1m'
TIMEFRAME_M5 = '5m'
TIMEFRAME_M15 = '15m'
TIMEFRAME_H1 = '1h'
TIMEFRAME_H4 = '4h'
TIMEFRAME_D1 = '1d'


def get_connector(login=None, password=None, server=None):
    """
    Return the appropriate connector for the current platform/config.
    - If USE_METAAPI is True and METAAPI_TOKEN is set: return MetaApiConnector (works on Mac/Linux/Windows).
    - Else if MetaTrader5 is available: return MT5Connector (Windows only).
    - Else: return MetaApiConnector if token set, else raise with clear message.
    """
    import config
    use_metaapi = getattr(config, 'USE_METAAPI', False)
    token = getattr(config, 'METAAPI_TOKEN', None)

    if use_metaapi and token:
        from .metaapi_connector import MetaApiConnector
        return MetaApiConnector(login=login, password=password, server=server, token=token)
    try:
        from .mt5_connector import MT5Connector
        return MT5Connector(login=login, password=password, server=server)
    except ImportError:
        if token:
            from .metaapi_connector import MetaApiConnector
            return MetaApiConnector(login=login, password=password, server=server, token=token)
        raise ImportError(
            "MetaTrader5 package is not available on this platform (e.g. Mac/Linux). "
            "Set USE_METAAPI=True and METAAPI_TOKEN in .env to use MetaApi cloud connector. "
            "Get a token at https://app.metaapi.cloud/token"
        ) from None
