import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import time


def _print_mt5_hint(step, err):
    """Print a short hint for common MT5 errors. err is (code, message) from mt5.last_error()."""
    code = err[0] if isinstance(err, (tuple, list)) and len(err) >= 1 else None
    msg = (err[1] or "").lower() if isinstance(err, (tuple, list)) and len(err) >= 2 else ""
    hints = []
    if step == "initialize":
        if code == -10005 or "ipc" in msg or "timeout" in msg:
            hints.append("  → MT5 terminal may not be running. Start MetaTrader 5 from the Start menu, then run the bot again.")
            hints.append("  → If MT5 is installed in a custom path, set MT5_PATH in .env and use it in initialize (see docs).")
        elif code == -10001:
            hints.append("  → MT5 terminal not found. Install MetaTrader 5 (from your broker, e.g. Exness) and run it at least once.")
    elif step == "login":
        if code == -6 or "auth" in msg or "invalid" in msg:
            hints.append("  → Check MT5_LOGIN, MT5_PASSWORD, MT5_SERVER in .env. Server must match exactly (e.g. Exness-MT5Trial vs Exness-MT5).")
            hints.append("  → Log in once in the MT5 app with the same account to confirm credentials work.")
    if hints:
        print("Troubleshooting:")
        for h in hints:
            print(h)


class MT5Connector:
    """Handles all interactions with MetaTrader 5 platform."""

    def __init__(self, login=None, password=None, server=None):
        self.login = login
        self.password = password
        self.server = server
        self.connected = False

    def connect(self):
        print("MT5 credentials (before connect):")
        print(f"  Login:  {self.login}")
        print(f"  Server: {self.server}")
        print(f"  Password: {'****' if self.password else '(not set)'}")
        print("Connecting...")
        if not mt5.initialize():
            err = mt5.last_error()
            print(f"MT5 initialize() failed: {err}")
            _print_mt5_hint("initialize", err)
            return False
        print("MT5 initialize() successful.")
        if self.login and self.password and self.server:
            authorized = mt5.login(self.login, password=self.password, server=self.server)
            if not authorized:
                err = mt5.last_error()
                print(f"MT5 login failed: {err}")
                _print_mt5_hint("login", err)
                mt5.shutdown()
                return False
            print(f"Connected to MT5 — account #{self.login} on {self.server}")
        else:
            print("Connected to MT5 (no account login)")
        self.connected = True
        return True

    def disconnect(self):
        mt5.shutdown()
        self.connected = False
        print("Disconnected from MT5")

    def get_account_info(self):
        if not self.connected:
            return None
        account_info = mt5.account_info()
        if account_info is None:
            return None
        return {
            'balance': account_info.balance,
            'equity': account_info.equity,
            'margin': account_info.margin,
            'free_margin': account_info.margin_free,
            'profit': account_info.profit,
            'currency': account_info.currency
        }

    def calc_required_margin(self, symbol, order_type, volume, price):
        if not self.connected:
            return None
        trade_type = mt5.ORDER_TYPE_BUY if order_type == 'BUY' else mt5.ORDER_TYPE_SELL
        margin = mt5.order_calc_margin(trade_type, symbol, volume, price)
        return float(margin) if margin is not None else None

    def get_symbol_info(self, symbol):
        info = mt5.symbol_info(symbol)
        if info is None:
            return None
        return {
            'point': info.point,
            'digits': info.digits,
            'volume_min': info.volume_min,
            'volume_max': info.volume_max,
            'volume_step': info.volume_step,
            'trade_contract_size': info.trade_contract_size,
            'trade_tick_size': getattr(info, 'trade_tick_size', info.point),
            'trade_tick_value': getattr(info, 'trade_tick_value', 0),
        }

    def calc_lot_size_from_risk(self, symbol, balance, entry_price, sl_price, risk_pct):
        """
        Calculate lot size so that risk = balance * risk_pct (matches backtest).
        Returns volume or None if calc fails (fallback to config.MAX_POSITION_SIZE).
        """
        if not self.connected or balance <= 0 or risk_pct <= 0:
            return None
        info = mt5.symbol_info(symbol)
        if info is None:
            return None
        tick_size = getattr(info, 'trade_tick_size', info.point) or info.point
        tick_value = getattr(info, 'trade_tick_value', 0)
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
        # Round to volume_step
        step = info.volume_step
        lot_size = max(info.volume_min, min(info.volume_max, lot_size))
        lot_size = round(lot_size / step) * step
        lot_size = max(info.volume_min, min(info.volume_max, lot_size))
        return round(lot_size, 2)

    def get_live_price(self, symbol):
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        return {
            'bid': tick.bid,
            'ask': tick.ask,
            'time': datetime.fromtimestamp(tick.time)
        }

    # Map string timeframes (used by live_trading) to MT5 constants
    _TIMEFRAME_MAP = {
        '1m': mt5.TIMEFRAME_M1,
        '5m': mt5.TIMEFRAME_M5,
        '15m': mt5.TIMEFRAME_M15,
        '1h': mt5.TIMEFRAME_H1,
        '4h': mt5.TIMEFRAME_H4,
        '1d': mt5.TIMEFRAME_D1,
    }

    def get_bars(self, symbol, timeframe, count=100):
        if isinstance(timeframe, str):
            timeframe = self._TIMEFRAME_MAP.get(timeframe, mt5.TIMEFRAME_M5)
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
        if rates is None or len(rates) == 0:
            return None
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        df.rename(columns={'tick_volume': 'volume'}, inplace=True)
        return df[['open', 'high', 'low', 'close', 'volume']]

    def place_order(self, symbol, order_type, volume, price=None, sl=None, tp=None, comment=""):
        if not self.connected:
            return None
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return None
        if not symbol_info.visible:
            if not mt5.symbol_select(symbol, True):
                return None
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        if order_type == 'BUY':
            trade_type = mt5.ORDER_TYPE_BUY
            execution_price = tick.ask if price is None else price
        elif order_type == 'SELL':
            trade_type = mt5.ORDER_TYPE_SELL
            execution_price = tick.bid if price is None else price
        else:
            return None
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": trade_type,
            "price": execution_price,
            "deviation": 20,
            "magic": 234000,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        if sl is not None:
            request["sl"] = sl
        if tp is not None:
            request["tp"] = tp
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            return None
        print(f"Order executed: {order_type} {volume} {symbol} @ {result.price}")
        return {
            'ticket': result.order,
            'symbol': symbol,
            'type': order_type,
            'volume': volume,
            'price': result.price,
            'sl': sl,
            'tp': tp,
            'time': datetime.now()
        }

    def get_positions(self):
        positions = mt5.positions_get()
        if positions is None:
            return []
        return [{
            'ticket': pos.ticket,
            'symbol': pos.symbol,
            'type': 'BUY' if pos.type == mt5.POSITION_TYPE_BUY else 'SELL',
            'volume': pos.volume,
            'price_open': pos.price_open,
            'sl': pos.sl,
            'tp': pos.tp,
            'profit': pos.profit,
            'time': datetime.fromtimestamp(pos.time)
        } for pos in positions]

    def close_position(self, ticket):
        positions = mt5.positions_get(ticket=ticket)
        if positions is None or len(positions) == 0:
            return False
        position = positions[0]
        if position.type == mt5.POSITION_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(position.symbol).bid
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(position.symbol).ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": order_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": 234000,
            "comment": "Close position",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            return False
        print(f"Position {ticket} closed successfully")
        return True
