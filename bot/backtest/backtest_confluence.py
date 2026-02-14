"""
Backtest for confluence strategy: 4H BOS + 15m OB, kill zone. SL = CONFLUENCE_SL_PIPS pips.
"""
import pandas as pd
import config
from ..data_loader import fetch_data_yfinance, load_data_csv
from ..strategies import ConfluenceStrategy
from .backtest import _stats_dict


def _pip_size_for_symbol(symbol):
    """Return pip size for SL/TP. Gold, BTC, indices, vs forex."""
    if symbol is None:
        return 0.0001
    s = str(symbol).upper()
    if 'GC=' in s or 'XAU' in s or 'GOLD' in s:
        return 0.1
    if 'BTC' in s:
        return 1.0
    if 'NDX' in s or 'NAS' in s or 'US100' in s:
        return 1.0
    return 0.0001


def run_confluence_backtest(csv_path=None, symbol=None, period=None, return_stats=False):
    if csv_path:
        if not return_stats:
            print(f"Loading data from {csv_path}...")
        df = load_data_csv(csv_path)
        df_4h = df.resample('4h').agg({
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
        }).dropna()
        df_15m = df
    else:
        symbol = symbol or config.SYMBOLS[0]
        period = period or getattr(config, 'BACKTEST_PERIOD', '60d')
        if not return_stats:
            print(f"Fetching data for {symbol} ({period})...")
        df_4h = fetch_data_yfinance(symbol, period=period, interval='1h')
        df_4h = df_4h.resample('4h').agg({
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
        }).dropna()
        df_15m = fetch_data_yfinance(symbol, period=period, interval='15m')
    if df_4h.index.tz is not None:
        df_4h.index = df_4h.index.tz_convert(None)
    if df_15m.index.tz is not None:
        df_15m.index = df_15m.index.tz_convert(None)
    if not return_stats:
        print("Preparing indicators (4H BOS + 15m OB)...")
    strat = ConfluenceStrategy(df_4h, df_15m)
    df_4h_p, df_15m_p = strat.prepare_data()
    strat.df_4h = df_4h_p
    strat.df_15m = df_15m_p
    signals = strat.run_backtest()
    if signals.empty:
        if return_stats:
            return _stats_dict("confluence", 0, 0, 0, 0.0, 0.0, config.INITIAL_BALANCE)
        print("No trades generated.")
        return
    pip = _pip_size_for_symbol(symbol)
    sl_pips = getattr(config, 'CONFLUENCE_SL_PIPS', 50)
    sl_distance = sl_pips * pip
    for i in range(len(signals)):
        row = signals.iloc[i]
        if row['type'] == 'BUY':
            signals.at[signals.index[i], 'sl'] = row['price'] - sl_distance
        else:
            signals.at[signals.index[i], 'sl'] = row['price'] + sl_distance
    if not return_stats:
        print(f"Generated {len(signals)} signals (SL={sl_pips} pips).")
    balance = config.INITIAL_BALANCE
    wins = 0
    losses = 0
    total_profit = 0.0
    total_loss = 0.0
    risk = config.RISK_REWARD_RATIO
    max_trades = getattr(config, 'BACKTEST_MAX_TRADES', None)
    for _, trade in signals.iterrows():
        if max_trades is not None and (wins + losses) >= max_trades:
            break
        entry_price = trade['price']
        stop_loss = trade['sl']
        trade_time = trade['time']
        future_prices = df_15m.loc[df_15m.index > trade_time]
        if future_prices.empty:
            continue
        if trade['type'] == 'BUY':
            sl_dist = entry_price - stop_loss
            tp_price = entry_price + (sl_dist * risk)
            outcome = None
            for _, bar in future_prices.iterrows():
                if bar['low'] <= stop_loss:
                    outcome = 'LOSS'
                    break
                if bar['high'] >= tp_price:
                    outcome = 'WIN'
                    break
        else:
            sl_dist = stop_loss - entry_price
            tp_price = entry_price - (sl_dist * risk)
            outcome = None
            for _, bar in future_prices.iterrows():
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
            "confluence", wins + losses, wins, losses,
            total_profit, total_loss, balance,
        )
    print("-" * 30)
    print("CONFLUENCE STRATEGY RESULTS (4H BOS + 15m OB, 50 pip SL)")
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
    run_confluence_backtest()
