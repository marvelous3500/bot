import pandas as pd
import config
from ..data_loader import fetch_data_yfinance, load_data_csv
from ..strategies import H1M5BOSStrategy
from .backtest import _stats_dict


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
        if not return_stats:
            print(f"Fetching data for {symbol} ({period})...")
        df_h1 = fetch_data_yfinance(symbol, period=period, interval='1h')
        df_m5 = fetch_data_yfinance(symbol, period=period, interval='5m')
    if df_h1.index.tz is not None:
        df_h1.index = df_h1.index.tz_convert(None)
    if df_m5.index.tz is not None:
        df_m5.index = df_m5.index.tz_convert(None)
    if not return_stats:
        print(f"H1 candles: {len(df_h1)}, M5 candles: {len(df_m5)}")
        print("Initializing H1-M5 BOS strategy...")
    strat = H1M5BOSStrategy(df_h1, df_m5)
    df_h1_processed, df_m5_processed = strat.prepare_data()
    strat.df_h1 = df_h1_processed
    strat.df_m5 = df_m5_processed
    if not return_stats:
        print("Running H1 BOS + M5 entry strategy...")
    signals = strat.run_backtest()
    if signals.empty:
        if return_stats:
            return _stats_dict("h1_m5_bos", 0, 0, 0, 0.0, 0.0, config.INITIAL_BALANCE)
        print("No trades generated.")
        print("-" * 30)
        print("H1 BOS STRATEGY RESULTS")
        print("-" * 30)
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
    print("-" * 30)
    print("H1 BOS STRATEGY RESULTS")
    print("-" * 30)
    print(f"Starting Capital: ${config.INITIAL_BALANCE:.2f}")
    print(f"Total Profit: ${total_profit:.2f}")
    print(f"Total Loss: ${total_loss:.2f}")
    print(f"Total Trades: {wins + losses}")
    print(f"Wins: {wins}")
    print(f"Losses: {losses}")
    if wins + losses > 0:
        print(f"Win Rate: {wins / (wins + losses) * 100:.2f}%")
    print(f"Final Balance: ${balance:.2f}")
    print(f"Return: {((balance - config.INITIAL_BALANCE) / config.INITIAL_BALANCE) * 100:.2f}%")
    print(f"Risk:Reward: 1:{risk}")

if __name__ == "__main__":
    run_bos_backtest()
