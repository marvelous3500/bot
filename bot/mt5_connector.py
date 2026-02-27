import math
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import time
import subprocess
import sys
import os

try:
    import config
except ImportError:
    config = None


def _log(msg, verbose_only=True):
    """Print log message. Set verbose_only=False to always print."""
    if verbose_only and config and not getattr(config, "MT5_VERBOSE", True):
        return
    print(f"[MT5] {msg}")


def _print_mt5_hint(step, err):
    """Print a short hint for common MT5 errors. err is (code, message) from mt5.last_error()."""
    code = err[0] if isinstance(err, (tuple, list)) and len(err) >= 1 else None
    msg = (err[1] or "").lower() if isinstance(err, (tuple, list)) and len(err) >= 2 else ""
    hints = []
    if step == "initialize":
        if code == -6 or "auth" in msg or "authorization" in msg:
            hints.append("  → Authorization failed: .env login/password/server must match an account that works in the MT5 app.")
            hints.append("  → Exness Trial/demo: MT5_SERVER=Exness-MT5Trial9. Exness Real: MT5_SERVER=Exness-MT5Real9 (use the server name MT5 shows for your account).")
            hints.append("  → In MT5: File → Open an account, or log in with your account — copy that exact Login and Server into .env.")
            hints.append("  → Close MT5 completely, then run the bot again so it logs in with your .env credentials.")
        elif code == -10005 or "ipc" in msg or "timeout" in msg:
            hints.append("  → Use Command Prompt or PowerShell (not Git Bash): cmd or powershell, then python main.py --mode live")
            hints.append("  → Close MT5 completely, then run the bot — it will start MT5 and try to connect (wait 15s).")
            hints.append("  → Or: start MT5 as Administrator (right-click → Run as administrator), then run the bot from an Administrator cmd/powershell.")
            hints.append("  → In MT5 enable 'Algo Trading' (toolbar). Allow Python and terminal64.exe in Windows Firewall / antivirus if needed.")
        elif code == -10001:
            hints.append("  → MT5 terminal not found. Install MetaTrader 5 (from your broker, e.g. Exness) and run it at least once.")
    elif step == "login":
        if code == -2 or "invalid" in msg or "param" in msg:
            hints.append("  → Invalid argument: MT5_LOGIN must be a number (e.g. 298444944). MT5_PASSWORD and MT5_SERVER must be non-empty in .env.")
        if code == -6 or "auth" in msg or "invalid" in msg:
            hints.append("  → Exness Trial: MT5_SERVER=Exness-MT5Trial9. Exness Real: MT5_SERVER=Exness-MT5Real9. Login and Server must match the account type.")
            hints.append("  → Log in once in the MT5 app (File → Open an account / Login) with the same Login and Server — then use that exact Server name in .env.")
            hints.append("  → Wrong server (e.g. Trial server for a real account) causes 'Invalid account' or 'Authorization failed'.")
    if hints:
        print("Troubleshooting:")
        for h in hints:
            print(h)


class MT5Connector:
    """Handles all interactions with MetaTrader 5 platform."""

    def __init__(self, login=None, password=None, server=None, path=None, auto_start=True):
        self.login = login
        self.password = password
        self.server = server
        self.path = path
        self.auto_start = auto_start  # When True and path set, start MT5 at the beginning (same session)
        self.connected = False

    def connect(self):
        max_tries = getattr(config, "MT5_CONNECT_RETRIES", 5) if config else 5
        retry_delay = getattr(config, "MT5_CONNECT_DELAY", 5) if config else 5

        print("\n" + "=" * 50)
        print("MT5 CONNECTION")
        print("=" * 50)
        print(f"  Login:   {self.login}")
        print(f"  Server:  {self.server}")
        print(f"  Password: {'****' if self.password else '(not set)'}")
        if self.path:
            print(f"  Path:    {self.path}")
        else:
            print(f"  Path:    (auto-detect)")
        print(f"  Retries: {max_tries} (delay {retry_delay}s)")
        print("=" * 50)

        started_terminal = False
        try_without_path = False

        # Step 1: Start MT5 terminal if needed
        if self.auto_start and self.path and sys.platform == "win32":
            path_exe = self.path.replace("/", os.sep)
            if os.path.isfile(path_exe):
                try:
                    _log("Starting MT5 terminal...")
                    subprocess.Popen([path_exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    print("  → MT5 terminal launched. Waiting 15s for it to load...")
                    time.sleep(15)
                    _log("Terminal should be ready. Connecting (auto-detect)...")
                    started_terminal = True
                    try_without_path = True
                except Exception as e:
                    print(f"  → Could not start MT5: {e}")
            else:
                print(f"  → Path not found: {path_exe}")

        # Step 2: Initialize MT5 (with retries)
        for attempt in range(1, max_tries + 1):
            if try_without_path:
                init_kw = {}
                try_without_path = False
                _log(f"  → Attempt {attempt}/{max_tries}: initialize (auto-detect)")
            else:
                init_kw = {"path": self.path} if self.path else {}
                _log(f"  → Attempt {attempt}/{max_tries}: initialize(path={self.path or 'auto'})")

            if mt5.initialize(**init_kw):
                print(f"  → MT5 initialize() OK (attempt {attempt})")
                break

            err = mt5.last_error()
            code = err[0] if isinstance(err, (tuple, list)) and len(err) >= 1 else None
            msg = err[1] if isinstance(err, (tuple, list)) and len(err) >= 2 else ""
            print(f"  → initialize() failed: retcode={code} {msg}")

            # If IPC timeout, try starting terminal and retry
            if code == -10005 and self.path and sys.platform == "win32" and not started_terminal:
                path_exe = self.path.replace("/", os.sep)
                if os.path.isfile(path_exe):
                    try:
                        _log("  → IPC timeout. Starting MT5 terminal...")
                        subprocess.Popen([path_exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        print("  → Waiting 15s for terminal to load...")
                        time.sleep(15)
                        started_terminal = True
                        try_without_path = True
                        continue
                    except Exception as e:
                        print(f"  → Could not start MT5: {e}")

            if attempt < max_tries:
                print(f"  → Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
                continue

            print(f"  → initialize() failed after {max_tries} attempts.")
            _print_mt5_hint("initialize", err)
            return False

        # Step 3: Login to account (with retries)
        if self.login is not None and self.password and self.server:
            login_val = self.login
            if isinstance(login_val, str):
                login_val = login_val.strip()
                try:
                    login_val = int(login_val)
                except (ValueError, TypeError):
                    pass

            for attempt in range(1, max_tries + 1):
                _log(f"  → Login attempt {attempt}/{max_tries} (server={self.server})")
                authorized = mt5.login(login=login_val, password=self.password, server=self.server)
                if authorized:
                    print(f"  → Login OK (attempt {attempt})")
                    break
                err = mt5.last_error()
                code = err[0] if isinstance(err, (tuple, list)) and len(err) >= 1 else None
                msg = err[1] if isinstance(err, (tuple, list)) and len(err) >= 2 else ""
                print(f"  → Login failed: retcode={code} {msg}")
                if attempt < max_tries:
                    print(f"  → Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                else:
                    print(f"  → Login failed after {max_tries} attempts.")
                    _print_mt5_hint("login", err)
                    mt5.shutdown()
                    return False

            # Print account info
            acc = mt5.account_info()
            if acc:
                print(f"  → Account: {acc.login} | {acc.server} | Balance: {acc.balance} {acc.currency}")
            else:
                print(f"  → Connected to MT5 — account #{self.login} on {self.server}")
        else:
            print("  → Connected to MT5 (no account login)")

        self.connected = True
        # Check Algo Trading status first — print before doing anything else
        ti = mt5.terminal_info()
        if ti is not None:
            if getattr(ti, "trade_allowed", True):
                print("  → Algo Trading: ENABLED (orders will execute)")
            else:
                print("  → Algo Trading: DISABLED — orders will fail.")
                print("  → Enable it: click the 'Algo Trading' button in the MT5 toolbar (it must be green).")
        print("  → Connection ready.")
        print("=" * 50 + "\n")
        return True

    def disconnect(self):
        _log("Shutting down MT5...")
        mt5.shutdown()
        self.connected = False
        print("[MT5] Disconnected from server.")

    def is_algo_trading_enabled(self):
        """Return True if Algo Trading is enabled (required for order_send)."""
        if not self.connected:
            return False
        ti = mt5.terminal_info()
        return ti is not None and getattr(ti, "trade_allowed", False)

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

    def is_market_open(self, symbol):
        """Return True if market is open for trading. False on weekend (forex/gold) or when trade_mode is disabled.
        Crypto (BTC, ETH, etc.) trades 24/7 — skip weekend check for those."""
        from datetime import datetime
        now_utc = datetime.utcnow()
        s = (symbol or "").upper().replace("-", "").replace("_", "")
        is_crypto = "BTC" in s or "ETH" in s or "CRYPTO" in s
        if not is_crypto and now_utc.weekday() >= 5:  # Saturday=5, Sunday=6 — forex/gold closed
            return False
        info = mt5.symbol_info(symbol)
        if info is None:
            return False
        trade_mode = getattr(info, 'trade_mode', None)
        if trade_mode == 0:  # SYMBOL_TRADE_MODE_DISABLED
            return False
        return True

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
        Uses SYMBOL_CONFIGS LOSS_PER_LOT_PER_POINT for gold when broker tick_value is wrong.
        Returns volume or None if calc fails (fallback to config.MAX_POSITION_SIZE).
        """
        if not self.connected or balance <= 0 or risk_pct <= 0:
            return None
        info = mt5.symbol_info(symbol)
        if info is None:
            return None
        sl_distance = abs(float(entry_price) - float(sl_price))
        if sl_distance <= 0:
            return None
        risk_amount = balance * risk_pct
        # Gold override: 1 lot = 100 oz, $1 move = $100. Use when broker tick_value wrong.
        loss_per_lot_per_pt = config.get_symbol_config(symbol, "LOSS_PER_LOT_PER_POINT") if config else None
        if loss_per_lot_per_pt is not None and loss_per_lot_per_pt > 0:
            loss_per_lot = sl_distance * loss_per_lot_per_pt
        else:
            tick_size = getattr(info, 'trade_tick_size', info.point) or info.point
            tick_value = getattr(info, 'trade_tick_value', 0)
            if tick_size <= 0 or tick_value <= 0:
                return None
            risk_ticks = sl_distance / tick_size
            if risk_ticks <= 0:
                return None
            loss_per_lot = risk_ticks * tick_value
        if loss_per_lot <= 0:
            return None
        lot_size = risk_amount / loss_per_lot
        step = info.volume_step
        lot_size = max(info.volume_min, min(info.volume_max, lot_size))
        # Round half up so we get closer to target risk (e.g. 0.0445 → 0.05 not 0.04)
        lot_size = math.floor(lot_size / step + 0.5) * step
        lot_size = max(info.volume_min, min(info.volume_max, lot_size))
        return round(lot_size, 2)

    def calc_dollar_risk(self, symbol, entry_price, sl_price, volume):
        """Return dollar amount at risk if SL hits, or None if calc fails."""
        if not self.connected:
            return None
        info = mt5.symbol_info(symbol)
        if info is None:
            return None
        sl_distance = abs(float(entry_price) - float(sl_price))
        if sl_distance <= 0:
            return None
        loss_per_lot_per_pt = config.get_symbol_config(symbol, "LOSS_PER_LOT_PER_POINT") if config else None
        if loss_per_lot_per_pt is not None and loss_per_lot_per_pt > 0:
            loss_per_lot = sl_distance * loss_per_lot_per_pt
        else:
            tick_size = getattr(info, 'trade_tick_size', info.point) or info.point
            tick_value = getattr(info, 'trade_tick_value', 0)
            if tick_size <= 0 or tick_value <= 0:
                return None
            risk_ticks = sl_distance / tick_size
            if risk_ticks <= 0:
                return None
            loss_per_lot = risk_ticks * tick_value
        if loss_per_lot <= 0:
            return None
        return round(loss_per_lot * float(volume), 2)

    def get_live_price(self, symbol):
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            err = mt5.last_error()
            _log(f"get_live_price({symbol}): no tick — {err}")
            return None
        _log(f"get_live_price({symbol}): bid={tick.bid} ask={tick.ask}")
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
        _log(f"get_bars({symbol}, {timeframe}, count={count})...")
        # Ensure symbol is in Market Watch (required for copy_rates on some brokers)
        info = mt5.symbol_info(symbol)
        if info is None:
            _log(f"  → Symbol {symbol} not found.")
            return None
        if not info.visible:
            _log(f"  → Adding {symbol} to Market Watch...")
            mt5.symbol_select(symbol, True)
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
        if rates is None or len(rates) == 0:
            err = mt5.last_error()
            _log(f"  → No data: {err}")
            return None
        _log(f"  → Got {len(rates)} bars")
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        df.rename(columns={'tick_volume': 'volume'}, inplace=True)
        return df[['open', 'high', 'low', 'close', 'volume']]

    def place_order(self, symbol, order_type, volume, price=None, sl=None, tp=None, comment=""):
        if not self.connected:
            return None, "Not connected"
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return None, "Symbol not found"
        if not symbol_info.visible:
            if not mt5.symbol_select(symbol, True):
                return None, "Could not add symbol to Market Watch"
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None, "No tick data"
        if order_type == 'BUY':
            trade_type = mt5.ORDER_TYPE_BUY
            execution_price = tick.ask if price is None else price
        elif order_type == 'SELL':
            trade_type = mt5.ORDER_TYPE_SELL
            execution_price = tick.bid if price is None else price
        else:
            return None, "Invalid order type"
        # Normalize volume to symbol's step (e.g. 0.01 for gold)
        vol_min = getattr(symbol_info, 'volume_min', 0.01)
        vol_max = getattr(symbol_info, 'volume_max', 100)
        vol_step = getattr(symbol_info, 'volume_step', 0.01)
        try:
            v = float(volume)
            v = max(vol_min, min(vol_max, round(v / vol_step) * vol_step))
            volume = round(v, 2)
        except (TypeError, ValueError):
            volume = vol_min
        # MT5 comment max 31 chars; many brokers allow only ASCII alphanumeric, space, hyphen, underscore. Some require empty.
        if comment is None or (isinstance(comment, str) and not comment.strip()):
            safe_comment = ""
        else:
            raw = str(comment).replace("\x00", "") if comment else ""
            try:
                raw = raw.encode("ascii", "replace").decode("ascii")  # drop non-ASCII
            except Exception:
                raw = ""
            allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 _-")
            safe_comment = "".join(c if c in allowed else " " for c in raw)
            safe_comment = " ".join(safe_comment.split())[:31].strip() or "ICT"
        # Deviation (slippage) in points: ENTRY_SLIPPAGE_PIPS -> points (1 pip = 10 points for 5-digit, 1 point for 2-digit gold)
        point = getattr(symbol_info, 'point', 0.00001)
        pip_size = 10.0 * point if point and point < 0.01 else (point or 0.01)
        slippage_pips = getattr(config, 'ENTRY_SLIPPAGE_PIPS', 3.0) or 0
        deviation_pts = max(1, int(round(slippage_pips * pip_size / (point or 0.00001)))) if point else 20
        deviation_pts = min(deviation_pts, 500)
        # Filling mode: try FOK, IOC, RETURN (Exness gold often needs FOK or IOC, not RETURN)
        filling_modes = [
            ("FOK", mt5.ORDER_FILLING_FOK),
            ("IOC", mt5.ORDER_FILLING_IOC),
            ("RETURN", getattr(mt5, "ORDER_FILLING_RETURN", 0)),
        ]
        result = None
        last_err = None
        for fill_name, type_filling in filling_modes:
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": trade_type,
                "price": execution_price,
                "deviation": deviation_pts,
                "magic": getattr(config, 'MT5_MAGIC_NUMBER', 234000),
                "comment": safe_comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": type_filling,
            }
            if sl is not None:
                request["sl"] = sl
            if tp is not None:
                request["tp"] = tp
            _log(f"order_send: {order_type} {volume} {symbol} @ {execution_price} (filling={fill_name}) sl={sl} tp={tp}")
            result = mt5.order_send(request)
            if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
                break
            if result is not None and result.retcode == 10030:
                _log(f"  → Filling {fill_name} not supported, trying next...")
                last_err = result
                continue
            break
        if result is None or getattr(result, "retcode", -1) != mt5.TRADE_RETCODE_DONE:
            err = mt5.last_error()
            retcode = getattr(result, "retcode", err[0] if err else "?")
            comment = getattr(result, 'comment', None) if result is not None else (err[1] if err and len(err) > 1 else "")
            err_msg = f"retcode={retcode} comment={comment}"
            print(f"[MT5] Order failed: {err_msg}")
            if result is not None and hasattr(result, 'retcode') and result.retcode:
                if result.retcode == 10027:  # AutoTrading disabled by client
                    print("  → Enable 'Algo Trading' in MT5: click the button in the top toolbar (it must be green/on).")
                elif result.retcode == 10019:  # Not enough money
                    print("  → Insufficient margin. Reduce lot size or add funds.")
                elif result.retcode == 10016:  # Invalid request
                    print("  → Invalid order (check SL/TP distance, volume, symbol). Gold: try volume 0.01.")
                elif result.retcode == 10030:  # Invalid fill
                    print("  → Tried FOK, IOC, RETURN — none supported. Check broker/symbol in MT5 Market Watch.")
                elif result.retcode == -2:  # Invalid comment
                    print("  → Comment rejected. Set MT5_ORDER_COMMENT= in .env (empty) or MT5_ORDER_COMMENT=ICT; some brokers require empty comment.")
            return None, err_msg
        print(f"Order executed: {order_type} {volume} {symbol} @ {result.price} (filling={fill_name})")
        return {
            'ticket': result.order,
            'symbol': symbol,
            'type': order_type,
            'volume': volume,
            'price': result.price,
            'sl': sl,
            'tp': tp,
            'time': datetime.now()
        }, None

    def get_pip_size(self, symbol):
        """Return pip size in price units for the symbol (e.g. 0.0001 for forex, 0.1 for XAUUSD)."""
        info = mt5.symbol_info(symbol)
        if info is None:
            return None
        point = getattr(info, 'point', 0)
        if point <= 0:
            return None
        digits = getattr(info, 'digits', 5)
        # 1 pip = 10 * point for 5/3-digit forex and 2-digit gold
        return 10.0 * point

    def get_atr(self, symbol, period=14):
        """Return ATR(period) from M15 bars, or None if not available. Used for trailing SL when TRAILING_SL_ATR_MULT set."""
        if not self.connected:
            return None
        df = self.get_bars(symbol, '15m', count=period + 20)
        if df is None or len(df) < period + 2:
            return None
        high = df['high'].astype(float)
        low = df['low'].astype(float)
        close = df['close'].astype(float)
        prev_close = close.shift(1)
        tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        atr = tr.rolling(period).mean().iloc[-1]
        return float(atr) if not pd.isna(atr) else None

    def modify_position(self, ticket, sl=None, tp=None):
        """Modify an open position's SL and/or TP. Returns (True, None) on success, (False, error_msg) on failure."""
        if not self.connected:
            return False, "Not connected"
        positions = mt5.positions_get(ticket=ticket)
        if positions is None or len(positions) == 0:
            return False, "Position not found"
        pos = positions[0]
        new_sl = float(sl) if sl is not None else pos.sl
        new_tp = float(tp) if tp is not None else pos.tp
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "position": ticket,
            "sl": new_sl,
            "tp": new_tp,
        }
        result = mt5.order_send(request)
        if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
            _log(f"Position {ticket} modified: sl={new_sl} tp={new_tp}")
            return True, None
        err = mt5.last_error()
        err_msg = err[1] if err and len(err) > 1 else str(result.retcode if result is not None else "?")
        return False, err_msg

    def get_today_deals_pnl(self):
        """Return today's total P&L from closed deals (profit + commission + swap). UTC date. Returns 0.0 if not connected or error."""
        if not self.connected:
            return 0.0
        now = datetime.utcnow()
        from_date = datetime(now.year, now.month, now.day)
        to_date = now
        deals = mt5.history_deals_get(from_date, to_date)
        if deals is None:
            return 0.0
        total = sum(getattr(d, 'profit', 0) + getattr(d, 'commission', 0) + getattr(d, 'swap', 0) for d in deals)
        return float(total)

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
            "magic": getattr(config, 'MT5_MAGIC_NUMBER', 234000),
            "comment": "Close position",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            return False
        print(f"Position {ticket} closed successfully")
        return True

    def close_position_partial(self, ticket, volume_to_close):
        """Close part of a position by volume. Returns (True, None) on success, (False, error_msg) on failure."""
        if not self.connected:
            return False, "Not connected"
        positions = mt5.positions_get(ticket=ticket)
        if positions is None or len(positions) == 0:
            return False, "Position not found"
        position = positions[0]
        vol_min = getattr(mt5.symbol_info(position.symbol), 'volume_min', 0.01)
        vol_step = getattr(mt5.symbol_info(position.symbol), 'volume_step', 0.01)
        try:
            v = float(volume_to_close)
            v = max(vol_min, min(float(position.volume), round(v / vol_step) * vol_step))
        except (TypeError, ValueError):
            return False, "Invalid volume"
        if v >= position.volume - 0.0001:
            ok = self.close_position(ticket)
            return (True, None) if ok else (False, "Close failed")
        if position.type == mt5.POSITION_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(position.symbol).bid
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(position.symbol).ask
        deviation_pts = 20
        if config:
            slippage_pips = getattr(config, 'ENTRY_SLIPPAGE_PIPS', 3.0) or 0
            point = getattr(mt5.symbol_info(position.symbol), 'point', 0.00001)
            pip_size = 10.0 * point if point and point < 0.01 else (point or 0.01)
            deviation_pts = max(1, min(500, int(round(slippage_pips * pip_size / (point or 0.00001))))) if point else 20
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": round(v, 2),
            "type": order_type,
            "position": ticket,
            "price": price,
            "deviation": deviation_pts,
            "magic": getattr(config, 'MT5_MAGIC_NUMBER', 234000),
            "comment": "Partial close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
            _log(f"Position {ticket} partially closed: {v} lots")
            return True, None
        err = mt5.last_error()
        err_msg = err[1] if err and len(err) > 1 else str(getattr(result, 'retcode', '?'))
        return False, err_msg
