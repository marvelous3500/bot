import pandas as pd
import config
from ..data_loader import fetch_data_yfinance, fetch_daily_data_yfinance, load_data_csv
from ..strategies import ICTStrategy

def prepare_pdh_pdl(df_5m, df_daily):
    """Maps daily PDH/PDL to the 5m dataframe."""
    if df_5m.index.tz is not None:
        df_5m.index = df_5m.index.tz_convert(None)
    if df_daily.index.tz is not None:
        df_daily.index = df_daily.index.tz_convert(None)
    df_5m['pdh'] = None
    df_5m['pdl'] = None
    input_daily = df_daily.shift(1).copy()
    aligned_daily = input_daily.reindex(df_5m.index, method='ffill')
    return aligned_daily['high'], aligned_daily['low']


def _stats_dict(strategy, trades, wins, losses, total_profit, total_loss, final_balance):
    """Build a result dict for summary tables (used by all strategy runners)."""
    initial = config.INITIAL_BALANCE
    win_rate = (100.0 * wins / trades) if trades else 0.0
    return_pct = (100.0 * (final_balance - initial) / initial) if initial else 0.0
    return {
        "strategy": strategy,
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "total_profit": total_profit,
        "total_loss": total_loss,
        "final_balance": final_balance,
        "return_pct": return_pct,
    }


def run_backtest_simulation(csv_path=None, symbol=None, period=None, return_stats=False):
    if csv_path:
        if not return_stats:
            print(f"Loading data from {csv_path}...")
        df = load_data_csv(csv_path)
        df_daily = df.resample('1D').agg({
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
        }).dropna()
    else:
        symbol = symbol or config.SYMBOLS[0]
        period = period or getattr(config, 'BACKTEST_PERIOD', '60d')
        if not return_stats:
            print(f"Fetching data for {symbol} ({period})...")
        df = fetch_data_yfinance(symbol, period=period, interval='5m')
        df_daily = fetch_daily_data_yfinance(symbol, period='6mo')
    if df.index.tz is not None:
        df.index = df.index.tz_convert(None)
    if df_daily.index.tz is not None:
        df_daily.index = df_daily.index.tz_convert(None)
    if not return_stats:
        print("Preparing indicators...")
    strat = ICTStrategy(df)
    df_processed = strat.prepare_data()
    pdh_series, pdl_series = prepare_pdh_pdl(df_processed, df_daily)
    if not return_stats:
        print("Running strategy logic...")
    signals = strat.run_backtest(pdh_series, pdl_series)
    if signals.empty:
        if return_stats:
            return _stats_dict("pdh_pdl", 0, 0, 0, 0.0, 0.0, config.INITIAL_BALANCE)
        print("No trades generated.")
        return
    if not return_stats:
        print(f"Generated {len(signals)} signals.")
    balance = config.INITIAL_BALANCE
    equity_curve = [balance]
    wins = 0
    losses = 0
    total_profit = 0.0
    total_loss = 0.0
    for _, trade in signals.iterrows():
        entry_price = trade['price']
        stop_loss = trade['sl']
        risk = config.RISK_REWARD_RATIO
        trade_time = trade['time']
        future_prices = df.loc[df.index > trade_time]
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
        equity_curve.append(balance)
    if return_stats:
        return _stats_dict(
            "pdh_pdl", wins + losses, wins, losses,
            total_profit, total_loss, balance,
        )
    print("-" * 30)
    print("BACKTEST RESULTS")
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
    run_backtest_simulation()
