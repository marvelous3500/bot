"""
Replay engine: runs the full live flow on historical data. No MT5 required.
"""
import pandas as pd
import config
from .data_loader import fetch_data_yfinance, load_data_csv
from .strategies import MarvellousStrategy, VesterStrategy
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

    if strategy_name == 'marvellous':
        from . import marvellous_config as mc
        agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
        symbol = symbol or mc.MARVELLOUS_BACKTEST_SYMBOL
        entry_tf = getattr(mc, 'ENTRY_TIMEFRAME', '5m')
        if csv_path:
            df_h1 = df.resample('1h').agg(agg).dropna()
            df_4h = df_h1.resample('4h').agg(agg).dropna()
            df_daily = df_h1.resample('1D').agg(agg).dropna()
            df_m15 = df.resample('15min').agg(agg).dropna()
            if entry_tf == '15m':
                df_entry = df_m15.copy()
            else:
                resample_entry = '5min' if entry_tf == '5m' else '1min'
                df_entry = df.resample(resample_entry).agg(agg).dropna()
        else:
            fetch_period = '7d' if entry_tf == '1m' else '60d'
            df_h1 = fetch_data_yfinance(symbol, period=fetch_period, interval='1h')
            df_4h = df_h1.resample('4h').agg(agg).dropna()
            df_daily = df_h1.resample('1D').agg(agg).dropna()
            df_m15 = fetch_data_yfinance(symbol, period=fetch_period, interval='15m')
            if entry_tf == '15m':
                df_entry = df_m15.copy()
            else:
                df_entry = fetch_data_yfinance(symbol, period=fetch_period, interval='1m' if entry_tf == '1m' else '5m')
        for d in (df_daily, df_4h, df_h1, df_m15, df_entry):
            _strip_tz(d)
        return df_entry, {'df_daily': df_daily, 'df_4h': df_4h, 'df_h1': df_h1, 'df_m15': df_m15, 'df_entry': df_entry, 'symbol': symbol}

    if strategy_name == 'vester':
        from . import vester_config as vc
        agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
        symbol = symbol or getattr(config, 'VESTER_BACKTEST_SYMBOL', vc.VESTER_BACKTEST_SYMBOL)
        if csv_path:
            df_h1 = df.resample('1h').agg(agg).dropna()
            df_m5 = df.resample('5min').agg(agg).dropna()
            df_m1 = df.resample('1min').agg(agg).dropna()
        else:
            fetch_period = '7d'
            df_h1 = fetch_data_yfinance(symbol, period=fetch_period, interval='1h')
            df_m5 = fetch_data_yfinance(symbol, period=fetch_period, interval='5m')
            df_m1 = fetch_data_yfinance(symbol, period=fetch_period, interval='1m')
        df_h4 = df_h1.resample('4h').agg(agg).dropna()
        for d in (df_h1, df_m5, df_m1, df_h4):
            _strip_tz(d)
        return df_m1, {'df_h1': df_h1, 'df_m5': df_m5, 'df_m1': df_m1, 'df_h4': df_h4, 'symbol': symbol}

    raise ValueError(f"Unknown strategy: {strategy_name}")


def run_strategy_at_time(strategy_name, data, current_time):
    signal = None
    symbol = data.get('symbol', config.SYMBOLS[0])
    if strategy_name == 'marvellous':
        df_daily = data.get('df_daily')
        df_4h = data.get('df_4h')
        df_h1 = data['df_h1'].loc[data['df_h1'].index <= current_time]
        df_m15 = data['df_m15'].loc[data['df_m15'].index <= current_time]
        df_entry = data['df_entry'].loc[data['df_entry'].index <= current_time]
        if df_daily is not None:
            df_daily = df_daily.loc[df_daily.index <= current_time]
        if df_4h is not None:
            df_4h = df_4h.loc[df_4h.index <= current_time]
        if len(df_h1) < 20 or len(df_m15) < 100 or len(df_entry) < 50:
            return None
        strat = MarvellousStrategy(
            df_daily=df_daily,
            df_4h=df_4h,
            df_h1=df_h1,
            df_m15=df_m15,
            df_entry=df_entry,
            verbose=False,
        )
        strat.prepare_data()
        signals_df = strat.run_backtest()
        if not signals_df.empty:
            signal = signals_df.iloc[-1].to_dict()
    elif strategy_name == 'vester':
        df_h1 = data['df_h1'].loc[data['df_h1'].index <= current_time]
        df_m5 = data['df_m5'].loc[data['df_m5'].index <= current_time]
        df_m1 = data['df_m1'].loc[data['df_m1'].index <= current_time]
        df_h4 = data.get('df_h4')
        if df_h4 is not None:
            df_h4 = df_h4.loc[df_h4.index <= current_time]
        if len(df_h1) < 20 or len(df_m5) < 100 or len(df_m1) < 50:
            return None
        strat = VesterStrategy(
            df_h1=df_h1,
            df_m5=df_m5,
            df_m1=df_m1,
            df_h4=df_h4,
            symbol=symbol,
            verbose=False,
        )
        strat.prepare_data()
        signals_df = strat.run_backtest()
        if not signals_df.empty:
            signal = signals_df.iloc[-1].to_dict()
    if signal is None:
        return None
    signal['symbol'] = symbol
    signal['volume'] = config.MAX_POSITION_SIZE
    rr = getattr(config, 'VESTER_MIN_RR', config.RISK_REWARD_RATIO) if strategy_name == 'vester' else config.RISK_REWARD_RATIO
    sl_dist = abs(signal['price'] - signal['sl'])
    if signal['type'] == 'BUY':
        signal['tp'] = signal['price'] + sl_dist * rr
    else:
        signal['tp'] = signal['price'] - sl_dist * rr
    return signal


def run_replay(strategy_name, symbol=None, csv_path=None, auto_approve=True):
    if strategy_name == 'marvellous':
        from . import marvellous_config as mc
        symbol = symbol or mc.MARVELLOUS_BACKTEST_SYMBOL
    elif strategy_name == 'vester':
        from . import vester_config as vc
        symbol = symbol or getattr(config, 'VESTER_BACKTEST_SYMBOL', vc.VESTER_BACKTEST_SYMBOL)
    print(f"Loading replay data for {strategy_name}...")
    entry_df, data = load_replay_data(strategy_name, symbol, csv_path)
    symbol = data.get('symbol', symbol or config.SYMBOLS[0])
    risk_pct = getattr(config, 'VESTER_RISK_PER_TRADE', config.RISK_PER_TRADE) if strategy_name == 'vester' else config.RISK_PER_TRADE
    rr_ratio = config.RISK_REWARD_RATIO
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
                    loss = balance * risk_pct
                    balance -= loss
                    positions.remove(pos)
                    ct = {**pos, 'time_close': t, 'profit': -loss, 'outcome': 'loss'}
                    if getattr(config, 'AI_EXPLAIN_TRADES', False):
                        summary = {'reason': pos.get('reason', ''), 'symbol': pos['symbol'], 'type': pos['type'], 'price': pos['price_open'], 'sl': pos['sl'], 'tp': pos['tp'], 'outcome': 'loss'}
                        ct['ai_explain'] = explain_trade(summary)
                    closed_trades.append(ct)
                    continue
                if bar['high'] >= tp:
                    gain = balance * risk_pct * rr_ratio
                    balance += gain
                    positions.remove(pos)
                    ct = {**pos, 'time_close': t, 'profit': gain, 'outcome': 'win'}
                    if getattr(config, 'AI_EXPLAIN_TRADES', False):
                        summary = {'reason': pos.get('reason', ''), 'symbol': pos['symbol'], 'type': pos['type'], 'price': pos['price_open'], 'sl': pos['sl'], 'tp': pos['tp'], 'outcome': 'win'}
                        ct['ai_explain'] = explain_trade(summary)
                    closed_trades.append(ct)
            else:
                if bar['high'] >= sl:
                    loss = balance * risk_pct
                    balance -= loss
                    positions.remove(pos)
                    ct = {**pos, 'time_close': t, 'profit': -loss, 'outcome': 'loss'}
                    if getattr(config, 'AI_EXPLAIN_TRADES', False):
                        summary = {'reason': pos.get('reason', ''), 'symbol': pos['symbol'], 'type': pos['type'], 'price': pos['price_open'], 'sl': pos['sl'], 'tp': pos['tp'], 'outcome': 'loss'}
                        ct['ai_explain'] = explain_trade(summary)
                    closed_trades.append(ct)
                    continue
                if bar['low'] <= tp:
                    gain = balance * risk_pct * rr_ratio
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
        max_per_session = getattr(config, 'MAX_TRADES_PER_SESSION', None)
        session_hours = getattr(config, 'TRADE_SESSION_HOURS', {})
        if max_per_session is not None and session_hours:
            bar_hour = t.hour if hasattr(t, 'hour') else pd.Timestamp(t).hour
            current_session = session_hours.get(bar_hour)
            if current_session is not None:
                execs_in_session = [
                    x for x in execution_times
                    if (x.date() if hasattr(x, 'date') else pd.Timestamp(x).date()) == current_date
                    and session_hours.get(x.hour if hasattr(x, 'hour') else pd.Timestamp(x).hour) == current_session
                ]
                if len(execs_in_session) >= max_per_session:
                    if config.VOICE_ALERTS and getattr(config, 'VOICE_ALERT_ON_REJECT', True):
                        speak("Trade rejected. Reason: Session trade limit reached.")
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
