import time
import config
import pandas as pd
from datetime import datetime, timedelta
from .connector_interface import get_connector, TIMEFRAME_M5, TIMEFRAME_M15, TIMEFRAME_H1, TIMEFRAME_H4, TIMEFRAME_D1
from .paper_trading import PaperTrading
from .trade_approver import TradeApprover
from .strategies import ICTStrategy, LiquiditySweepStrategy, H1M5BOSStrategy, ConfluenceStrategy, KingsleyGoldStrategy, TestStrategy
from .backtest import prepare_pdh_pdl
from ai import get_signal_confidence, explain_trade, speak

class LiveTradingEngine:
    """Main live trading engine that runs strategies continuously."""

    def __init__(self, strategy_name='pdh_pdl', paper_mode=True):
        self.strategy_name = strategy_name
        self.paper_mode = paper_mode
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
        today = datetime.now().date()
        trades_count = len([t for t in self.trades_today if t['time'].date() == today])
        if trades_count >= config.MAX_TRADES_PER_DAY:
            print(f"[SAFETY] Daily trade limit reached ({config.MAX_TRADES_PER_DAY})")
            return False
        return True

    def run_strategy(self):
        if self.strategy_name in ('kingsely_gold', 'test'):
            symbol = (
                config.LIVE_SYMBOLS.get('XAUUSD') or
                config.LIVE_SYMBOLS.get('GOLD') or
                next((v for k, v in config.LIVE_SYMBOLS.items() if 'XAU' in k.upper() or 'GOLD' in k.upper()), None) or
                list(config.LIVE_SYMBOLS.values())[0]
            )
        else:
            symbol = list(config.LIVE_SYMBOLS.values())[0]
        if self.strategy_name == 'pdh_pdl':
            df_daily = self.mt5.get_bars(symbol, TIMEFRAME_D1, count=10)
            df_5m = self.mt5.get_bars(symbol, TIMEFRAME_M5, count=500)
            if df_daily is None or df_5m is None:
                return []
            strat = ICTStrategy(df_5m)
            df_processed = strat.prepare_data()
            pdh_series, pdl_series = prepare_pdh_pdl(df_processed, df_daily)
            signals_df = strat.run_backtest(pdh_series, pdl_series)
        elif self.strategy_name == 'liquidity_sweep':
            df_4h = self.mt5.get_bars(symbol, TIMEFRAME_H4, count=100)
            df_1h = self.mt5.get_bars(symbol, TIMEFRAME_H1, count=200)
            df_15m = self.mt5.get_bars(symbol, TIMEFRAME_M15, count=500)
            if df_4h is None or df_1h is None or df_15m is None:
                return []
            strat = LiquiditySweepStrategy(df_4h, df_1h, df_15m)
            strat.prepare_data()
            signals_df = strat.run_backtest()
        elif self.strategy_name == 'h1_m5_bos':
            df_h1 = self.mt5.get_bars(symbol, TIMEFRAME_H1, count=200)
            df_5m = self.mt5.get_bars(symbol, TIMEFRAME_M5, count=1000)
            if df_h1 is None or df_5m is None:
                if getattr(config, 'LIVE_DEBUG', False):
                    print(f"[LIVE_DEBUG] No data: H1={df_h1 is not None}, M5={df_5m is not None}")
                return []
            if getattr(config, 'LIVE_DEBUG', False):
                last_h1 = df_h1.index[-1] if len(df_h1) > 0 else None
                last_m5 = df_5m.index[-1] if len(df_5m) > 0 else None
                print(f"[LIVE_DEBUG] {symbol} H1: {len(df_h1)} bars, last={last_h1} | M5: {len(df_5m)} bars, last={last_m5}")
            strat = H1M5BOSStrategy(df_h1, df_5m)
            strat.prepare_data()
            signals_df = strat.run_backtest()
            if getattr(config, 'LIVE_DEBUG', False) and signals_df.empty:
                print(f"[LIVE_DEBUG] Strategy returned 0 signals (no BOS + kill zone + entry)")
        elif self.strategy_name == 'confluence':
            df_4h = self.mt5.get_bars(symbol, TIMEFRAME_H4, count=100)
            df_15m = self.mt5.get_bars(symbol, TIMEFRAME_M15, count=500)
            if df_4h is None or df_15m is None:
                return []
            strat = ConfluenceStrategy(df_4h, df_15m)
            strat.prepare_data()
            signals_df = strat.run_backtest()
        elif self.strategy_name == 'kingsely_gold':
            gold_symbols = list(dict.fromkeys([
                symbol, getattr(config, 'KINGSLEY_LIVE_SYMBOL', 'XAUUSD'), 'GOLD', 'XAUUSD'
            ]))
            df_h1, df_15m = None, None
            for sym in gold_symbols:
                df_h1 = self.mt5.get_bars(sym, TIMEFRAME_H1, count=200)
                df_15m = self.mt5.get_bars(sym, TIMEFRAME_M15, count=1000)
                if df_h1 is not None and df_15m is not None:
                    symbol = sym
                    break
            if df_h1 is None or df_15m is None:
                if getattr(config, 'LIVE_DEBUG', False):
                    h1_ok = "OK" if df_h1 is not None else "MISSING"
                    m15_ok = "OK" if df_15m is not None else "MISSING"
                    print(f"[LIVE_DEBUG] kingsely_gold: Bar data missing — H1={h1_ok}, 15m={m15_ok} (tried: {gold_symbols})")
                    print(f"[LIVE_DEBUG]   → Check: symbol in MT5 Market Watch, market open (not weekend), broker symbol name")
                return []
            if getattr(config, 'LIVE_DEBUG', False):
                last_h1 = df_h1.index[-1] if len(df_h1) > 0 else None
                last_15m = df_15m.index[-1] if len(df_15m) > 0 else None
                print(f"[LIVE_DEBUG] {symbol} H1: {len(df_h1)} bars, last={last_h1} | 15m: {len(df_15m)} bars, last={last_15m}")
            strat = KingsleyGoldStrategy(df_h1, df_15m, verbose=False)
            strat.prepare_data()
            signals_df = strat.run_backtest()
            if getattr(config, 'LIVE_DEBUG', False) and signals_df.empty:
                print(f"[LIVE_DEBUG] kingsely_gold: 0 signals (no H1+15m BOS + OB tap + Liq sweep + OB test)")
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
                # Kingsley Gold: add buffer below/above lq_level so slight price move doesn't invalidate SL
                if self.strategy_name == 'kingsely_gold':
                    sl = latest_signal.get('sl')
                    if sl is not None:
                        buf = getattr(config, 'KINGSLEY_SL_BUFFER', 1.0)
                        try:
                            sl_f = float(sl)
                            if latest_signal['type'] == 'BUY':
                                latest_signal['sl'] = sl_f - buf  # Move SL lower for BUY
                            else:
                                latest_signal['sl'] = sl_f + buf  # Move SL higher for SELL
                        except (TypeError, ValueError):
                            pass
                # Kingsley Gold: if live price invalidated SL and fallback enabled, use fallback SL
                if self.strategy_name == 'kingsely_gold' and getattr(config, 'KINGSLEY_USE_SL_FALLBACK', False):
                    sl = latest_signal.get('sl')
                    price = latest_signal['price']
                    if sl is not None:
                        try:
                            sl_f, price_f = float(sl), float(price)
                            fallback_dist = getattr(config, 'KINGSLEY_SL_FALLBACK_DISTANCE', 5.0)
                            if latest_signal['type'] == 'BUY' and sl_f >= price_f:
                                latest_signal['sl'] = price_f - fallback_dist
                            elif latest_signal['type'] == 'SELL' and sl_f <= price_f:
                                latest_signal['sl'] = price_f + fallback_dist
                        except (TypeError, ValueError):
                            pass
                # Confluence: set SL from pips before lot calc (other strategies have sl from signal)
                if self.strategy_name == 'confluence':
                    sl_pips = getattr(config, 'CONFLUENCE_SL_PIPS', 50)
                    info = self.mt5.get_symbol_info(symbol)
                    pip_size = (info['point'] * 10) if info else 0.0001
                    if 'XAU' in symbol.upper() or 'GOLD' in symbol.upper():
                        pip_size = 0.1
                    elif 'BTC' in symbol.upper():
                        pip_size = 1.0
                    elif 'NAS' in symbol.upper() or 'US100' in symbol.upper() or 'NDX' in symbol.upper():
                        pip_size = 1.0
                    sl_dist = sl_pips * pip_size
                    if latest_signal['type'] == 'BUY':
                        latest_signal['sl'] = latest_signal['price'] - sl_dist
                    else:
                        latest_signal['sl'] = latest_signal['price'] + sl_dist
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
                        lot = self.mt5.calc_lot_size_from_risk(
                            symbol, balance, latest_signal['price'], sl, config.RISK_PER_TRADE
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
        if self.paper_mode:
            result = self.paper.place_order(
                symbol=signal['symbol'],
                order_type=signal['type'],
                volume=signal['volume'],
                price=signal['price'],
                sl=signal['sl'],
                tp=signal['tp'],
                comment=config.MT5_ORDER_COMMENT or signal.get('reason', '')
            )
            mt5_err = None
        else:
            result, mt5_err = self.mt5.place_order(
                symbol=signal['symbol'],
                order_type=signal['type'],
                volume=signal['volume'],
                price=signal['price'],
                sl=signal['sl'],
                tp=signal['tp'],
                comment=config.MT5_ORDER_COMMENT or signal.get('reason', '')
            )
        if result:
            result['time'] = datetime.now()
            self.trades_today.append(result)
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

    def show_status(self):
        if self.paper_mode:
            account = self.paper.get_account_info()
            stats = self.paper.get_stats()
            print("\n" + "=" * 50)
            print(f"PAPER TRADING STATUS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
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
            print(f"LIVE TRADING STATUS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 50)
            print(f"Balance: ${account['balance']:.2f}")
            print(f"Equity: ${account['equity']:.2f}")
            print(f"Profit: ${account['profit']:.2f}")
            print(f"Margin: ${account['margin']:.2f}")
            print(f"Free Margin: ${account['free_margin']:.2f}")
            print(f"\nOpen Positions: {len(positions)}")
            print("=" * 50)

    def run(self):
        print(f"\nStarting {'PAPER' if self.paper_mode else 'LIVE'} trading engine...")
        print(f"Strategy: {self.strategy_name}")
        print(f"Check interval: {config.LIVE_CHECK_INTERVAL}s")
        print(f"Manual approval: {'ON' if config.MANUAL_APPROVAL else 'OFF'}")
        print(f"Max trades/day: {config.MAX_TRADES_PER_DAY}")
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
                    if self.strategy_name == 'test' and getattr(config, 'TEST_SINGLE_RUN', False):
                        print("Daily limit reached. Exiting.")
                        self.running = False
                        break
                    if config.VOICE_ALERTS and config.VOICE_ALERT_ON_REJECT:
                        speak("Trade rejected. Reason: Daily trade limit reached.")
                    print("Waiting... (daily limit reached)")
                    time.sleep(config.LIVE_CHECK_INTERVAL)
                    continue
                self.update_positions()
                self._last_run_errors = []
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
                    if config.VOICE_ALERTS and config.VOICE_ALERT_ON_SIGNAL:
                        reason = signal.get('reason', 'Strategy signal')
                        speak(f"Trade found. {signal['type']} {signal['symbol']}. {reason}. Checking approval.")
                    result, exec_err = self.execute_signal(signal)
                    if result:
                        last_signal_time = datetime.now()
                        print(f"[EXECUTE] Order placed: {result.get('type')} {result.get('volume')} {result.get('symbol')} @ {result.get('price')}")
                    else:
                        if exec_err:
                            self._last_run_errors.append(exec_err)
                        print(f"[EXECUTE] Order failed — check [MT5] or [SAFETY] message above for reason.")
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
                print(f"\nNext check in {config.LIVE_CHECK_INTERVAL}s...")
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
