import pandas as pd
import config
from ..data_loader import fetch_data_yfinance, load_data_csv
from ..strategies import H1M5BOSStrategy
from .common import _stats_dict


def run_bos_backtest(csv_path=None, symbol=None, period=None, return_stats=False):
    if csv_path:
        if not return_stats:
            print(f"Loading data from {csv_path}...")
        df = load_data_csv(csv_path)
        df_h1 = df.resample('1h').agg({
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
        }).dropna()
        df_m5 = df
    else:
        symbol = symbol or config.SYMBOLS[0]
        period = period or getattr(config, 'BACKTEST_PERIOD', '60d')
        agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
        if not return_stats:
            print(f"Fetching data for {symbol} ({period})...")
        df_h1 = fetch_data_yfinance(symbol, period=period, interval='1h')
        df_m5 = fetch_data_yfinance(symbol, period=period, interval='5m')
        df_4h = df_h1.resample('4h').agg(agg).dropna() if getattr(config, 'USE_4H_BIAS_FILTER', False) else None
        df_daily = df_h1.resample('1D').agg(agg).dropna() if getattr(config, 'USE_DAILY_BIAS_FILTER', False) else None
    if csv_path:
        df_4h = df_h1.resample('4h').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna() if getattr(config, 'USE_4H_BIAS_FILTER', False) else None
        df_daily = df_h1.resample('1D').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna() if getattr(config, 'USE_DAILY_BIAS_FILTER', False) else None
    if df_h1.index.tz is not None:
        df_h1.index = df_h1.index.tz_convert(None)
    if df_m5.index.tz is not None:
        df_m5.index = df_m5.index.tz_convert(None)
    if df_4h is not None and df_4h.index.tz is not None:
        df_4h.index = df_4h.index.tz_convert(None)
    if df_daily is not None and df_daily.index.tz is not None:
        df_daily.index = df_daily.index.tz_convert(None)
    if not return_stats:
        print(f"H1 candles: {len(df_h1)}, M5 candles: {len(df_m5)}")
        print("Initializing H1-M5 BOS strategy...")
    strat = H1M5BOSStrategy(df_h1, df_m5, df_4h=df_4h, df_daily=df_daily)
    df_h1_processed, df_m5_processed = strat.prepare_data()
    strat.df_h1 = df_h1_processed
    strat.df_m5 = df_m5_processed
    if not return_stats:
        print("Running H1 BOS + M5 entry strategy...")
    signals = strat.run_backtest()
    if signals.empty:
        if return_stats:
            return _stats_dict("h1_m5_bos", 0, 0, 0, 0.0, 0.0, config.INITIAL_BALANCE)
        used_symbol = symbol or config.SYMBOLS[0]
        used_period = period or getattr(config, 'BACKTEST_PERIOD', '60d')
        print()
        print("Backtest Parameters:")
        print(f"  Asset: {used_symbol}")
        print(f"  Risk per trade: {config.RISK_PER_TRADE * 100:.0f}%")
        print(f"  Trade Limit: {'No trade limit' if getattr(config, 'BACKTEST_MAX_TRADES', None) is None else config.BACKTEST_MAX_TRADES}")
        print(f"  Duration: {used_period}")
        print()
        print("| Strategy          | Trades | Wins | Losses | Win rate  | Final balance | Return      |")
        print("| :---------------- | :----- | :--- | :----- | :-------- | :------------ | :---------- |")
        print("| h1_m5_bos         |      0 |    0 |      0 |     0.00% | $      100.00 |      0.00% |")
        return
    if not return_stats:
        print(f"\nGenerated {len(signals)} signals.")
    balance = config.INITIAL_BALANCE
    wins = 0
    losses = 0
    total_profit = 0.0
    total_loss = 0.0
    risk = getattr(config, 'RISK_REWARD_RATIO', 2.0)
    for _, trade in signals.iterrows():
        entry_price = trade['price']
        stop_loss = trade['sl']
        trade_time = trade['time']
        future_prices = df_m5.loc[df_m5.index > trade_time]
        if future_prices.empty:
            continue
        if trade['type'] == 'BUY':
            sl_dist = entry_price - stop_loss
            tp_price = entry_price + (sl_dist * risk)
            outcome = None
            for idx, bar in future_prices.iterrows():
                if bar['low'] <= stop_loss:
                    outcome = 'LOSS'
                    break
                if bar['high'] >= tp_price:
                    outcome = 'WIN'
                    break
            if outcome == 'WIN':
                profit = (balance * config.RISK_PER_TRADE) * risk
                total_profit += profit
                balance += profit
                wins += 1
            elif outcome == 'LOSS':
                loss = (balance * config.RISK_PER_TRADE)
                total_loss += loss
                balance -= loss
                losses += 1
        elif trade['type'] == 'SELL':
            sl_dist = stop_loss - entry_price
            tp_price = entry_price - (sl_dist * risk)
            outcome = None
            for idx, bar in future_prices.iterrows():
                if bar['high'] >= stop_loss:
                    outcome = 'LOSS'
                    break
                if bar['low'] <= tp_price:
                    outcome = 'WIN'
                    break
            if outcome == 'WIN':
                profit = (balance * config.RISK_PER_TRADE) * risk
                total_profit += profit
                balance += profit
                wins += 1
            elif outcome == 'LOSS':
                loss = (balance * config.RISK_PER_TRADE)
                total_loss += loss
                balance -= loss
                losses += 1
    if return_stats:
        return _stats_dict(
            "h1_m5_bos", wins + losses, wins, losses,
            total_profit, total_loss, balance,
        )
    # Display in image format (same as kingsely_gold)
    used_symbol = symbol or config.SYMBOLS[0]
    used_period = period or getattr(config, 'BACKTEST_PERIOD', '60d')
    trade_limit = getattr(config, 'BACKTEST_MAX_TRADES', None)
    trade_limit_str = "No trade limit" if trade_limit is None else str(trade_limit)
    risk_pct = config.RISK_PER_TRADE * 100
    return_pct = ((balance - config.INITIAL_BALANCE) / config.INITIAL_BALANCE) * 100
    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
    print()
    print("Backtest Parameters:")
    print(f"  Asset: {used_symbol}")
    print(f"  Risk per trade: {risk_pct:.0f}%")
    print(f"  Trade Limit: {trade_limit_str}")
    print(f"  Duration: {used_period}")
    print()
    print("| Strategy          | Trades | Wins | Losses | Win rate  | Final balance | Return      |")
    print("| :---------------- | :----- | :--- | :----- | :-------- | :------------ | :---------- |")
    ret_str = f"{'+' if return_pct >= 0 else ''}{return_pct:,.2f}%"
    print(f"| h1_m5_bos         | {wins + losses:>5} | {wins:>4} | {losses:>6} | {win_rate:>8.2f}% | ${balance:>11,.2f} | {ret_str:>10} |")

if __name__ == "__main__":
    run_bos_backtest()
