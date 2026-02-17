"""Backtest runner for Test strategy (H1 trend follow, gold only)."""
import pandas as pd
import config
from ..data_loader import fetch_data_yfinance, load_data_csv
from ..strategies import TestStrategy
from .backtest import _stats_dict

TEST_BACKTEST_SYMBOL = 'GC=F'
TEST_LIVE_SYMBOL = 'XAUUSD'


def run_test_backtest(csv_path=None, symbol=None, period=None, return_stats=False):
    agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
    if csv_path:
        df = load_data_csv(csv_path)
        df_h1 = df.resample('1h').agg(agg).dropna()
    else:
        symbol = symbol or getattr(config, 'TEST_BACKTEST_SYMBOL', TEST_BACKTEST_SYMBOL)
        period = period or getattr(config, 'BACKTEST_PERIOD', '60d')
        df_h1 = fetch_data_yfinance(symbol, period=period, interval='1h')
    if df_h1.index.tz is not None:
        df_h1.index = df_h1.index.tz_convert(None)
    strat = TestStrategy(df_h1, verbose=False)
    df_h1_processed, _ = strat.prepare_data()
    strat.df_h1 = df_h1_processed
    signals = strat.run_backtest()

    def _valid_sl(trade):
        sl, price = trade.get('sl'), trade.get('price')
        if sl is None or price is None:
            return False
        try:
            sl_f, price_f = float(sl), float(price)
        except (TypeError, ValueError):
            return False
        if trade['type'] == 'BUY' and sl_f >= price_f:
            return False
        if trade['type'] == 'SELL' and sl_f <= price_f:
            return False
        return True

    invalid_sl = signals[~signals.apply(_valid_sl, axis=1)]
    signals = signals[signals.apply(_valid_sl, axis=1)]
    if signals.empty:
        if return_stats:
            return _stats_dict("test", 0, 0, 0, 0.0, 0.0, config.INITIAL_BALANCE)
        used_symbol = symbol or getattr(config, 'TEST_BACKTEST_SYMBOL', TEST_BACKTEST_SYMBOL)
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
        print("| test              |      0 |    0 |      0 |     0.00% | $      100.00 |      0.00% |")
        print()
        print(f"Invalid SL (rejected, would fail in live): {len(invalid_sl)}")
        if not invalid_sl.empty:
            for _, row in invalid_sl.iterrows():
                print(f"  {row['type']} @ {row['price']:.2f} sl={row['sl']:.2f} ({row['time']})")
        return

    balance = config.INITIAL_BALANCE
    wins = 0
    losses = 0
    total_profit = 0.0
    total_loss = 0.0
    risk = getattr(config, 'RISK_REWARD_RATIO', 3.0)
    for _, trade in signals.iterrows():
        entry_price = trade['price']
        stop_loss = trade['sl']
        trade_time = trade['time']
        future_prices = df_h1.loc[df_h1.index > trade_time]
        if future_prices.empty:
            continue
        if trade['type'] == 'BUY':
            sl_dist = entry_price - stop_loss
            tp_price = trade.get('tp')
            if tp_price is None or tp_price <= entry_price:
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
            tp_price = trade.get('tp')
            if tp_price is None or tp_price >= entry_price:
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
            "test", wins + losses, wins, losses,
            total_profit, total_loss, balance,
        )
    used_symbol = symbol or getattr(config, 'TEST_BACKTEST_SYMBOL', TEST_BACKTEST_SYMBOL)
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
    print(f"| test              | {wins + losses:>5} | {wins:>4} | {losses:>6} | {win_rate:>8.2f}% | ${balance:>11,.2f} | {ret_str:>10} |")
    print()
    print(f"Invalid SL (rejected, would fail in live): {len(invalid_sl)}")
    if not invalid_sl.empty:
        for _, row in invalid_sl.iterrows():
            print(f"  {row['type']} @ {row['price']:.2f} sl={row['sl']:.2f} ({row['time']})")


if __name__ == "__main__":
    run_test_backtest()
