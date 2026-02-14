import pandas as pd
import config
from ..data_loader import fetch_data_yfinance, load_data_csv
from ..strategies import LiquiditySweepStrategy
from .backtest import _stats_dict


def _agg_ohlcv():
    return {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}

def run_liquidity_sweep_backtest(csv_path=None, symbol=None, period=None, return_stats=False):
    if csv_path:
        if not return_stats:
            print(f"Loading data from {csv_path}...")
        df = load_data_csv(csv_path)
        df_4h = df.resample('4h').agg(_agg_ohlcv()).dropna()
        df_1h = df.resample('1h').agg(_agg_ohlcv()).dropna()
        df_15m = df.resample('15m').agg(_agg_ohlcv()).dropna()
    else:
        symbol = symbol or config.SYMBOLS[0]
        period = period or getattr(config, 'BACKTEST_PERIOD', '60d')
        if not return_stats:
            print(f"Fetching data for {symbol} ({period})...")
        df_1h = fetch_data_yfinance(symbol, period=period, interval='1h')
        df_4h = df_1h.resample('4h').agg(_agg_ohlcv()).dropna()
        df_15m = fetch_data_yfinance(symbol, period=period, interval='15m')
    if df_4h.index.tz is not None:
        df_4h.index = df_4h.index.tz_convert(None)
    if df_1h.index.tz is not None:
        df_1h.index = df_1h.index.tz_convert(None)
    if df_15m.index.tz is not None:
        df_15m.index = df_15m.index.tz_convert(None)
    if not return_stats:
        print("Preparing indicators...")
    strat = LiquiditySweepStrategy(df_4h, df_1h, df_15m)
    df_4h_p, df_1h_p, df_15m_p = strat.prepare_data()
    strat.df_4h = df_4h_p
    strat.df_1h = df_1h_p
    strat.df_15m = df_15m_p
    if not return_stats:
        print("Running liquidity sweep strategy (4H → 1H → 15m)...")
    signals = strat.run_backtest()
    if signals.empty:
        if return_stats:
            return _stats_dict("liquidity_sweep", 0, 0, 0, 0.0, 0.0, config.INITIAL_BALANCE)
        print("No trades generated.")
        return
    if not return_stats:
        print(f"Generated {len(signals)} signals.")
    balance = config.INITIAL_BALANCE
    wins = 0
    losses = 0
    total_profit = 0.0
    total_loss = 0.0
    for _, trade in signals.iterrows():
        entry_price = trade['price']
        stop_loss = trade['sl']
        risk = config.RISK_REWARD_RATIO
        trade_time = trade['time']
        future_prices = df_15m.loc[df_15m.index > trade_time]
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
            "liquidity_sweep", wins + losses, wins, losses,
            total_profit, total_loss, balance,
        )
    print("-" * 30)
    print("LIQUIDITY SWEEP STRATEGY RESULTS (4H→1H→15m)")
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

if __name__ == "__main__":
    run_liquidity_sweep_backtest()
