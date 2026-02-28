import os
import time
import config
import pandas as pd
from datetime import datetime, timedelta
from .connector_interface import get_connector, TIMEFRAME_M1, TIMEFRAME_M5, TIMEFRAME_M15, TIMEFRAME_H1, TIMEFRAME_H4, TIMEFRAME_D1
from .paper_trading import PaperTrading
from .trade_approver import TradeApprover
from .strategies import VesterStrategy, VeeStrategy, TrendVesterStrategy
from .indicators_bos import detect_swing_highs_lows, detect_break_of_structure
from ai import get_signal_confidence, explain_trade, speak
from .telegram_notifier import send_setup_notification


def _print_live_checklist():
    """Print real-money checklist at live startup. See REAL_MONEY_CHECKLIST.md for full details."""
    print("\n" + "=" * 50)
    print("LIVE TRADING CHECKLIST (verify before continuing)")
    print("=" * 50)
    items = [
        ("Paper traded 2+ weeks with target strategy", True),
        ("Backtest with spread/commission shows acceptable performance", True),
        ("MANUAL_APPROVAL = True for first live runs", config.MANUAL_APPROVAL),
        ("MAX_TRADES_PER_DAY = 2 or 3", config.MAX_TRADES_PER_DAY <= 3),
        (".env has correct MT5 server for real account (not Trial)", True),
        ("Position size = 0.01 or minimum for first trades", True),
        ("LIVE_CONFIRM_ON_START = True to confirm before loop", getattr(config, 'LIVE_CONFIRM_ON_START', False)),
        ("SKIP_WHEN_MARKET_CLOSED = True (no weekend trades)", getattr(config, 'SKIP_WHEN_MARKET_CLOSED', True)),
    ]
    for desc, ok in items:
        mark = "[OK]" if ok else "[?]"
        print(f"  {mark} {desc}")
    print("  [ ] Real money at risk. Only use capital you can afford to lose.")
    print("=" * 50 + "\n")


class LiveTradingEngine:
    """Main live trading engine that runs strategies continuously."""

    def __init__(self, strategy_name='vester', paper_mode=True, symbol=None):
        self.strategy_name = strategy_name
        self.paper_mode = paper_mode
        self.cli_symbol = symbol  # --symbol from CLI (e.g. 'BTC-USD'); overrides config for live/paper

        login = config.MT5_LOGIN
        password = config.MT5_PASSWORD
        server = config.MT5_SERVER

        self.mt5 = get_connector(
            login=login,
            password=password,
            server=server,
            path=getattr(config, 'MT5_PATH', None),
            auto_start=getattr(config, 'MT5_AUTO_START', True)
        )
        if paper_mode:
            self.paper = PaperTrading(
                initial_balance=config.INITIAL_BALANCE,
                log_file=config.PAPER_TRADING_LOG
            )
        if config.MANUAL_APPROVAL:
            self.approver = TradeApprover()
        self.trades_today = []
        self.running = False
        self._trades_per_setup = {}  # (symbol, type, setup_key) -> count

    def _get_setup_key(self, signal):
        """Return hashable key (symbol, type, setup_str) for setup tracking, or None if not applicable."""
        symbol = signal.get('symbol', '')
        order_type = signal.get('type', '')
        if not symbol or not order_type:
            return None
        setup_ts = None
        if self.strategy_name in ('vester', 'trend_vester'):
            setup_ts = signal.get('setup_15m') or signal.get('setup_5m')
            if setup_ts is None:
                t = signal.get('time')
                if t is not None:
                    ts = t if hasattr(t, 'floor') else pd.Timestamp(t)
                    setup_ts = ts.floor('15min') if self.strategy_name == 'vester' else ts.floor('5min')
        elif self.strategy_name == 'vee':
            setup_ts = signal.get('setup_15m')
            if setup_ts is None:
                t = signal.get('time')
                if t is not None:
                    ts = t if hasattr(t, 'floor') else pd.Timestamp(t)
                    setup_ts = ts.floor('15min')
            if setup_ts is None:
                t = signal.get('time')
                if t is not None:
                    ts = t if hasattr(t, 'floor') else pd.Timestamp(t)
                    setup_ts = ts.floor('15min')
        if setup_ts is None:
            return None
        setup_str = setup_ts.isoformat() if hasattr(setup_ts, 'isoformat') else str(setup_ts)
        return (symbol, order_type, setup_str)

    def _check_setup_limit(self, signal):
        """Return (True, None) if OK to trade, else (False, reason)."""
        max_per_setup = None
        if self.strategy_name == 'vester':
            max_per_setup = getattr(config, 'VESTER_MAX_TRADES_PER_SETUP', None)
        if max_per_setup is None:
            max_per_setup = 1 if getattr(config, 'VESTER_ONE_SIGNAL_PER_SETUP', True) else None
        elif self.strategy_name == 'vee':
            max_per_setup = getattr(config, 'VEE_MAX_TRADES_PER_SETUP', None)
            if max_per_setup is None:
                max_per_setup = 3
        elif self.strategy_name == 'trend_vester':
            max_per_setup = getattr(config, 'TREND_VESTER_MAX_TRADES_PER_SETUP', 3)
        elif self.strategy_name == 'test-sl':
            max_per_setup = None  # One-shot: no setup limit
        if max_per_setup is None:
            return True, None
        key = self._get_setup_key(signal)
        if key is None:
            return True, None
        count = self._trades_per_setup.get(key, 0)
        if count >= max_per_setup:
            return False, f"Max trades per setup reached ({count}/{max_per_setup})"
        return True, None

    def _record_setup_trade(self, signal):
        """Increment trades-per-setup count after successful execution."""
        key = self._get_setup_key(signal)
        if key is not None:
            self._trades_per_setup[key] = self._trades_per_setup.get(key, 0) + 1

    def connect(self):
        return self.mt5.connect()

    def disconnect(self):
        self.mt5.disconnect()

    def check_safety_limits(self):
        now_utc = datetime.utcnow()
        today = now_utc.date()
        session_hours = getattr(config, 'TRADE_SESSION_HOURS', {})
        max_per_session = getattr(config, 'MAX_TRADES_PER_SESSION', None)
        self._limit_reason = None

        # Daily loss limit: stop new trades when today's closed P&L loss exceeds limit (live only)
        if not self.paper_mode and self.mt5.connected and getattr(config, 'ENABLE_DAILY_LOSS_LIMIT', True):
            limit_pct = getattr(config, f'{self.strategy_name.upper()}_DAILY_LOSS_LIMIT_PCT', None) or getattr(config, 'DAILY_LOSS_LIMIT_PCT', 5.0)
            today_pnl = self.mt5.get_today_deals_pnl()
            account = self.mt5.get_account_info()
            balance = account.get('balance', 0) or 0
            if balance > 0 and today_pnl < 0 and abs(today_pnl) >= balance * (limit_pct / 100):
                self._limit_reason = f"Daily loss limit reached ({today_pnl:.2f} >= {limit_pct}% of balance)"
                print(f"[SAFETY] {self._limit_reason}")
                return False

        # When per-pair mode: limits are checked per symbol in the signal loop
        if getattr(config, 'MAX_TRADES_PER_DAY_PER_PAIR', False):
            return True

        trades_today = [t for t in self.trades_today if t['time'].date() == today]
        if len(trades_today) >= config.MAX_TRADES_PER_DAY:
            self._limit_reason = "Daily trade limit reached"
            print(f"[SAFETY] Daily trade limit reached ({config.MAX_TRADES_PER_DAY})")
            return False

        if max_per_session is not None and session_hours:
            current_session = session_hours.get(now_utc.hour)
            if current_session is not None:
                trades_in_session = [
                    t for t in trades_today
                    if session_hours.get(t['time'].hour) == current_session
                ]
                if len(trades_in_session) >= max_per_session:
                    self._limit_reason = "Session trade limit reached"
                    print(f"[SAFETY] Session limit reached ({max_per_session} per {current_session})")
                    return False
        return True

    def _can_trade_symbol(self, symbol):
        """Check if we can trade this symbol (per-pair daily/session limits). Returns (True, None) or (False, reason)."""
        if not symbol:
            return True, None
        now_utc = datetime.utcnow()
        today = now_utc.date()
        session_hours = getattr(config, 'TRADE_SESSION_HOURS', {})
        max_per_session = getattr(config, 'MAX_TRADES_PER_SESSION', None)

        trades_today = [t for t in self.trades_today if t['time'].date() == today]
        trades_for_symbol = [t for t in trades_today if t.get('symbol') == symbol]

        if len(trades_for_symbol) >= config.MAX_TRADES_PER_DAY:
            return False, f"Daily limit reached for {symbol} ({config.MAX_TRADES_PER_DAY})"

        if max_per_session is not None and session_hours:
            current_session = session_hours.get(now_utc.hour)
            if current_session is not None:
                trades_in_session = [
                    t for t in trades_for_symbol
                    if session_hours.get(t['time'].hour) == current_session
                ]
                if len(trades_in_session) >= max_per_session:
                    return False, f"Session limit reached for {symbol} ({max_per_session} per {current_session})"
        return True, None

    def _get_symbol_for_bias(self):
        """Return the symbol used for bias-of-day and market-open check (matches strategy's trading symbol)."""
        if self.strategy_name == 'vester':
            from . import vester_config as vc
            if self.cli_symbol:
                symbol = config.cli_symbol_to_mt5(self.cli_symbol) or getattr(config, 'VESTER_LIVE_SYMBOL', vc.VESTER_LIVE_SYMBOL)
            else:
                symbol = getattr(config, 'VESTER_LIVE_SYMBOL', vc.VESTER_LIVE_SYMBOL)
        elif self.strategy_name == 'vee':
            from . import vee_config as vc
            if self.cli_symbol:
                symbol = config.cli_symbol_to_mt5(self.cli_symbol) or getattr(config, 'VEE_LIVE_SYMBOL', vc.VEE_LIVE_SYMBOL)
            else:
                symbol = getattr(config, 'VEE_LIVE_SYMBOL', vc.VEE_LIVE_SYMBOL)
        elif self.strategy_name == 'trend_vester':
            from . import vester_config as vc
            if self.cli_symbol:
                symbol = config.cli_symbol_to_mt5(self.cli_symbol) or getattr(config, 'TREND_VESTER_LIVE_SYMBOL', vc.VESTER_LIVE_SYMBOL)
            else:
                symbol = getattr(config, 'TREND_VESTER_LIVE_SYMBOL', vc.VESTER_LIVE_SYMBOL)
        elif self.strategy_name == 'test-sl':
            if self.cli_symbol:
                symbol = config.cli_symbol_to_mt5(self.cli_symbol) or config.LIVE_SYMBOLS.get('XAUUSD') or 'XAUUSDm'
            else:
                symbol = config.LIVE_SYMBOLS.get('XAUUSD') or 'XAUUSDm'
        else:
            if self.cli_symbol:
                symbol = config.cli_symbol_to_mt5(self.cli_symbol) or config.LIVE_SYMBOLS.get('XAUUSD') or 'XAUUSDm'
            else:
                symbol = config.LIVE_SYMBOLS.get('XAUUSD') or 'XAUUSDm'
        return symbol

    def _get_bias_of_day(self, symbol):
        """Compute ICT-style bias from last closed Daily and H1 bars (BOS). Returns {'daily': str, 'h1': str} or None."""
        result = {}
        for label, tf_const, count in [('daily', TIMEFRAME_D1, 50), ('h1', TIMEFRAME_H1, 200)]:
            df = self.mt5.get_bars(symbol, tf_const, count=count)
            if df is None or len(df) < 5:
                return None
            df = df.copy()
            df = detect_swing_highs_lows(df, swing_length=3)
            df = detect_break_of_structure(df)
            last_closed = df.iloc[-2] if len(df) >= 2 else df.iloc[-1]
            if last_closed.get('bos_bull'):
                result[label] = 'BULLISH'
            elif last_closed.get('bos_bear'):
                result[label] = 'BEARISH'
            else:
                result[label] = 'NEUTRAL'
        return result

    def run_strategy(self):
        symbol = (
            (config.cli_symbol_to_mt5(self.cli_symbol) if self.cli_symbol else None) or
            config.LIVE_SYMBOLS.get('XAUUSD') or
            config.LIVE_SYMBOLS.get('GOLD') or
            next((v for k, v in config.LIVE_SYMBOLS.items() if 'XAU' in k.upper() or 'GOLD' in k.upper()), None) or
            list(config.LIVE_SYMBOLS.values())[0]
        )
        if self.strategy_name == 'vester':
            from . import vester_config as vc
            cli_mt5 = config.cli_symbol_to_mt5(self.cli_symbol) if self.cli_symbol else None
            vester_live = getattr(config, 'VESTER_LIVE_SYMBOL', vc.VESTER_LIVE_SYMBOL)
            vester_symbols = list(dict.fromkeys([
                s for s in [cli_mt5, vester_live, symbol, 'XAUUSD', 'XAUUSDm'] if s
            ]))
            df_h1 = df_m5 = df_m1 = df_h4 = None
            agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
            for sym in vester_symbols:
                df_h1 = self.mt5.get_bars(sym, TIMEFRAME_H1, count=200)
                df_m5 = self.mt5.get_bars(sym, TIMEFRAME_M5, count=1000)
                df_m1 = self.mt5.get_bars(sym, TIMEFRAME_M1, count=1000)
                if all(x is not None for x in (df_h1, df_m5, df_m1)):
                    symbol = sym
                    df_h4 = df_h1.resample("4h").agg(agg).dropna()
                    break
            if df_h1 is None or df_m5 is None or df_m1 is None:
                if getattr(config, 'LIVE_DEBUG', False):
                    print(f"[LIVE_DEBUG] vester: Bar data missing (tried: {vester_symbols})")
                return []
            if getattr(config, 'LIVE_DEBUG', False):
                print(f"[LIVE_DEBUG] {symbol} vester: H1/M5/M1" + ("/4H" if df_h4 is not None else "") + " loaded")
            strat = VesterStrategy(
                df_h1=df_h1,
                df_m5=df_m5,
                df_m1=df_m1,
                df_h4=df_h4,
                symbol=symbol,
                verbose=False,
            )
            strat.prepare_data()
            only_last = getattr(config, 'VESTER_LIVE_ONLY_LAST_N_BARS', None)
            signals_df = strat.run_backtest(only_last_n_bars=only_last)
            if getattr(config, 'LIVE_DEBUG', False) and signals_df.empty:
                print(f"[LIVE_DEBUG] vester: 0 signals")
        elif self.strategy_name == 'trend_vester':
            from . import vester_config as vc
            cli_mt5 = config.cli_symbol_to_mt5(self.cli_symbol) if self.cli_symbol else None
            trend_live = getattr(config, 'TREND_VESTER_LIVE_SYMBOL', vc.VESTER_LIVE_SYMBOL)
            trend_symbols = list(dict.fromkeys([
                s for s in [cli_mt5, trend_live, symbol, 'XAUUSD', 'XAUUSDm'] if s
            ]))
            df_h1 = df_m5 = df_m1 = df_h4 = None
            agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
            for sym in trend_symbols:
                df_h1 = self.mt5.get_bars(sym, TIMEFRAME_H1, count=200)
                df_m5 = self.mt5.get_bars(sym, TIMEFRAME_M5, count=1000)
                df_m1 = self.mt5.get_bars(sym, TIMEFRAME_M1, count=1000)
                if all(x is not None for x in (df_h1, df_m5, df_m1)):
                    symbol = sym
                    df_h4 = df_h1.resample("4h").agg(agg).dropna()
                    break
            if df_h1 is None or df_m5 is None or df_m1 is None:
                if getattr(config, 'LIVE_DEBUG', False):
                    print(f"[LIVE_DEBUG] trend_vester: Bar data missing (tried: {trend_symbols})")
                return []
            if getattr(config, 'LIVE_DEBUG', False):
                print(f"[LIVE_DEBUG] {symbol} trend_vester: H1/M5/M1 loaded")
            strat = TrendVesterStrategy(
                df_h1=df_h1,
                df_m5=df_m5,
                df_m1=df_m1,
                df_h4=df_h4,
                symbol=symbol,
                verbose=False,
            )
            strat.prepare_data()
            only_last = getattr(config, 'TREND_VESTER_LIVE_ONLY_LAST_N_BARS', None)
            signals_df = strat.run_backtest(only_last_n_bars=only_last)
            if getattr(config, 'LIVE_DEBUG', False) and signals_df.empty:
                print(f"[LIVE_DEBUG] trend_vester: 0 signals")
        elif self.strategy_name == 'test-sl':
            cli_mt5 = config.cli_symbol_to_mt5(self.cli_symbol) if self.cli_symbol else None
            test_symbols = list(dict.fromkeys([
                s for s in [cli_mt5, symbol, 'XAUUSD', 'XAUUSDm'] if s
            ]))
            tick = None
            for sym in test_symbols:
                tick = self.mt5.get_live_price(sym)
                if tick is not None:
                    symbol = sym
                    break
            if tick is None:
                print("[test-sl] No live tick - cannot place test trade")
                return []
            price = float(tick.get('ask', 0))
            if price <= 0:
                return []
            is_gold = config.is_gold_symbol(symbol) if hasattr(config, 'is_gold_symbol') else ("XAU" in str(symbol or "").upper())
            if is_gold:
                sl_dist = getattr(config, 'GOLD_MANUAL_SL_POINTS', 5.0)
            else:
                info = self.mt5.get_symbol_info(symbol)
                point = float(info.get('point', 0.00001) or 0.00001)
                sl_dist = 50 * 10 * point
            sl = price - sl_dist
            tp = price + sl_dist * getattr(config, 'RISK_REWARD_RATIO', 5.0)
            signals_df = pd.DataFrame([{
                'time': pd.Timestamp.utcnow(),
                'type': 'BUY',
                'price': price,
                'sl': sl,
                'tp': tp,
                'reason': 'test-sl: lot size test',
                'setup_5m': pd.Timestamp.utcnow().floor('5min'),
            }])
        elif self.strategy_name == 'vee':
            from . import vee_config as vc
            cli_mt5 = config.cli_symbol_to_mt5(self.cli_symbol) if self.cli_symbol else None
            vee_live = getattr(config, 'VEE_LIVE_SYMBOL', vc.VEE_LIVE_SYMBOL)
            vee_symbols = list(dict.fromkeys([s for s in [cli_mt5, vee_live, symbol] if s]))
            df_h1 = df_m15 = df_m1 = None
            for sym in vee_symbols:
                df_h1 = self.mt5.get_bars(sym, TIMEFRAME_H1, count=200)
                df_m15 = self.mt5.get_bars(sym, TIMEFRAME_M15, count=1000)
                df_m1 = self.mt5.get_bars(sym, TIMEFRAME_M1, count=1000)
                if all(x is not None for x in (df_h1, df_m15, df_m1)):
                    symbol = sym
                    break
            if df_h1 is None or df_m15 is None or df_m1 is None:
                if getattr(config, 'LIVE_DEBUG', False):
                    print(f"[LIVE_DEBUG] vee: Bar data missing (tried: {vee_symbols})")
                return []
            strat = VeeStrategy(
                df_h1=df_h1,
                df_m15=df_m15,
                df_m1=df_m1,
                symbol=symbol,
                verbose=False,
            )
            only_last = getattr(config, 'VEE_LIVE_ONLY_LAST_N_BARS', None)
            signals_df = strat.run_backtest(only_last_n_bars=only_last)
            if getattr(config, 'LIVE_DEBUG', False) and signals_df.empty:
                print(f"[LIVE_DEBUG] vee: 0 signals")
        else:
            print(f"Unknown strategy: {self.strategy_name}")
            return []
        if signals_df.empty:
            return []
        latest_signal = signals_df.iloc[-1].to_dict() if not signals_df.empty else None
        if latest_signal:
            tick = self.mt5.get_live_price(symbol)
            if tick is None:
                if getattr(config, 'LIVE_DEBUG', False):
                    print(f"[LIVE_DEBUG] No live tick for {symbol} - cannot get entry price")
            elif tick:
                latest_signal['symbol'] = symbol
                latest_signal['price'] = tick['ask'] if latest_signal['type'] == 'BUY' else tick['bid']
                # Vester/Vee/TrendVester: add buffer below/above so slight price move doesn't invalidate SL
                if self.strategy_name in ('vester', 'vee', 'trend_vester'):
                    sl = latest_signal.get('sl')
                    if sl is not None:
                        buf_key = 'VESTER_SL_BUFFER' if self.strategy_name in ('vester', 'trend_vester') else 'VEE_SL_BUFFER_POINTS'
                        buf = config.get_symbol_config(symbol, buf_key) or getattr(config, buf_key, 1.0)
                        try:
                            sl_f = float(sl)
                            if latest_signal['type'] == 'BUY':
                                latest_signal['sl'] = sl_f - buf  # Move SL lower for BUY
                            else:
                                latest_signal['sl'] = sl_f + buf  # Move SL higher for SELL
                        except (TypeError, ValueError):
                            pass
                # Cap SL at MAX_SL_PIPS (converted per symbol's pip size)
                # Use PIP_SIZE from SYMBOL_CONFIGS if set, else MT5's get_pip_size (e.g. gold 0.10)
                max_sl_pips = getattr(config, 'MAX_SL_PIPS', None)
                if max_sl_pips is not None and max_sl_pips > 0 and self.mt5.connected:
                    pip_size = config.get_symbol_config(symbol, 'PIP_SIZE')
                    if pip_size is None:
                        pip_size = self.mt5.get_pip_size(symbol)
                    if pip_size is not None and pip_size > 0:
                        max_dist = max_sl_pips * pip_size
                        price_f = float(latest_signal['price'])
                        sl = latest_signal.get('sl')
                        if sl is not None:
                            try:
                                sl_f = float(sl)
                                sl_dist = abs(price_f - sl_f)
                                if sl_dist > max_dist:
                                    if latest_signal['type'] == 'BUY':
                                        latest_signal['sl'] = price_f - max_dist
                                    else:
                                        latest_signal['sl'] = price_f + max_dist
                            except (TypeError, ValueError):
                                pass

                # Gold manual: override SL to fixed distance (50 pips = 5 points = $10 risk with 0.02 lots)
                _is_gold = config.is_gold_symbol(symbol) if hasattr(config, 'is_gold_symbol') else ("XAU" in str(symbol or "").upper() or "GOLD" in str(symbol or "").upper())
                _use_manual = getattr(config, 'GOLD_USE_MANUAL_LOT', True)
                if _is_gold and _use_manual:
                    sl_points = getattr(config, 'GOLD_MANUAL_SL_POINTS', 5.0)
                    price_f = float(latest_signal['price'])
                    if latest_signal['type'] == 'BUY':
                        latest_signal['sl'] = price_f - sl_points
                    else:
                        latest_signal['sl'] = price_f + sl_points

                # Gold: override SL to fixed distance when GOLD_MANUAL_SL_POINTS set (50 pips = 5 points)
                _is_gold = config.is_gold_symbol(symbol) if hasattr(config, 'is_gold_symbol') else ("XAU" in str(symbol or "").upper() or "GOLD" in str(symbol or "").upper())
                _sl_points = getattr(config, 'GOLD_MANUAL_SL_POINTS', 0)
                if _is_gold and _sl_points > 0:
                    price_f = float(latest_signal['price'])
                    if latest_signal['type'] == 'BUY':
                        latest_signal['sl'] = price_f - _sl_points
                    else:
                        latest_signal['sl'] = price_f + _sl_points

                # Use strategy-specific RR when available (closer TP can materially increase win rate)
                rr_ratio = getattr(config, "RISK_REWARD_RATIO", 5.0)
                if self.strategy_name in ("vester", "trend_vester"):
                    rr_ratio = getattr(config, "VESTER_MIN_RR", rr_ratio)
                elif self.strategy_name == "vee":
                    rr_ratio = getattr(config, "VEE_MIN_RR", rr_ratio)
                sl_dist = abs(latest_signal['price'] - latest_signal.get('sl', 0))
                if latest_signal['type'] == 'BUY':
                    latest_signal['tp'] = latest_signal['price'] + (sl_dist * rr_ratio)
                else:
                    latest_signal['tp'] = latest_signal['price'] - (sl_dist * rr_ratio)
                # Lot size: dynamic (balance × risk %) when GOLD_USE_MANUAL_LOT=False; fixed when True
                use_manual_for_gold = getattr(config, 'GOLD_USE_MANUAL_LOT', True)
                is_gold = config.is_gold_symbol(symbol) if hasattr(config, 'is_gold_symbol') else ("XAU" in str(symbol or "").upper() or "GOLD" in str(symbol or "").upper())
                use_dynamic = (
                    getattr(config, 'USE_DYNAMIC_POSITION_SIZING', True)
                    and (not is_gold or not use_manual_for_gold)
                    and self.mt5.connected
                )
                if use_dynamic:
                    account = self.paper.get_account_info() if self.paper_mode else self.mt5.get_account_info()
                    balance = account['balance'] if account else 0
                    sl = latest_signal.get('sl')
                    if sl is not None and balance > 0:
                        risk_pct = getattr(config, 'VESTER_RISK_PER_TRADE', config.RISK_PER_TRADE) if self.strategy_name in ('vester', 'trend_vester') else (getattr(config, 'VEE_RISK_PER_TRADE', config.RISK_PER_TRADE) if self.strategy_name == 'vee' else config.RISK_PER_TRADE)
                        lot = self.mt5.calc_lot_size_from_risk(
                            symbol, balance, latest_signal['price'], sl, risk_pct
                        )
                        if lot is not None:
                            latest_signal['volume'] = lot
                            # Log how 10% risk translated to lot (rounding to lot step can make actual < 10%)
                            target_risk = balance * risk_pct
                            actual_risk = self.mt5.calc_dollar_risk(
                                symbol, latest_signal['price'], sl, lot
                            )
                            if actual_risk is not None:
                                print(f"[RISK] Balance ${balance:.2f} | {risk_pct*100:.0f}% target ${target_risk:.2f} | lot {lot} → risk ${actual_risk:.2f}")
                            # Safety cap: never risk more than MAX_RISK_PCT_LIVE
                            max_risk_pct = getattr(config, 'MAX_RISK_PCT_LIVE', None)
                            if max_risk_pct is not None and max_risk_pct > 0:
                                dollar_risk = self.mt5.calc_dollar_risk(
                                    symbol, latest_signal['price'], sl, lot
                                )
                                if dollar_risk is not None and dollar_risk > 0:
                                    max_risk_dollars = balance * max_risk_pct
                                    if dollar_risk > max_risk_dollars:
                                        lot = max(0.01, round(lot * max_risk_dollars / dollar_risk, 2))
                                        latest_signal['volume'] = lot
                if latest_signal.get('volume') is None:
                    latest_signal['volume'] = config.MAX_POSITION_SIZE
                return [latest_signal]
        return []

    def _validate_signal_sl(self, signal):
        sl = signal.get('sl')
        if sl is None:
            return False, "No stop loss"
        try:
            sl = float(sl)
        except (TypeError, ValueError):
            return False, "Stop loss invalid"
        price = signal.get('price')
        if price is None:
            return True, None
        try:
            price = float(price)
        except (TypeError, ValueError):
            return True, None
        order_type = signal.get('type')
        if order_type == 'BUY' and sl >= price:
            return False, "Stop loss invalid"
        if order_type == 'SELL' and sl <= price:
            return False, "Stop loss invalid"
        return True, None

    def _allowed_same_symbol_entry(self, signal):
        """Allow new entry on same symbol only when we have no position or when adding at TP1/TP2."""
        symbol = signal.get('symbol')
        if not symbol:
            return True, None
        if getattr(config, 'ALLOW_MULTIPLE_SAME_SYMBOL', False):
            return True, None
        entry_price = signal.get('price')
        if entry_price is None:
            return True, None
        try:
            entry_price = float(entry_price)
        except (TypeError, ValueError):
            return True, None
        if self.paper_mode:
            positions = [p for p in self.paper.get_positions() if p.get('symbol') == symbol]
        else:
            positions = [p for p in self.mt5.get_positions() if p.get('symbol') == symbol]
        if not positions:
            return True, None
        if not getattr(config, 'ALLOW_SAME_SYMBOL_AT_TP', True):
            return False, "Same symbol has open position (ALLOW_SAME_SYMBOL_AT_TP is False)"
        threshold = getattr(config, 'AT_TP_POINTS', 5.0)
        for pos in positions:
            tp = pos.get('tp')
            if tp is None:
                continue
            try:
                tp = float(tp)
                price_open = pos.get('price_open')
                if price_open is not None:
                    price_open = float(price_open)
                    # TP2 = same direction as TP1, double the distance from open to TP1
                    if pos.get('type') == 'BUY':
                        tp2 = price_open + 2.0 * (tp - price_open)
                    else:
                        tp2 = price_open - 2.0 * (price_open - tp)
                else:
                    tp2 = None
            except (TypeError, ValueError):
                tp2 = None
            if abs(entry_price - tp) <= threshold:
                return True, None
            if tp2 is not None and abs(entry_price - tp2) <= threshold:
                return True, None
        return False, "Same symbol has open position; add only at TP1/TP2"

    def execute_signal(self, signal):
        valid, sl_reason = self._validate_signal_sl(signal)
        if not valid:
            print(f"[SAFETY] Rejected: {sl_reason}")
            if getattr(config, 'LIVE_DEBUG', False) and "Stop loss" in sl_reason:
                price = signal.get('price')
                sl = signal.get('sl')
                order_type = signal.get('type')
                try:
                    dist = abs(float(price) - float(sl)) if price is not None and sl is not None else None
                    print(f"[LIVE_DEBUG]   price={price} sl={sl} type={order_type} dist={dist:.2f}" if dist is not None else f"[LIVE_DEBUG]   price={price} sl={sl} type={order_type}")
                except (TypeError, ValueError):
                    print(f"[LIVE_DEBUG]   price={price} sl={sl} type={order_type}")
            if config.VOICE_ALERTS and config.VOICE_ALERT_ON_REJECT:
                speak(f"Trade rejected. Reason: {sl_reason}.")
            return None, sl_reason
        allowed, same_symbol_reason = self._allowed_same_symbol_entry(signal)
        if not allowed:
            print(f"[SAFETY] Rejected: {same_symbol_reason}")
            if config.VOICE_ALERTS and config.VOICE_ALERT_ON_REJECT:
                speak(f"Trade rejected. Reason: {same_symbol_reason}.")
            return None, same_symbol_reason
        if not self.paper_mode and config.USE_MARGIN_CHECK:
            account_info = self.mt5.get_account_info()
            if account_info:
                required = self.mt5.calc_required_margin(
                    signal['symbol'], signal['type'], signal['volume'], signal['price']
                )
                if required is not None and account_info['free_margin'] < required:
                    err = f"Insufficient margin (free: {account_info['free_margin']:.2f}, required: {required:.2f})"
                    print(f"[SAFETY] Rejected: {err}")
                    if config.VOICE_ALERTS and config.VOICE_ALERT_ON_REJECT:
                        speak("Trade rejected. Reason: Insufficient margin.")
                    return None, err
        if config.AI_ENABLED:
            score = get_signal_confidence(signal)
            if score is not None and score < config.AI_CONFIDENCE_THRESHOLD:
                err = f"AI confidence {score} below threshold"
                print(f"[AI] Rejected: {err}")
                if config.VOICE_ALERTS and config.VOICE_ALERT_ON_REJECT:
                    speak("Trade rejected. Reason: Below confidence threshold.")
                return None, err
        if config.MANUAL_APPROVAL:
            account_info = self.paper.get_account_info() if self.paper_mode else self.mt5.get_account_info()
            if not self.approver.request_approval(signal, account_info):
                print("[REJECTED] Trade not approved by user")
                if config.VOICE_ALERTS and config.VOICE_ALERT_ON_REJECT:
                    speak("Trade rejected. Reason: Not approved by user.")
                return None, "User rejected"
        vol = signal['volume']
        if not self.paper_mode:
            max_lot = getattr(config, 'MAX_LOT_LIVE', None)
            if max_lot is not None and vol > max_lot:
                vol = max_lot
                signal = {**signal, 'volume': vol}
        if self.paper_mode:
            result = self.paper.place_order(
                symbol=signal['symbol'],
                order_type=signal['type'],
                volume=vol,
                price=signal['price'],
                sl=signal['sl'],
                tp=signal['tp'],
                comment=config.MT5_ORDER_COMMENT or signal.get('reason', '')
            )
            mt5_err = None
        else:
            _comment = config.MT5_ORDER_COMMENT if config.MT5_ORDER_COMMENT is not None else signal.get('reason', '')
            result, mt5_err = None, None
            retry_count = getattr(config, 'ENTRY_RETRY_COUNT', 0) or 0
            retry_delay = getattr(config, 'ENTRY_RETRY_DELAY_SEC', 1) or 1
            for attempt in range(retry_count + 1):
                result, mt5_err = self.mt5.place_order(
                    symbol=signal['symbol'],
                    order_type=signal['type'],
                    volume=vol,
                    price=signal['price'],
                    sl=signal['sl'],
                    tp=signal['tp'],
                    comment=_comment
                )
                if result is not None:
                    break
                if attempt < retry_count and retry_delay > 0:
                    time.sleep(retry_delay)
        if result:
            result['time'] = datetime.utcnow()
            self.trades_today.append(result)
            if not self.paper_mode and getattr(config, 'LIVE_TRADE_LOG', False):
                self._log_trade(signal, result)
            if config.VOICE_ALERTS and config.VOICE_ALERT_ON_SIGNAL:
                speak(f"Trade executed. {signal['type']} {signal['symbol']} at {signal['price']}.")
            if config.AI_EXPLAIN_TRADES:
                summary = {
                    'reason': signal.get('reason', ''),
                    'symbol': signal.get('symbol', ''),
                    'type': signal.get('type', ''),
                    'price': signal.get('price'),
                    'sl': signal.get('sl'),
                    'tp': signal.get('tp'),
                    'outcome': 'opened',
                }
                explanation = explain_trade(summary)
                if explanation:
                    result['ai_explain'] = explanation
                    print(f"[AI] {explanation}")
            return result, None
        return None, mt5_err if not self.paper_mode else "Paper order failed"

    def update_positions(self):
        if self.paper_mode:
            closed = self.paper.update_positions(self.mt5)
            if closed:
                print(f"[UPDATE] {len(closed)} positions closed automatically")

    def _check_breakeven(self):
        """When price reaches BREAKEVEN_TRIGGER_RR (e.g. 1R), move SL to entry. Live only. Runs before lock-in.
        When strategy is vee, uses VEE_BREAKEVEN_TRIGGER_RR."""
        if self.paper_mode or not getattr(config, 'BREAKEVEN_ENABLED', True):
            return
        if self.strategy_name == 'vee':
            trigger_rr = getattr(config, 'VEE_BREAKEVEN_TRIGGER_RR', 1.0)
        else:
            trigger_rr = getattr(config, 'BREAKEVEN_TRIGGER_RR', 1.0)
        positions = self.mt5.get_positions()
        for pos in positions:
            ticket = pos.get('ticket')
            symbol = pos.get('symbol')
            price_open = pos.get('price_open')
            sl = pos.get('sl')
            tp = pos.get('tp')
            pos_type = pos.get('type')
            if ticket is None or symbol is None or price_open is None or sl is None or sl == 0:
                continue
            try:
                price_open = float(price_open)
                sl = float(sl)
            except (TypeError, ValueError):
                continue
            sl_dist = abs(price_open - sl)
            if sl_dist <= 0:
                continue
            be_sl = price_open
            if pos_type == 'BUY':
                sl_at_be = sl >= be_sl - 0.00001
                trigger = price_open + sl_dist * trigger_rr
            else:
                sl_at_be = sl <= be_sl + 0.00001
                trigger = price_open - sl_dist * trigger_rr
            if sl_at_be:
                continue
            tick = self.mt5.get_live_price(symbol)
            if not tick:
                continue
            current = float(tick.get('bid' if pos_type == 'BUY' else 'ask') or 0)
            if current == 0:
                continue
            triggered = (pos_type == 'BUY' and current >= trigger) or (pos_type == 'SELL' and current <= trigger)
            if not triggered:
                continue
            ok, err = self.mt5.modify_position(ticket, sl=be_sl, tp=tp)
            if ok:
                print(f"[BREAKEVEN] Position {ticket} SL moved to entry {be_sl:.5f} (price reached {trigger_rr}R)")
            elif getattr(config, 'MT5_VERBOSE', False):
                print(f"[BREAKEVEN] Failed to move SL for {ticket}: {err}")

    def _check_lock_in(self):
        """When price reaches LOCK_IN_TRIGGER_RR (e.g. 3.3R), move SL to LOCK_IN_AT_RR (e.g. 3R). Live only.
        When strategy is vee, uses VEE_LOCK_IN_*."""
        if self.paper_mode or not getattr(config, 'LOCK_IN_ENABLED', True):
            return
        if self.strategy_name == 'vee':
            trigger_rr = getattr(config, 'VEE_LOCK_IN_TRIGGER_RR', 3.3)
            lock_at_rr = getattr(config, 'VEE_LOCK_IN_AT_RR', 3.0)
        else:
            trigger_rr = getattr(config, 'LOCK_IN_TRIGGER_RR', 3.3)
            lock_at_rr = getattr(config, 'LOCK_IN_AT_RR', 3.0)
        risk_ratio = getattr(config, 'RISK_REWARD_RATIO', 5.0)
        positions = self.mt5.get_positions()
        for pos in positions:
            ticket = pos.get('ticket')
            symbol = pos.get('symbol')
            price_open = pos.get('price_open')
            tp = pos.get('tp')
            sl = pos.get('sl')
            pos_type = pos.get('type')
            if ticket is None or symbol is None or price_open is None or tp is None:
                continue
            try:
                price_open = float(price_open)
                tp = float(tp)
                sl = float(sl) if sl is not None and sl != 0 else None
            except (TypeError, ValueError):
                continue
            if self.strategy_name == 'vee' and sl is not None:
                sl_dist = abs(price_open - sl)
            else:
                sl_dist = abs(tp - price_open) / risk_ratio
            if sl_dist <= 0:
                continue
            if pos_type == 'BUY':
                lock_in_trigger = price_open + sl_dist * trigger_rr
                lock_in_sl = price_open + sl_dist * lock_at_rr
                sl_ok = sl is not None and sl != 0 and float(sl) >= lock_in_sl - 0.00001
            else:
                lock_in_trigger = price_open - sl_dist * trigger_rr
                lock_in_sl = price_open - sl_dist * lock_at_rr
                sl_ok = sl is not None and sl != 0 and float(sl) <= lock_in_sl + 0.00001
            if sl_ok:
                continue
            tick = self.mt5.get_live_price(symbol)
            if not tick:
                continue
            current = float(tick.get('bid' if pos_type == 'BUY' else 'ask') or 0)
            if current == 0:
                continue
            triggered = (pos_type == 'BUY' and current >= lock_in_trigger) or (pos_type == 'SELL' and current <= lock_in_trigger)
            if not triggered:
                continue
            ok, err = self.mt5.modify_position(ticket, sl=lock_in_sl, tp=tp)
            if ok:
                print(f"[LOCK-IN] Position {ticket} SL moved to {lock_at_rr}R at {lock_in_sl:.5f} (price reached {trigger_rr}R)")
            elif getattr(config, 'MT5_VERBOSE', False):
                print(f"[LOCK-IN] Failed to move SL for {ticket}: {err}")

    def _check_trailing_sl(self):
        """When price moved in favor by TRAILING_SL_ACTIVATION_R, trail SL by TRAILING_SL_DISTANCE_PIPS (only tightens). Live only."""
        if self.paper_mode or not getattr(config, 'TRAILING_SL_ENABLED', False):
            return
        activation_r = getattr(config, 'TRAILING_SL_ACTIVATION_R', 1.0)
        distance_pips = getattr(config, 'TRAILING_SL_DISTANCE_PIPS', 20.0)
        atr_mult = getattr(config, 'TRAILING_SL_ATR_MULT', None)
        risk_ratio = getattr(config, 'RISK_REWARD_RATIO', 5.0)
        positions = self.mt5.get_positions()
        for pos in positions:
            ticket = pos.get('ticket')
            symbol = pos.get('symbol')
            price_open = pos.get('price_open')
            sl = pos.get('sl')
            tp = pos.get('tp')
            pos_type = pos.get('type')
            if ticket is None or symbol is None or price_open is None:
                continue
            try:
                price_open = float(price_open)
                sl = float(sl) if sl is not None and sl != 0 else None
            except (TypeError, ValueError):
                continue
            if sl is None:
                continue
            sl_dist = abs(price_open - sl)
            if sl_dist <= 0:
                continue
            activation_price = (price_open + sl_dist * activation_r) if pos_type == 'BUY' else (price_open - sl_dist * activation_r)
            tick = self.mt5.get_live_price(symbol)
            if not tick:
                continue
            current = float(tick.get('bid' if pos_type == 'BUY' else 'ask') or 0)
            if current == 0:
                continue
            if pos_type == 'BUY' and current < activation_price:
                continue
            if pos_type == 'SELL' and current > activation_price:
                continue
            pip_size = self.mt5.get_pip_size(symbol)
            if pip_size is None or pip_size <= 0:
                pip_size = 0.0001
            if atr_mult is not None and atr_mult > 0:
                atr_val = self.mt5.get_atr(symbol, 14)
                trail_dist = (atr_val or sl_dist * 0.1) * atr_mult
            else:
                trail_dist = distance_pips * pip_size
            if pos_type == 'BUY':
                new_sl = current - trail_dist
                if new_sl <= sl or new_sl >= current:
                    continue
            else:
                new_sl = current + trail_dist
                if new_sl >= sl or new_sl <= current:
                    continue
            ok, err = self.mt5.modify_position(ticket, sl=new_sl, tp=tp)
            if ok:
                print(f"[TRAILING-SL] Position {ticket} SL moved to {new_sl:.5f}")
            elif getattr(config, 'MT5_VERBOSE', False):
                print(f"[TRAILING-SL] Failed {ticket}: {err}")

    def _check_partial_tp(self):
        """When price hits TP1 (PARTIAL_TP_TP1_R), close PARTIAL_TP_CLOSE_PCT of position. Live only."""
        if self.paper_mode or not getattr(config, 'PARTIAL_TP_ENABLED', False):
            return
        tp1_r = getattr(config, 'PARTIAL_TP_TP1_R', 1.5)
        close_pct = getattr(config, 'PARTIAL_TP_CLOSE_PCT', 50) or 50
        risk_ratio = getattr(config, 'RISK_REWARD_RATIO', 5.0)
        if not hasattr(self, '_partial_tp_done'):
            self._partial_tp_done = set()
        positions = self.mt5.get_positions()
        open_tickets = {p.get('ticket') for p in positions if p.get('ticket') is not None}
        self._partial_tp_done &= open_tickets  # drop closed positions from set
        for pos in positions:
            ticket = pos.get('ticket')
            symbol = pos.get('symbol')
            price_open = pos.get('price_open')
            sl = pos.get('sl')
            tp = pos.get('tp')
            volume = pos.get('volume')
            pos_type = pos.get('type')
            if ticket is None or ticket in self._partial_tp_done or symbol is None or price_open is None or volume is None:
                continue
            try:
                price_open = float(price_open)
                sl = float(sl) if sl is not None and sl != 0 else None
                volume = float(volume)
            except (TypeError, ValueError):
                continue
            if sl is None:
                sl_dist = abs(float(tp) - price_open) / risk_ratio if tp else 0
            else:
                sl_dist = abs(price_open - sl)
            if sl_dist <= 0:
                continue
            tp1_price = (price_open + sl_dist * tp1_r) if pos_type == 'BUY' else (price_open - sl_dist * tp1_r)
            tick = self.mt5.get_live_price(symbol)
            if not tick:
                continue
            current = float(tick.get('bid' if pos_type == 'BUY' else 'ask') or 0)
            if pos_type == 'BUY' and current < tp1_price:
                continue
            if pos_type == 'SELL' and current > tp1_price:
                continue
            vol_to_close = round(volume * (close_pct / 100.0), 2)
            if vol_to_close <= 0:
                continue
            ok, err = self.mt5.close_position_partial(ticket, vol_to_close)
            if ok:
                self._partial_tp_done.add(ticket)
                print(f"[PARTIAL-TP] Position {ticket} closed {close_pct}% at TP1 ({tp1_r}R)")
            elif getattr(config, 'MT5_VERBOSE', False):
                print(f"[PARTIAL-TP] Failed {ticket}: {err}")

    def _log_trade(self, signal, result):
        """Append trade to logs/trades_YYYYMMDD.json."""
        import json
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        today = datetime.now().strftime('%Y%m%d')
        log_path = os.path.join(log_dir, f'trades_{today}.json')
        entry = {
            'time': result.get('time', datetime.now()).isoformat() if hasattr(result.get('time', datetime.now()), 'isoformat') else str(result.get('time')),
            'symbol': signal.get('symbol', ''),
            'type': signal.get('type', ''),
            'price': signal.get('price'),
            'sl': signal.get('sl'),
            'tp': signal.get('tp'),
            'volume': signal.get('volume'),
            'ticket': result.get('ticket') or result.get('order') or result.get('deal'),
        }
        try:
            if os.path.exists(log_path):
                with open(log_path, 'r') as f:
                    data = json.load(f)
                if not isinstance(data, list):
                    data = [data]
            else:
                data = []
            data.append(entry)
            with open(log_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            if getattr(config, 'MT5_VERBOSE', False):
                print(f"[LOG] Failed to write trade log: {e}")

    def show_status(self):
        if self.paper_mode:
            account = self.paper.get_account_info()
            stats = self.paper.get_stats()
            print("\n" + "=" * 50)
            print(f"PAPER TRADING STATUS [{self.strategy_name}] - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 50)
            print(f"Balance: ${account['balance']:.2f}")
            print(f"Equity: ${account['equity']:.2f}")
            print(f"Profit: ${account['profit']:.2f}")
            print(f"\nOpen Positions: {len(self.paper.get_positions())}")
            print(f"Total Trades: {stats['total_trades']}")
            print(f"Win Rate: {stats['win_rate']:.1f}%")
            print(f"Return: {stats['return_pct']:.2f}%")
            print("=" * 50)
        else:
            account = self.mt5.get_account_info()
            positions = self.mt5.get_positions()
            print("\n" + "=" * 50)
            print(f"LIVE TRADING STATUS [{self.strategy_name}] - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 50)
            print(f"Balance: ${account['balance']:.2f}")
            print(f"Equity: ${account['equity']:.2f}")
            print(f"Profit: ${account['profit']:.2f}")
            print(f"Margin: ${account['margin']:.2f}")
            print(f"Free Margin: ${account['free_margin']:.2f}")
            print(f"\nOpen Positions: {len(positions)}")
            print(f"Total Trades: {len(self.trades_today)}")
            print("=" * 50)

    def run(self):
        print(f"\nStarting {'PAPER' if self.paper_mode else 'LIVE'} trading engine...")
        print(f"Strategy: {self.strategy_name}")
        print(f"Check interval: {config.LIVE_CHECK_INTERVAL}s")
        print(f"Manual approval: {'ON' if config.MANUAL_APPROVAL else 'OFF'}")
        session_limit = getattr(config, 'MAX_TRADES_PER_SESSION', None)
        per_pair = getattr(config, 'MAX_TRADES_PER_DAY_PER_PAIR', False)
        limit_str = f"{config.MAX_TRADES_PER_DAY}/day per pair" if per_pair else f"{config.MAX_TRADES_PER_DAY}/day"
        print(f"Max trades: {limit_str}" + (f" ({session_limit} per session per pair)" if per_pair and session_limit else (f" ({session_limit} per session)" if session_limit else "")))
        if not self.paper_mode and getattr(config, 'PRINT_CHECKLIST_ON_START', True):
            _print_live_checklist()
        if not self.paper_mode and getattr(config, 'LIVE_CONFIRM_ON_START', False):
            resp = input("LIVE MODE — REAL MONEY. Type 'yes' to continue: ").strip().lower()
            if resp != 'yes':
                print("Aborted.")
                return
        print("Press Ctrl+C to stop\n")
        self.running = True
        last_signal_time = None
        self._last_run_errors = []  # Capture why trade wasn't executed
        try:
            while self.running:
                # Pre-check: Algo Trading must be enabled for live orders
                if not self.paper_mode and not self.mt5.is_algo_trading_enabled():
                    print("\n" + "=" * 50)
                    print("BLOCKED: Algo Trading is DISABLED in MT5.")
                    print("  Enable it: click the 'Algo Trading' button in the MT5 toolbar (it must be GREEN).")
                    print("  Then run the bot again.")
                    print("=" * 50)
                    self.running = False
                    break
                if not self.check_safety_limits():
                    reason = getattr(self, '_limit_reason', 'Trade limit reached')
                    if config.VOICE_ALERTS and config.VOICE_ALERT_ON_REJECT:
                        speak(f"Trade rejected. Reason: {reason}.")
                    print(f"Waiting... ({reason})")
                    time.sleep(config.LIVE_CHECK_INTERVAL)
                    continue
                # Skip strategy run when market is closed (weekend or trade disabled)
                if getattr(config, 'SKIP_WHEN_MARKET_CLOSED', True):
                    sym = self._get_symbol_for_bias()
                    if self.mt5.connected and not self.mt5.is_market_open(sym):
                        if getattr(config, 'MT5_VERBOSE', False):
                            print(f"[MT5] Market closed for {sym} (weekend or trading disabled). Skipping.")
                        time.sleep(config.LIVE_CHECK_INTERVAL)
                        continue
                self.update_positions()
                self._check_breakeven()
                self._check_lock_in()
                self._check_trailing_sl()
                self._check_partial_tp()
                self._last_run_errors = []
                if getattr(config, "SHOW_BIAS_OF_DAY", False) and not self.paper_mode and self.mt5.connected:
                    sym = self._get_symbol_for_bias()
                    bias = self._get_bias_of_day(sym)
                    if bias is not None:
                        print(f"[BIAS OF DAY] Daily: {bias['daily']} | H1: {bias['h1']} ({sym})")
                if getattr(config, "MT5_VERBOSE", False):
                    print(f"[MT5] Running strategy check...")
                signals = self.run_strategy()
                if signals:
                    print(f"\n[MT5] Got {len(signals)} signal(s). Attempting execution...")
                for signal in signals:
                    # Skip signals that would fail SL validation (e.g. strategy emitted SL on wrong side)
                    valid, sl_reason = self._validate_signal_sl(signal)
                    if not valid:
                        err = f"Invalid SL: {sl_reason}"
                        self._last_run_errors.append(err)
                        print(f"[SKIP] Invalid signal: {sl_reason} (price={signal.get('price')} sl={signal.get('sl')} type={signal.get('type')})")
                        continue
                    signal_time = signal.get('time', datetime.now())
                    if isinstance(signal_time, pd.Timestamp):
                        signal_time = signal_time.to_pydatetime()
                    # Staleness handled by only_last_n_bars in strategy (current bar only); no separate max-age check
                    if last_signal_time and abs((signal_time - last_signal_time).total_seconds()) < 300:
                        self._last_run_errors.append("5 min cooldown")
                        print(f"[SKIP] Signal within 5 min of last execution (cooldown)")
                        continue
                    if getattr(config, 'MAX_TRADES_PER_DAY_PER_PAIR', False):
                        can_trade, limit_reason = self._can_trade_symbol(signal.get('symbol', ''))
                        if not can_trade:
                            print(f"[SKIP] {limit_reason}")
                            continue
                    can_setup, setup_reason = self._check_setup_limit(signal)
                    if not can_setup:
                        self._last_run_errors.append(setup_reason)
                        print(f"[SKIP] {setup_reason}")
                        continue
                    sl = signal.get('sl')
                    sl_dist = abs(float(signal['price']) - float(sl)) if sl is not None else None
                    dollar_risk = self.mt5.calc_dollar_risk(
                        signal['symbol'], signal['price'], sl, signal.get('volume', 0)
                    ) if sl is not None else None
                    sl_info = ""
                    if sl is not None:
                        sl_info = f" | SL: {float(sl):.2f}"
                        if sl_dist is not None:
                            sl_info += f" (dist: {sl_dist:.2f})"
                        if dollar_risk is not None:
                            sl_info += f" | Risk: ${dollar_risk:.2f}"
                    vol = signal.get('volume')
                    lot_str = f" | Lot: {vol:.2f}" if vol is not None else ""
                    print(f"\n[SIGNAL] {signal['type']} {signal['symbol']} @ {signal['price']:.5f}{lot_str}{sl_info}")
                    reason = signal.get('reason', '')
                    if reason:
                        print(f"[REASON] {reason}")
                    if sl is not None:
                        print(f"[SL] Stop loss: {float(sl):.5f} | Risk in dollars: ${dollar_risk:.2f}" if dollar_risk is not None else f"[SL] Stop loss: {float(sl):.5f} | Risk in dollars: n/a")
                    if config.VOICE_ALERTS and config.VOICE_ALERT_ON_SIGNAL:
                        reason = signal.get('reason', 'Strategy signal')
                        speak(f"Trade found. {signal['type']} {signal['symbol']}. {reason}. Checking approval.")
                    # Skip Telegram + execution if market closed (avoid retcode 10018, don't alert on impossible trades)
                    if getattr(config, 'SKIP_WHEN_MARKET_CLOSED', True) and self.mt5.connected:
                        sym = signal.get('symbol', '')
                        if sym and not self.mt5.is_market_open(sym):
                            print(f"[SKIP] Market closed for {sym}. Not sending to Telegram or executing.")
                            continue
                    result, exec_err = self.execute_signal(signal)
                    if result:
                        self._record_setup_trade(signal)
                        last_signal_time = datetime.now()
                        if getattr(config, 'TELEGRAM_ENABLED', False):
                            send_setup_notification(signal, self.strategy_name)
                        exec_reason = signal.get('reason', '')
                        vol = result.get('volume')
                        risk_str = ""
                        if sl is not None and vol is not None:
                            dr = self.mt5.calc_dollar_risk(signal['symbol'], signal['price'], sl, vol)
                            if dr is not None:
                                risk_str = f" | Risk: ${dr:.2f}"
                        print(f"[EXECUTE] Order placed: {result.get('type')} {vol} {result.get('symbol')} @ {result.get('price')}{risk_str}")
                        if exec_reason:
                            print(f"[EXECUTE] Reason: {exec_reason}")
                    else:
                        if exec_err:
                            self._last_run_errors.append(exec_err)
                        print(f"[EXECUTE] Order failed — check [MT5] or [SAFETY] message above for reason.")
                # Always show status (Open Positions + Total Trades + Lot Size + Risk) every loop
                self.show_status()
                # Compact status line: Strategy + Open Positions + Total Trades + Lot Size + Risk
                if self.paper_mode:
                    positions = self.paper.get_positions()
                    n_pos = len(positions)
                    n_trades = self.paper.get_stats().get('total_trades', 0)
                else:
                    positions = self.mt5.get_positions()
                    n_pos = len(positions)
                    n_trades = len(self.trades_today)
                total_lot = sum(float(p.get('volume', 0)) for p in positions)
                total_risk = 0.0
                if self.mt5.connected:
                    for p in positions:
                        sym = p.get('symbol')
                        entry = p.get('price_open')
                        sl = p.get('sl')
                        vol = p.get('volume')
                        if sym and entry is not None and sl is not None and vol is not None:
                            dr = self.mt5.calc_dollar_risk(sym, entry, sl, vol)
                            if dr is not None:
                                total_risk += dr
                lot_str = f"{total_lot:.2f}" if total_lot > 0 else "0"
                risk_str = f"${total_risk:.2f}" if total_risk > 0 else "$0"
                print(f"\n[{self.strategy_name}] Open Positions: {n_pos} | Total Trades: {n_trades} | Lot Size: {lot_str} | Risk: {risk_str}")
                if self.strategy_name == 'test-sl':
                    print("[test-sl] Stopping in 3 seconds...")
                    time.sleep(3)
                    self.running = False
                    break
                print(f"Next check in {config.LIVE_CHECK_INTERVAL}s...")
                time.sleep(config.LIVE_CHECK_INTERVAL)
        except KeyboardInterrupt:
            print("\n\nStopping trading engine...")
            self.running = False
        finally:
            if config.MANUAL_APPROVAL and self.trades_today:
                self.approver.show_daily_summary(self.trades_today)
            self.show_status()
            if self.paper_mode:
                self.paper.save_session()
            print("\nTrading engine stopped.")
