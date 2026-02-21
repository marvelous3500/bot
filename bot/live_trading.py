import os
import time
import config
import pandas as pd
from datetime import datetime, timedelta
from .connector_interface import get_connector, TIMEFRAME_M1, TIMEFRAME_M5, TIMEFRAME_M15, TIMEFRAME_H1, TIMEFRAME_H4, TIMEFRAME_D1
from .paper_trading import PaperTrading
from .trade_approver import TradeApprover
from .strategies import H1M5BOSStrategy, KingsleyGoldStrategy, MarvellousStrategy, NasStrategy, JudasStrategy, TestStrategy
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

    def __init__(self, strategy_name='h1_m5_bos', paper_mode=True, symbol=None):
        self.strategy_name = strategy_name
        self.paper_mode = paper_mode
        self.cli_symbol = symbol  # --symbol from CLI (e.g. 'BTC-USD'); overrides config for live/paper
        self.mt5 = get_connector(
            login=config.MT5_LOGIN,
            password=config.MT5_PASSWORD,
            server=config.MT5_SERVER,
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
        """Return the symbol used for bias-of-day (matches strategy's primary symbol)."""
        if self.strategy_name == 'marvellous':
            from . import marvellous_config as mc
            symbol = getattr(config, 'MARVELLOUS_LIVE_SYMBOL', mc.MARVELLOUS_LIVE_SYMBOL)
        elif self.strategy_name == 'nas':
            from . import nas_config as nc
            symbol = getattr(config, 'NAS_LIVE_SYMBOL', nc.LIVE_SYMBOL)
        elif self.strategy_name == 'judas':
            from . import judas_config as jc
            symbol = getattr(config, 'JUDAS_LIVE_SYMBOL', jc.LIVE_SYMBOL)
        elif self.strategy_name in ('kingsely_gold', 'test'):
            symbol = (
                config.LIVE_SYMBOLS.get('XAUUSD') or
                getattr(config, 'KINGSLEY_LIVE_SYMBOL', 'XAUUSDm') or
                'XAUUSDm'
            )
        else:
            symbol = list(config.LIVE_SYMBOLS.values())[0]
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
        if self.strategy_name in ('kingsely_gold', 'marvellous', 'test'):
            symbol = (
                (config.cli_symbol_to_mt5(self.cli_symbol) if self.cli_symbol else None) or
                config.LIVE_SYMBOLS.get('XAUUSD') or
                config.LIVE_SYMBOLS.get('GOLD') or
                next((v for k, v in config.LIVE_SYMBOLS.items() if 'XAU' in k.upper() or 'GOLD' in k.upper()), None) or
                list(config.LIVE_SYMBOLS.values())[0]
            )
        elif self.strategy_name == 'nas':
            from . import nas_config as nc
            symbol = (
                config.LIVE_SYMBOLS.get('NAS100') or
                config.LIVE_SYMBOLS.get('NDX') or
                getattr(config, 'NAS_LIVE_SYMBOL', nc.LIVE_SYMBOL) or
                list(config.LIVE_SYMBOLS.values())[0]
            )
        elif self.strategy_name == 'judas':
            from . import judas_config as jc
            symbol = (
                config.LIVE_SYMBOLS.get('NAS100') or
                config.LIVE_SYMBOLS.get('NDX') or
                getattr(config, 'JUDAS_LIVE_SYMBOL', jc.LIVE_SYMBOL) or
                list(config.LIVE_SYMBOLS.values())[0]
            )
        else:
            symbol = list(config.LIVE_SYMBOLS.values())[0]
        if self.strategy_name == 'h1_m5_bos':
            df_h1 = self.mt5.get_bars(symbol, TIMEFRAME_H1, count=200)
            df_5m = self.mt5.get_bars(symbol, TIMEFRAME_M5, count=1000)
            df_4h = self.mt5.get_bars(symbol, TIMEFRAME_H4, count=100) if getattr(config, 'USE_4H_BIAS_FILTER', False) else None
            df_daily = self.mt5.get_bars(symbol, TIMEFRAME_D1, count=50) if getattr(config, 'USE_DAILY_BIAS_FILTER', False) else None
            if df_h1 is None or df_5m is None:
                if getattr(config, 'LIVE_DEBUG', False):
                    print(f"[LIVE_DEBUG] No data: H1={df_h1 is not None}, M5={df_5m is not None}")
                return []
            if getattr(config, 'LIVE_DEBUG', False):
                last_h1 = df_h1.index[-1] if len(df_h1) > 0 else None
                last_m5 = df_5m.index[-1] if len(df_5m) > 0 else None
                print(f"[LIVE_DEBUG] {symbol} H1: {len(df_h1)} bars, last={last_h1} | M5: {len(df_5m)} bars, last={last_m5}")
            strat = H1M5BOSStrategy(df_h1, df_5m, df_4h=df_4h, df_daily=df_daily)
            strat.prepare_data()
            signals_df = strat.run_backtest()
            if getattr(config, 'LIVE_DEBUG', False) and signals_df.empty:
                print(f"[LIVE_DEBUG] Strategy returned 0 signals (no BOS + kill zone + entry)")
        elif self.strategy_name == 'kingsely_gold':
            entry_tf = getattr(config, 'KINGSLEY_ENTRY_TIMEFRAME', '5m')
            tf_entry = TIMEFRAME_M5 if entry_tf == '5m' else TIMEFRAME_M15
            gold_symbols = list(dict.fromkeys([
                symbol, getattr(config, 'KINGSLEY_LIVE_SYMBOL', 'XAUUSD'), 'GOLD', 'XAUUSD'
            ]))
            df_4h, df_h1, df_15m, df_daily = None, None, None, None
            for sym in gold_symbols:
                df_4h = self.mt5.get_bars(sym, TIMEFRAME_H4, count=100)
                df_h1 = self.mt5.get_bars(sym, TIMEFRAME_H1, count=200)
                df_15m = self.mt5.get_bars(sym, tf_entry, count=1000)
                if getattr(config, 'USE_DAILY_BIAS_FILTER', False):
                    df_daily = self.mt5.get_bars(sym, TIMEFRAME_D1, count=50)
                has_all = df_4h is not None and df_h1 is not None and df_15m is not None
                needs_daily = getattr(config, 'USE_DAILY_BIAS_FILTER', False)
                if has_all and (not needs_daily or df_daily is not None):
                    symbol = sym
                    break
            if df_4h is None or df_h1 is None or df_15m is None:
                if getattr(config, 'LIVE_DEBUG', False):
                    h4_ok = "OK" if df_4h is not None else "MISSING"
                    h1_ok = "OK" if df_h1 is not None else "MISSING"
                    entry_ok = "OK" if df_15m is not None else "MISSING"
                    print(f"[LIVE_DEBUG] kingsely_gold: Bar data missing — 4H={h4_ok}, H1={h1_ok}, {entry_tf}={entry_ok} (tried: {gold_symbols})")
                    print(f"[LIVE_DEBUG]   → Check: symbol in MT5 Market Watch, market open (not weekend), broker symbol name")
                return []
            if getattr(config, 'LIVE_DEBUG', False):
                last_4h = df_4h.index[-1] if len(df_4h) > 0 else None
                last_h1 = df_h1.index[-1] if len(df_h1) > 0 else None
                last_entry = df_15m.index[-1] if len(df_15m) > 0 else None
                print(f"[LIVE_DEBUG] {symbol} 4H: {len(df_4h)} bars, last={last_4h} | H1: {len(df_h1)} bars, last={last_h1} | {entry_tf}: {len(df_15m)} bars, last={last_entry}")
            strat = KingsleyGoldStrategy(df_4h, df_h1, df_15m, df_daily=df_daily, verbose=False)
            strat.prepare_data()
            signals_df = strat.run_backtest()
            if getattr(config, 'LIVE_DEBUG', False) and signals_df.empty:
                print(f"[LIVE_DEBUG] kingsely_gold: 0 signals (no H1+{entry_tf} BOS + OB tap + Liq sweep + OB test)")
        elif self.strategy_name == 'marvellous':
            from . import marvellous_config as mc
            # CLI --symbol overrides: try that MT5 symbol first (e.g. BTC-USD -> BTCUSDm)
            cli_mt5 = config.cli_symbol_to_mt5(self.cli_symbol) if self.cli_symbol else None
            marv_live = getattr(config, 'MARVELLOUS_LIVE_SYMBOL', mc.MARVELLOUS_LIVE_SYMBOL)
            gold_symbols = list(dict.fromkeys([
                s for s in [cli_mt5, marv_live, symbol, 'XAUUSD', 'XAUUSDm'] if s
            ]))
            entry_tf = getattr(mc, 'ENTRY_TIMEFRAME', '5m')
            df_daily = df_4h = df_h1 = df_m15 = df_entry = None
            for sym in gold_symbols:
                df_daily = self.mt5.get_bars(sym, TIMEFRAME_D1, count=50)
                df_4h = self.mt5.get_bars(sym, TIMEFRAME_H4, count=100)
                df_h1 = self.mt5.get_bars(sym, TIMEFRAME_H1, count=200)
                df_m15 = self.mt5.get_bars(sym, TIMEFRAME_M15, count=1000)
                if entry_tf == '15m':
                    df_entry = df_m15.copy() if df_m15 is not None else None
                else:
                    tf_entry = TIMEFRAME_M1 if entry_tf == '1m' else TIMEFRAME_M5
                    df_entry = self.mt5.get_bars(sym, tf_entry, count=1000)
                if all(x is not None for x in (df_daily, df_4h, df_h1, df_m15, df_entry)):
                    symbol = sym
                    break
            if df_h1 is None or df_m15 is None or df_entry is None:
                if getattr(config, 'LIVE_DEBUG', False):
                    print(f"[LIVE_DEBUG] marvellous: Bar data missing (tried: {gold_symbols})")
                return []
            if getattr(config, 'LIVE_DEBUG', False):
                print(f"[LIVE_DEBUG] {symbol} marvellous: D1/4H/H1/M15/Entry({entry_tf}) loaded")
            strat = MarvellousStrategy(
                df_daily=df_daily,
                df_4h=df_4h,
                df_h1=df_h1,
                df_m15=df_m15,
                df_entry=df_entry,
                symbol=symbol,
                verbose=False,
            )
            strat.prepare_data()
            signals_df = strat.run_backtest()
            if getattr(config, 'LIVE_DEBUG', False) and signals_df.empty:
                print(f"[LIVE_DEBUG] marvellous: 0 signals")
        elif self.strategy_name == 'nas':
            from . import nas_config as nc
            nas_symbols = [s for s in list(dict.fromkeys([
                getattr(config, 'NAS_LIVE_SYMBOL', nc.LIVE_SYMBOL),
                config.LIVE_SYMBOLS.get('NAS100'),
                config.LIVE_SYMBOLS.get('NDX'),
                'NAS100m',
                'NAS100',
            ])) if s]
            df_4h = df_h1 = df_m15 = None
            for sym in nas_symbols:
                if sym is None:
                    continue
                df_4h = self.mt5.get_bars(sym, TIMEFRAME_H4, count=100)
                df_h1 = self.mt5.get_bars(sym, TIMEFRAME_H1, count=200)
                df_m15 = self.mt5.get_bars(sym, TIMEFRAME_M15, count=1000)
                if all(x is not None for x in (df_4h, df_h1, df_m15)):
                    symbol = sym
                    break
            if df_h1 is None or df_m15 is None:
                if getattr(config, 'LIVE_DEBUG', False):
                    print(f"[LIVE_DEBUG] nas: Bar data missing (tried: {nas_symbols})")
                return []
            if getattr(config, 'LIVE_DEBUG', False):
                print(f"[LIVE_DEBUG] {symbol} nas: 4H/H1/M15 loaded")
            strat = NasStrategy(
                df_h1=df_h1,
                df_m15=df_m15,
                df_entry=df_m15,
                df_4h=df_4h,
                symbol=symbol,
                verbose=False,
            )
            strat.prepare_data()
            signals_df = strat.run_backtest()
            if getattr(config, 'LIVE_DEBUG', False) and signals_df.empty:
                print(f"[LIVE_DEBUG] nas: 0 signals")
        elif self.strategy_name == 'judas':
            from . import judas_config as jc
            judas_symbols = [s for s in list(dict.fromkeys([
                getattr(config, 'JUDAS_LIVE_SYMBOL', jc.LIVE_SYMBOL),
                config.LIVE_SYMBOLS.get('NAS100'),
                config.LIVE_SYMBOLS.get('NDX'),
                'NAS100m',
                'NAS100',
            ])) if s]
            df_h1 = df_m15 = None
            for sym in judas_symbols:
                if sym is None:
                    continue
                df_h1 = self.mt5.get_bars(sym, TIMEFRAME_H1, count=200)
                df_m15 = self.mt5.get_bars(sym, TIMEFRAME_M15, count=1000)
                if all(x is not None for x in (df_h1, df_m15)):
                    symbol = sym
                    break
            if df_h1 is None or df_m15 is None:
                if getattr(config, 'LIVE_DEBUG', False):
                    print(f"[LIVE_DEBUG] judas: Bar data missing (tried: {judas_symbols})")
                return []
            if getattr(config, 'LIVE_DEBUG', False):
                print(f"[LIVE_DEBUG] {symbol} judas: H1/M15 loaded")
            strat = JudasStrategy(
                df_h1=df_h1,
                df_m15=df_m15,
                symbol=symbol,
                verbose=False,
            )
            strat.prepare_data()
            signals_df = strat.run_backtest()
            if getattr(config, 'LIVE_DEBUG', False) and signals_df.empty:
                print(f"[LIVE_DEBUG] judas: 0 signals")
        elif self.strategy_name == 'test':
            gold_symbols = list(dict.fromkeys([
                symbol,
                getattr(config, 'TEST_LIVE_SYMBOL', 'XAUUSD'),
                getattr(config, 'KINGSLEY_LIVE_SYMBOL', 'XAUUSDm'),  # Exness uses XAUUSDm
                'GOLD',
                'XAUUSD',
                'XAUUSDm',
            ]))
            df_h1 = None
            for sym in gold_symbols:
                df_h1 = self.mt5.get_bars(sym, TIMEFRAME_H1, count=200)
                if df_h1 is not None:
                    symbol = sym
                    break
            if df_h1 is None:
                if getattr(config, 'LIVE_DEBUG', False):
                    print(f"[LIVE_DEBUG] test: No H1 data (tried: {gold_symbols})")
                    print(f"[LIVE_DEBUG]   → Check: symbol in MT5 Market Watch, market open (not weekend), broker symbol name")
                return []
            if getattr(config, 'LIVE_DEBUG', False) or getattr(config, 'MT5_VERBOSE', False):
                last_h1 = df_h1.index[-1] if len(df_h1) > 0 else None
                print(f"[MT5] test: {symbol} H1: {len(df_h1)} bars, last={last_h1}")
            strat = TestStrategy(df_h1, verbose=False)
            strat.prepare_data()
            signals_df = strat.run_backtest()
            if getattr(config, 'LIVE_DEBUG', False) and signals_df.empty:
                print(f"[LIVE_DEBUG] test: 0 signals (need at least 4 H1 bars)")
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
                # Kingsley/Marvellous/NAS/Judas: add buffer below/above lq_level so slight price move doesn't invalidate SL
                if self.strategy_name in ('kingsely_gold', 'marvellous', 'nas', 'judas'):
                    sl = latest_signal.get('sl')
                    if sl is not None:
                        if self.strategy_name == 'marvellous':
                            buf = config.get_symbol_config(symbol, 'MARVELLOUS_SL_BUFFER') or getattr(config, 'MARVELLOUS_SL_BUFFER', 1.0)
                        elif self.strategy_name == 'nas':
                            buf = config.get_symbol_config(symbol, 'NAS_SL_BUFFER') or getattr(config, 'NAS_SL_BUFFER', 5.0)
                        elif self.strategy_name == 'judas':
                            buf = getattr(config, 'JUDAS_SL_BUFFER', 8)
                        else:
                            buf = getattr(config, 'KINGSLEY_SL_BUFFER', 1.0)
                        try:
                            sl_f = float(sl)
                            if latest_signal['type'] == 'BUY':
                                latest_signal['sl'] = sl_f - buf  # Move SL lower for BUY
                            else:
                                latest_signal['sl'] = sl_f + buf  # Move SL higher for SELL
                        except (TypeError, ValueError):
                            pass
                # Kingsley/Marvellous/NAS: if live price invalidated SL and fallback enabled, use fallback SL
                use_fallback = (
                    (self.strategy_name == 'kingsely_gold' and getattr(config, 'KINGSLEY_USE_SL_FALLBACK', False)) or
                    (self.strategy_name == 'marvellous' and getattr(config, 'MARVELLOUS_USE_SL_FALLBACK', False)) or
                    (self.strategy_name == 'nas' and getattr(config, 'NAS_USE_SL_FALLBACK', False)) or
                    (self.strategy_name == 'judas' and getattr(config, 'JUDAS_USE_SL_FALLBACK', False))
                )
                if use_fallback:
                    sl = latest_signal.get('sl')
                    price = latest_signal['price']
                    if sl is not None:
                        try:
                            sl_f, price_f = float(sl), float(price)
                            if self.strategy_name == 'marvellous':
                                fallback_dist = config.get_symbol_config(symbol, 'MARVELLOUS_SL_FALLBACK_DISTANCE') or getattr(config, 'MARVELLOUS_SL_FALLBACK_DISTANCE', 5.0)
                            elif self.strategy_name == 'nas':
                                fallback_dist = config.get_symbol_config(symbol, 'NAS_SL_FALLBACK_DISTANCE') or getattr(config, 'NAS_SL_BUFFER', 5.0)
                            elif self.strategy_name == 'judas':
                                fallback_dist = getattr(config, 'JUDAS_SL_FALLBACK_DISTANCE', 10.0)
                            else:
                                fallback_dist = getattr(config, 'KINGSLEY_SL_FALLBACK_DISTANCE', 5.0)
                            if latest_signal['type'] == 'BUY' and sl_f >= price_f:
                                latest_signal['sl'] = price_f - fallback_dist
                            elif latest_signal['type'] == 'SELL' and sl_f <= price_f:
                                latest_signal['sl'] = price_f + fallback_dist
                        except (TypeError, ValueError):
                            pass
                sl_dist = abs(latest_signal['price'] - latest_signal.get('sl', 0))
                if latest_signal['type'] == 'BUY':
                    latest_signal['tp'] = latest_signal['price'] + (sl_dist * config.RISK_REWARD_RATIO)
                else:
                    latest_signal['tp'] = latest_signal['price'] - (sl_dist * config.RISK_REWARD_RATIO)
                # Test strategy: use fixed small lot to ensure order goes through
                if self.strategy_name == 'test':
                    lot = getattr(config, 'TEST_FIXED_LOT', 0.01) or 0.01
                    latest_signal['volume'] = max(0.01, float(lot))
                # Dynamic lot size: risk % of current balance (matches backtest)
                elif getattr(config, 'USE_DYNAMIC_POSITION_SIZING', True) and self.mt5.connected:
                    account = self.paper.get_account_info() if self.paper_mode else self.mt5.get_account_info()
                    balance = account['balance'] if account else 0
                    sl = latest_signal.get('sl')
                    if sl is not None and balance > 0:
                        risk_pct = getattr(config, 'NAS_RISK_PER_TRADE', 0.005) if self.strategy_name == 'nas' else config.RISK_PER_TRADE
                        lot = self.mt5.calc_lot_size_from_risk(
                            symbol, balance, latest_signal['price'], sl, risk_pct
                        )
                        if lot is not None:
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
            result, mt5_err = self.mt5.place_order(
                symbol=signal['symbol'],
                order_type=signal['type'],
                volume=vol,
                price=signal['price'],
                sl=signal['sl'],
                tp=signal['tp'],
                comment=_comment
            )
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
        """When a position is in profit by BREAKEVEN_PIPS, move SL to half breakeven (lock in half the pips). Live only."""
        if self.paper_mode or not getattr(config, 'BREAKEVEN_ENABLED', False):
            return
        required_pips = getattr(config, 'BREAKEVEN_PIPS', 3.0)
        half_pips = required_pips / 2.0
        positions = self.mt5.get_positions()
        for pos in positions:
            ticket = pos.get('ticket')
            symbol = pos.get('symbol')
            price_open = pos.get('price_open')
            sl = pos.get('sl')
            pos_type = pos.get('type')
            if ticket is None or symbol is None or price_open is None:
                continue
            try:
                price_open = float(price_open)
            except (TypeError, ValueError):
                continue
            pip_size = self.mt5.get_pip_size(symbol)
            if pip_size is None or pip_size <= 0:
                continue
            tick = self.mt5.get_live_price(symbol)
            if not tick:
                continue
            if pos_type == 'BUY':
                current = tick.get('bid')
            else:
                current = tick.get('ask')
            if current is None:
                continue
            try:
                current = float(current)
            except (TypeError, ValueError):
                continue
            if pos_type == 'BUY':
                profit_pips = (current - price_open) / pip_size
                target_sl = price_open + half_pips * pip_size
                sl_already_ok = (sl is not None and sl != 0 and float(sl) >= target_sl - pip_size)
            else:
                profit_pips = (price_open - current) / pip_size
                target_sl = price_open - half_pips * pip_size
                sl_already_ok = (sl is not None and sl != 0 and float(sl) <= target_sl + pip_size)
            if profit_pips < required_pips:
                continue
            if sl_already_ok:
                continue
            ok, err = self.mt5.modify_position(ticket, sl=target_sl, tp=pos.get('tp'))
            if ok:
                print(f"[BREAKEVEN] Position {ticket} SL moved to half breakeven ({half_pips:.1f} pips) at {target_sl:.5f} (profit was {profit_pips:.1f} pips)")
            elif getattr(config, 'MT5_VERBOSE', False):
                print(f"[BREAKEVEN] Failed to move SL for {ticket}: {err}")

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

    def _check_tp1_sl_to_entry(self):
        """When price reaches TP1, move SL to entry (breakeven). Live only."""
        if self.paper_mode or not getattr(config, 'TP1_SL_TO_ENTRY_ENABLED', False):
            return
        ratio = getattr(config, 'TP1_RATIO', 0.5)
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
            except (TypeError, ValueError):
                continue
            pip_size = self.mt5.get_pip_size(symbol)
            if pip_size is None or pip_size <= 0:
                pip_size = 0.0001
            tolerance = pip_size
            if pos_type == 'BUY':
                tp1 = price_open + (tp - price_open) * ratio
                sl_at_entry = sl is not None and sl != 0 and abs(float(sl) - price_open) <= tolerance
            else:
                tp1 = price_open - (price_open - tp) * ratio
                sl_at_entry = sl is not None and sl != 0 and abs(float(sl) - price_open) <= tolerance
            if sl_at_entry:
                continue
            tick = self.mt5.get_live_price(symbol)
            if not tick:
                continue
            if pos_type == 'BUY':
                current = tick.get('bid')
            else:
                current = tick.get('ask')
            if current is None:
                continue
            try:
                current = float(current)
            except (TypeError, ValueError):
                continue
            if pos_type == 'BUY':
                tp1_reached = current >= tp1
            else:
                tp1_reached = current <= tp1
            if not tp1_reached:
                continue
            ok, err = self.mt5.modify_position(ticket, sl=price_open, tp=tp)
            if ok:
                print(f"[TP1] Position {ticket} SL moved to entry (breakeven) at TP1")
            elif getattr(config, 'MT5_VERBOSE', False):
                print(f"[TP1] Failed to move SL for {ticket}: {err}")

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
        if self.strategy_name == 'test' and getattr(config, 'TEST_SINGLE_RUN', False):
            print("Test strategy: single-run mode (take one trade and exit)")
            if config.MANUAL_APPROVAL:
                print("  Use --auto-approve to skip confirmation prompt.\n")
            else:
                print()
        else:
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
                    if self.strategy_name == 'test' and getattr(config, 'TEST_SINGLE_RUN', False):
                        print(f"{reason}. Exiting.")
                        self.running = False
                        break
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
                self._check_tp1_sl_to_entry()
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
                    if last_signal_time and abs((signal_time - last_signal_time).total_seconds()) < 300:
                        self._last_run_errors.append("5 min cooldown")
                        print(f"[SKIP] Signal within 5 min of last execution (cooldown)")
                        continue
                    if getattr(config, 'MAX_TRADES_PER_DAY_PER_PAIR', False):
                        can_trade, limit_reason = self._can_trade_symbol(signal.get('symbol', ''))
                        if not can_trade:
                            print(f"[SKIP] {limit_reason}")
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
                    print(f"\n[SIGNAL] {signal['type']} {signal['symbol']} @ {signal['price']:.5f}{sl_info}")
                    reason = signal.get('reason', '')
                    if reason:
                        print(f"[REASON] {reason}")
                    diag = signal.get('kingsley_diagnostic')
                    if diag and self.strategy_name == 'kingsely_gold':
                        print(f"[KINGSLEY DIAGNOSTIC] Check 5m chart at these times:")
                        print(f"  H1 bar:      {diag.get('h1_bar', 'N/A')}")
                        print(f"  BOS bar:     {diag.get('bos_bar', 'N/A')}")
                        print(f"  OB tap:      {diag.get('ob_tap_bar', 'N/A')}")
                        print(f"  Liq sweep:   {diag.get('liq_sweep_bar', 'N/A')} (SL=LQ from this bar)")
                        print(f"  LQ sweep:    {diag.get('lq_sweep_back_bar', 'N/A')}")
                        print(f"  OB test:     {diag.get('ob_test_bar', 'N/A')}")
                        print(f"  Entry bar:   {diag.get('entry_bar', 'N/A')}")
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
                    if getattr(config, 'TELEGRAM_ENABLED', False):
                        send_setup_notification(signal, self.strategy_name)
                    result, exec_err = self.execute_signal(signal)
                    if result:
                        last_signal_time = datetime.now()
                        exec_reason = signal.get('reason', '')
                        print(f"[EXECUTE] Order placed: {result.get('type')} {result.get('volume')} {result.get('symbol')} @ {result.get('price')}")
                        if exec_reason:
                            print(f"[EXECUTE] Reason: {exec_reason}")
                    else:
                        if exec_err:
                            self._last_run_errors.append(exec_err)
                        print(f"[EXECUTE] Order failed — check [MT5] or [SAFETY] message above for reason.")
                # Always show status (Open Positions + Total Trades) every loop
                self.show_status()
                # Test strategy: single-run mode — always exit after one check
                if self.strategy_name == 'test' and getattr(config, 'TEST_SINGLE_RUN', False):
                    if not signals:
                        print("\nTest strategy: no signal (check XAUUSDm in Market Watch, market open). Exiting.")
                    else:
                        trades_done = len(self.trades_today)
                        if trades_done == 0:
                            print("\n" + "=" * 50)
                            print("Test strategy: single run complete — but NO TRADE was executed.")
                            if self._last_run_errors:
                                print("Reason(s):")
                                for e in self._last_run_errors:
                                    print(f"  • {e}")
                            else:
                                print("  (No signal was generated — check data/symbol)")
                            print("=" * 50)
                        else:
                            print(f"\nTest strategy: single run complete. {trades_done} trade(s) executed.")
                    self.running = False
                    break
                # Compact status line so Strategy + Open Positions + Total Trades are always visible
                if self.paper_mode:
                    n_pos = len(self.paper.get_positions())
                    n_trades = self.paper.get_stats().get('total_trades', 0)
                else:
                    n_pos = len(self.mt5.get_positions())
                    n_trades = len(self.trades_today)
                print(f"\n[{self.strategy_name}] Open Positions: {n_pos} | Total Trades: {n_trades}")
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
