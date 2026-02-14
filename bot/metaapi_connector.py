"""
MetaApi cloud connector: same interface as MT5Connector for Mac/Linux/Windows.
Uses MetaApi REST API (no local MT5 required). Set USE_METAAPI=True and METAAPI_TOKEN, METAAPI_ACCOUNT_ID in .env.
Get token at https://app.metaapi.cloud/token and add your MT5 account at https://app.metaapi.cloud/accounts to get account ID.
"""
import pandas as pd
from datetime import datetime
import time

try:
    import requests
except ImportError:
    requests = None


# MetaApi uses different base URLs for trading vs market data; region from token or env
def _client_base(config_region=None):
    region = config_region or "new-york"
    return f"https://mt-client-api-v1.{region}.agiliumtrade.ai"


def _market_data_base(config_region=None):
    region = config_region or "new-york"
    return f"https://mt-market-data-client-api-v1.{region}.agiliumtrade.ai"


class MetaApiConnector:
    """Implements same interface as MT5Connector using MetaApi REST API."""

    def __init__(self, login=None, password=None, server=None, token=None, account_id=None):
        import config
        self.login = login or config.MT5_LOGIN
        self.password = password or config.MT5_PASSWORD
        self.server = server or config.MT5_SERVER
        self.token = token or getattr(config, 'METAAPI_TOKEN', None)
        self.account_id = account_id or getattr(config, 'METAAPI_ACCOUNT_ID', None)
        self.region = getattr(config, 'METAAPI_REGION', None) or "new-york"
        self.connected = False
        self._session = None

    def _headers(self):
        return {"auth-token": self.token, "Accept": "application/json", "Content-Type": "application/json"}

    def _get(self, url, params=None, timeout=30):
        if requests is None:
            raise ImportError("MetaApi connector requires 'requests'. pip install requests")
        r = requests.get(url, headers=self._headers(), params=params, timeout=timeout)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def _post(self, url, json_data, timeout=30):
        if requests is None:
            raise ImportError("MetaApi connector requires 'requests'. pip install requests")
        r = requests.post(url, headers=self._headers(), json=json_data, timeout=timeout)
        if r.status_code in (400, 404):
            return None
        r.raise_for_status()
        return r.json()

    def connect(self):
        if not self.token or not self.token.strip():
            print("MetaApi: METAAPI_TOKEN not set in .env")
            return False
        if not self.account_id or not str(self.account_id).strip():
            print("MetaApi: METAAPI_ACCOUNT_ID not set. Add your MT5 account at https://app.metaapi.cloud/accounts and set the account ID in .env")
            return False
        # Verify we can read account info
        info = self.get_account_info()
        if info is None:
            print("MetaApi: Could not reach account (check token, account ID, and that account is deployed).")
            return False
        self.connected = True
        print(f"Connected to MetaApi account {self.account_id} (balance: {info['balance']:.2f} {info.get('currency', 'USD')})")
        return True

    def disconnect(self):
        self.connected = False
        print("Disconnected from MetaApi")

    def get_account_info(self):
        if not self.token or not self.account_id:
            return None
        base = _client_base(self.region)
        url = f"{base}/users/current/accounts/{self.account_id}/account-information"
        try:
            data = self._get(url)
        except Exception:
            return None
        if not data:
            return None
        return {
            'balance': float(data.get('balance', 0)),
            'equity': float(data.get('equity', 0)),
            'margin': float(data.get('margin', 0)),
            'free_margin': float(data.get('freeMargin', 0)),
            'profit': float(data.get('equity', 0)) - float(data.get('balance', 0)),
            'currency': data.get('currency', 'USD')
        }

    def calc_required_margin(self, symbol, order_type, volume, price):
        # MetaApi doesn't expose margin calc the same way; return a rough estimate or None (live_trading will skip check if None)
        return None

    def get_symbol_info(self, symbol):
        # Return minimal info; point/digits from common defaults (forex)
        if 'XAU' in symbol.upper() or 'GOLD' in symbol.upper():
            return {'point': 0.01, 'digits': 2, 'volume_min': 0.01, 'volume_max': 100, 'volume_step': 0.01,
                    'trade_contract_size': 100, 'trade_tick_size': 0.01, 'trade_tick_value': 1.0}
        if 'BTC' in symbol.upper():
            return {'point': 0.01, 'digits': 2, 'volume_min': 0.001, 'volume_max': 100, 'volume_step': 0.001,
                    'trade_contract_size': 1, 'trade_tick_size': 0.01, 'trade_tick_value': 1.0}
        return {'point': 0.00001, 'digits': 5, 'volume_min': 0.01, 'volume_max': 100, 'volume_step': 0.01,
                'trade_contract_size': 100000, 'trade_tick_size': 0.00001, 'trade_tick_value': 1.0}

    def calc_lot_size_from_risk(self, symbol, balance, entry_price, sl_price, risk_pct):
        info = self.get_symbol_info(symbol)
        tick_size = info.get('trade_tick_size') or info['point']
        tick_value = info.get('trade_tick_value', 0)
        if tick_size <= 0 or tick_value <= 0:
            return None
        risk_amount = balance * risk_pct
        sl_distance = abs(float(entry_price) - float(sl_price))
        risk_ticks = sl_distance / tick_size
        if risk_ticks <= 0:
            return None
        loss_per_lot = risk_ticks * tick_value
        if loss_per_lot <= 0:
            return None
        lot_size = risk_amount / loss_per_lot
        step = info['volume_step']
        lot_size = max(info['volume_min'], min(info['volume_max'], lot_size))
        lot_size = round(lot_size / step) * step
        lot_size = max(info['volume_min'], min(info['volume_max'], lot_size))
        return round(lot_size, 2)

    def get_live_price(self, symbol):
        if not self.token or not self.account_id:
            return None
        base = _client_base(self.region)
        url = f"{base}/users/current/accounts/{self.account_id}/symbols/{symbol}/current-price"
        try:
            data = self._get(url)
        except Exception:
            return None
        if not data:
            return None
        t = data.get('time')
        if t:
            try:
                dt = datetime.fromisoformat(t.replace('Z', '+00:00'))
                if dt.tzinfo:
                    dt = dt.replace(tzinfo=None)
            except Exception:
                dt = datetime.now()
        else:
            dt = datetime.now()
        return {
            'bid': float(data.get('bid', 0)),
            'ask': float(data.get('ask', 0)),
            'time': dt
        }

    def get_bars(self, symbol, timeframe, count=100):
        # timeframe: string '1m','5m','15m','1h','4h','1d'
        if not self.token or not self.account_id:
            return None
        base = _market_data_base(self.region)
        url = f"{base}/users/current/accounts/{self.account_id}/historical-market-data/symbols/{symbol}/timeframes/{timeframe}/candles"
        try:
            data = self._get(url, params={"limit": min(count, 1000)}, timeout=120)
        except Exception:
            return None
        if not data or not isinstance(data, list):
            return None
        df = pd.DataFrame(data)
        if df.empty:
            return None
        df['time'] = pd.to_datetime(df['time'])
        df.set_index('time', inplace=True)
        df.rename(columns={'tickVolume': 'volume'}, inplace=True)
        if 'volume' not in df.columns and 'volume' in data[0]:
            pass
        else:
            df['volume'] = df.get('volume', df.get('tickVolume', 0))
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col not in df.columns:
                return None
        return df[['open', 'high', 'low', 'close', 'volume']].tail(count)

    def place_order(self, symbol, order_type, volume, price=None, sl=None, tp=None, comment=""):
        if not self.connected or not self.token or not self.account_id:
            return None
        action = "ORDER_TYPE_BUY" if order_type == "BUY" else "ORDER_TYPE_SELL"
        base = _client_base(self.region)
        url = f"{base}/users/current/accounts/{self.account_id}/trade"
        body = {
            "actionType": action,
            "symbol": symbol,
            "volume": float(volume),
        }
        if sl is not None:
            body["stopLoss"] = float(sl)
        if tp is not None:
            body["takeProfit"] = float(tp)
        if comment:
            body["comment"] = str(comment)[:26]
        try:
            result = self._post(url, body)
        except Exception as e:
            print(f"MetaApi place_order error: {e}")
            return None
        if not result:
            return None
        code = result.get('numericCode', result.get('stringCode', ''))
        if code not in (0, 10008, 10009, 10010, 10025) and result.get('stringCode') != 'TRADE_RETCODE_DONE':
            print(f"MetaApi trade rejected: {result}")
            return None
        order_id = result.get('orderId') or result.get('positionId')
        print(f"Order executed: {order_type} {volume} {symbol} @ market (orderId: {order_id})")
        return {
            'ticket': order_id,
            'symbol': symbol,
            'type': order_type,
            'volume': volume,
            'price': price,
            'sl': sl,
            'tp': tp,
            'time': datetime.now()
        }

    def get_positions(self):
        if not self.token or not self.account_id:
            return []
        base = _client_base(self.region)
        url = f"{base}/users/current/accounts/{self.account_id}/positions"
        try:
            data = self._get(url)
        except Exception:
            return []
        if not data or not isinstance(data, list):
            return []
        out = []
        for pos in data:
            t = pos.get('time')
            try:
                dt = datetime.fromisoformat(t.replace('Z', '+00:00')) if t else datetime.now()
                if hasattr(dt, 'tzinfo') and dt.tzinfo:
                    dt = dt.replace(tzinfo=None)
            except Exception:
                dt = datetime.now()
            out.append({
                'ticket': pos.get('id'),
                'symbol': pos.get('symbol', ''),
                'type': 'BUY' if (pos.get('type') or '').endswith('BUY') else 'SELL',
                'volume': float(pos.get('volume', 0)),
                'price_open': float(pos.get('openPrice', 0)),
                'sl': float(pos['stopLoss']) if pos.get('stopLoss') is not None else None,
                'tp': float(pos['takeProfit']) if pos.get('takeProfit') is not None else None,
                'profit': float(pos.get('profit', 0)),
                'time': dt
            })
        return out

    def close_position(self, ticket):
        if not self.connected or not self.token or not self.account_id:
            return False
        base = _client_base(self.region)
        url = f"{base}/users/current/accounts/{self.account_id}/trade"
        body = {"actionType": "POSITION_CLOSE_ID", "positionId": str(ticket)}
        try:
            result = self._post(url, body)
        except Exception:
            return False
        if not result:
            return False
        code = result.get('numericCode')
        if code not in (0, 10008, 10009, 10010, 10025):
            return False
        print(f"Position {ticket} closed successfully")
        return True
