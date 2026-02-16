"""
Replay engine: runs the full live flow on historical data. No MT5 required.
"""
import pandas as pd
import config
from .data_loader import fetch_data_yfinance, fetch_daily_data_yfinance, load_data_csv
from .strategies import ICTStrategy, LiquiditySweepStrategy, H1M5BOSStrategy, ConfluenceStrategy, KingsleyGoldStrategy
from .backtest import prepare_pdh_pdl, _pip_size_for_symbol
from ai import get_signal_confidence, explain_trade, speak


def _strip_tz(df):
    if df is None or df.empty:
        return df
    if df.index.tz is not None:
        df = df.copy()
        df.index = df.index.tz_convert(None)
    return df


def load_replay_data(strategy_name, symbol, csv_path):
    symbol = symbol or config.SYMBOLS[0]
    if csv_path:
        df = load_data_csv(csv_path)
        if df.index.tz is not None:
            df.index = df.index.tz_convert(None)

    if strategy_name == 'pdh_pdl':
        if csv_path:
            df_5m = df
            df_daily = df.resample('1D').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()
        else:
            df_5m = fetch_data_yfinance(symbol, period='60d', interval='5m')
            df_daily = fetch_daily_data_yfinance(symbol, period='6mo')
        df_5m = _strip_tz(df_5m)
        df_daily = _strip_tz(df_daily)
        return df_5m, {'df_5m': df_5m, 'df_daily': df_daily, 'symbol': symbol}

    if strategy_name == 'liquidity_sweep':
        agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
        if csv_path:
            df_4h = df.resample('4h').agg(agg).dropna()
            df_1h = df.resample('1h').agg(agg).dropna()
            df_15m = df.resample('15m').agg(agg).dropna()
        else:
            df_1h = fetch_data_yfinance(symbol, period='60d', interval='1h')
            df_4h = df_1h.resample('4h').agg(agg).dropna()
            df_15m = fetch_data_yfinance(symbol, period='60d', interval='15m')
        df_4h = _strip_tz(df_4h)
        df_1h = _strip_tz(df_1h)
        df_15m = _strip_tz(df_15m)
        return df_15m, {'df_4h': df_4h, 'df_1h': df_1h, 'df_15m': df_15m, 'symbol': symbol}

    if strategy_name == 'confluence':
        if csv_path:
            df_4h = df.resample('4h').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()
            df_15m = df
        else:
            df_4h = fetch_data_yfinance(symbol, period='60d', interval='1h')
            df_4h = df_4h.resample('4h').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()
            df_15m = fetch_data_yfinance(symbol, period='60d', interval='15m')
        df_4h = _strip_tz(df_4h)
        df_15m = _strip_tz(df_15m)
        return df_15m, {'df_4h': df_4h, 'df_15m': df_15m, 'symbol': symbol}

    if strategy_name == 'h1_m5_bos':
        if csv_path:
            df_h1 = df.resample('1h').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()
            df_m5 = df
        else:
            df_h1 = fetch_data_yfinance(symbol, period='60d', interval='1h')
            df_m5 = fetch_data_yfinance(symbol, period='60d', interval='5m')
        df_h1 = _strip_tz(df_h1)
        df_m5 = _strip_tz(df_m5)
        return df_m5, {'df_h1': df_h1, 'df_m5': df_m5, 'symbol': symbol}

    if strategy_name == 'kingsely_gold':
        agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
        symbol = symbol or 'GC=F'
        if csv_path:
            df_h1 = df.resample('1h').agg(agg).dropna()
            df_15m = df.resample('15min').agg(agg).dropna()
        else:
            df_h1 = fetch_data_yfinance(symbol, period='60d', interval='1h')
            df_15m = fetch_data_yfinance(symbol, period='60d', interval='15m')
        df_h1 = _strip_tz(df_h1)
        df_15m = _strip_tz(df_15m)
        return df_15m, {'df_h1': df_h1, 'df_15m': df_15m, 'symbol': symbol}

    raise ValueError(f"Unknown strategy: {strategy_name}")


def run_strategy_at_time(strategy_name, data, current_time):
    signal = None
    symbol = data.get('symbol', config.SYMBOLS[0])
    if strategy_name == 'pdh_pdl':
        df_5m = data['df_5m'].loc[data['df_5m'].index <= current_time]
        df_daily = data['df_daily'].loc[data['df_daily'].index <= current_time]
        if len(df_5m) < 50 or len(df_daily) < 5:
            return None
        strat = ICTStrategy(df_5m)
        df_p = strat.prepare_data()
        pdh_series, pdl_series = prepare_pdh_pdl(df_p, df_daily)
        signals_df = strat.run_backtest(pdh_series, pdl_series)
        if not signals_df.empty:
            signal = signals_df.iloc[-1].to_dict()
            signal['sl'] = signal.get('sl')
    elif strategy_name == 'liquidity_sweep':
        df_4h = data['df_4h'].loc[data['df_4h'].index <= current_time]
        df_1h = data['df_1h'].loc[data['df_1h'].index <= current_time]
        df_15m = data['df_15m'].loc[data['df_15m'].index <= current_time]
        if len(df_4h) < 10 or len(df_1h) < 10 or len(df_15m) < 50:
            return None
        strat = LiquiditySweepStrategy(df_4h, df_1h, df_15m)
        strat.prepare_data()
        signals_df = strat.run_backtest()
        if not signals_df.empty:
            signal = signals_df.iloc[-1].to_dict()
    elif strategy_name == 'confluence':
        df_4h = data['df_4h'].loc[data['df_4h'].index <= current_time]
        df_15m = data['df_15m'].loc[data['df_15m'].index <= current_time]
        if len(df_4h) < 10 or len(df_15m) < 50:
            return None
        strat = ConfluenceStrategy(df_4h, df_15m)
        strat.prepare_data()
        signals_df = strat.run_backtest()
        if not signals_df.empty:
            signal = signals_df.iloc[-1].to_dict()
            pip = _pip_size_for_symbol(symbol)
            sl_pips = getattr(config, 'CONFLUENCE_SL_PIPS', 50)
            dist = sl_pips * pip
            if signal['type'] == 'BUY':
                signal['sl'] = signal['price'] - dist
            else:
                signal['sl'] = signal['price'] + dist
    elif strategy_name == 'h1_m5_bos':
        df_h1 = data['df_h1'].loc[data['df_h1'].index <= current_time]
        df_m5 = data['df_m5'].loc[data['df_m5'].index <= current_time]
        if len(df_h1) < 20 or len(df_m5) < 100:
            return None
        strat = H1M5BOSStrategy(df_h1, df_m5)
        strat.prepare_data()
        signals_df = strat.run_backtest()
        if not signals_df.empty:
            signal = signals_df.iloc[-1].to_dict()
    elif strategy_name == 'kingsely_gold':
        df_h1 = data['df_h1'].loc[data['df_h1'].index <= current_time]
        df_15m = data['df_15m'].loc[data['df_15m'].index <= current_time]
        if len(df_h1) < 20 or len(df_15m) < 100:
            return None
        strat = KingsleyGoldStrategy(df_h1, df_15m)
        strat.prepare_data()
        signals_df = strat.run_backtest()
        if not signals_df.empty:
            signal = signals_df.iloc[-1].to_dict()
    if signal is None:
        return None
    signal['symbol'] = symbol
    signal['volume'] = config.MAX_POSITION_SIZE
    sl_dist = abs(signal['price'] - signal['sl'])
    if signal['type'] == 'BUY':
        signal['tp'] = signal['price'] + sl_dist * config.RISK_REWARD_RATIO
    else:
        signal['tp'] = signal['price'] - sl_dist * config.RISK_REWARD_RATIO
    return signal


def run_replay(strategy_name, symbol=None, csv_path=None, auto_approve=True):
    if strategy_name == 'kingsely_gold':
        symbol = symbol or 'GC=F'
    print(f"Loading replay data for {strategy_name}...")
    entry_df, data = load_replay_data(strategy_name, symbol, csv_path)
    symbol = data.get('symbol', symbol or config.SYMBOLS[0])
    print(f"Replaying {len(entry_df)} bars (symbol={symbol}). Approval: {'auto' if auto_approve else 'prompt'}")
    balance = config.INITIAL_BALANCE
    positions = []
    closed_trades = []
    execution_times = []
    last_signal_time = None
    max_trades = getattr(config, 'MAX_TRADES_PER_DAY', 5)
    step = max(1, getattr(config, 'REPLAY_STEP_BARS', 1))
    total_bars = len(entry_df)
    for i in range(total_bars):
        t = entry_df.index[i]
        bar = entry_df.iloc[i]
        current_date = t.date() if hasattr(t, 'date') else pd.Timestamp(t).date()
        if i % 500 == 0 or i == total_bars - 1:
            print(f"  Replay progress: bar {i + 1}/{total_bars} ({t})", flush=True)
        for pos in positions[:]:
            sl, tp = pos['sl'], pos['tp']
            if pos['type'] == 'BUY':
                if bar['low'] <= sl:
                    loss = balance * config.RISK_PER_TRADE
                    balance -= loss
                    positions.remove(pos)
                    ct = {**pos, 'time_close': t, 'profit': -loss, 'outcome': 'loss'}
                    if getattr(config, 'AI_EXPLAIN_TRADES', False):
                        summary = {'reason': pos.get('reason', ''), 'symbol': pos['symbol'], 'type': pos['type'], 'price': pos['price_open'], 'sl': pos['sl'], 'tp': pos['tp'], 'outcome': 'loss'}
                        ct['ai_explain'] = explain_trade(summary)
                    closed_trades.append(ct)
                    continue
                if bar['high'] >= tp:
                    gain = balance * config.RISK_PER_TRADE * config.RISK_REWARD_RATIO
                    balance += gain
                    positions.remove(pos)
                    ct = {**pos, 'time_close': t, 'profit': gain, 'outcome': 'win'}
                    if getattr(config, 'AI_EXPLAIN_TRADES', False):
                        summary = {'reason': pos.get('reason', ''), 'symbol': pos['symbol'], 'type': pos['type'], 'price': pos['price_open'], 'sl': pos['sl'], 'tp': pos['tp'], 'outcome': 'win'}
                        ct['ai_explain'] = explain_trade(summary)
                    closed_trades.append(ct)
            else:
                if bar['high'] >= sl:
                    loss = balance * config.RISK_PER_TRADE
                    balance -= loss
                    positions.remove(pos)
                    ct = {**pos, 'time_close': t, 'profit': -loss, 'outcome': 'loss'}
                    if getattr(config, 'AI_EXPLAIN_TRADES', False):
                        summary = {'reason': pos.get('reason', ''), 'symbol': pos['symbol'], 'type': pos['type'], 'price': pos['price_open'], 'sl': pos['sl'], 'tp': pos['tp'], 'outcome': 'loss'}
                        ct['ai_explain'] = explain_trade(summary)
                    closed_trades.append(ct)
                    continue
                if bar['low'] <= tp:
                    gain = balance * config.RISK_PER_TRADE * config.RISK_REWARD_RATIO
                    balance += gain
                    positions.remove(pos)
                    ct = {**pos, 'time_close': t, 'profit': gain, 'outcome': 'win'}
                    if getattr(config, 'AI_EXPLAIN_TRADES', False):
                        summary = {'reason': pos.get('reason', ''), 'symbol': pos['symbol'], 'type': pos['type'], 'price': pos['price_open'], 'sl': pos['sl'], 'tp': pos['tp'], 'outcome': 'win'}
                        ct['ai_explain'] = explain_trade(summary)
                    closed_trades.append(ct)
        count_today = len([x for x in execution_times if (x.date() if hasattr(x, 'date') else pd.Timestamp(x).date()) == current_date])
        if count_today >= max_trades:
            if config.VOICE_ALERTS and getattr(config, 'VOICE_ALERT_ON_REJECT', True):
                speak("Trade rejected. Reason: Daily trade limit reached.")
            continue
        if i % step != 0:
            continue
        signal = run_strategy_at_time(strategy_name, data, t)
        if not signal:
            continue
        sig_time = signal.get('time')
        if sig_time is None:
            continue
        if last_signal_time is not None and pd.Timestamp(sig_time) <= pd.Timestamp(last_signal_time):
            continue
        if pd.Timestamp(sig_time) > t:
            continue
        if getattr(config, 'AI_ENABLED', False):
            score = get_signal_confidence(signal)
            if score is not None and score < getattr(config, 'AI_CONFIDENCE_THRESHOLD', 2.0):
                if config.VOICE_ALERTS and getattr(config, 'VOICE_ALERT_ON_REJECT', True):
                    speak("Trade rejected. Reason: Below confidence threshold.")
                continue
        if config.VOICE_ALERTS and getattr(config, 'VOICE_ALERT_ON_SIGNAL', True):
            reason = signal.get('reason', 'Strategy signal')
            speak(f"Trade found. {signal['type']} {signal['symbol']}. {reason}.")
        last_signal_time = sig_time
        execution_times.append(t)
        pos = {
            'ticket': len(positions) + len(closed_trades) + 1,
            'symbol': signal['symbol'],
            'type': signal['type'],
            'volume': signal['volume'],
            'price_open': signal['price'],
            'sl': signal['sl'],
            'tp': signal['tp'],
            'time': t,
            'reason': signal.get('reason', ''),
        }
        positions.append(pos)
    wins = len([x for x in closed_trades if x.get('profit', 0) > 0])
    losses = len([x for x in closed_trades if x.get('profit', 0) <= 0])
    total = wins + losses
    print("\n" + "=" * 50)
    print("REPLAY RESULTS (live flow on historical data)")
    print("=" * 50)
    print(f"Total Trades: {total}")
    print(f"Wins: {wins}")
    print(f"Losses: {losses}")
    if total > 0:
        print(f"Win Rate: {wins / total * 100:.2f}%")
    print(f"Final Balance: ${balance:.2f}")
    print(f"Return: {((balance - config.INITIAL_BALANCE) / config.INITIAL_BALANCE) * 100:.2f}%")
    print("=" * 50)
