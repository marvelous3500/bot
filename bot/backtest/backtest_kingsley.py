"""Backtest runner for Kingsley Gold strategy (H1 + 15m, gold only)."""
import pandas as pd
import config
from ..data_loader import fetch_data_yfinance, load_data_csv
from ..strategies import KingsleyGoldStrategy
from .common import _stats_dict, get_pip_size_for_symbol, _apply_backtest_realism

# Gold symbols: Yahoo uses GC=F, MT5 uses XAUUSD
KINGSLEY_BACKTEST_SYMBOL = 'GC=F'
KINGSLEY_LIVE_SYMBOL = 'XAUUSD'


def run_kingsley_backtest(csv_path=None, symbol=None, period=None, return_stats=False, include_trade_details=False, df_4h=None, df_h1=None, df_15m=None, df_daily=None):
    """Run Kingsley backtest. Pass df_4h, df_h1, df_15m, df_daily to reuse data (for sweeps)."""
    agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
    display_period = period or getattr(config, 'BACKTEST_PERIOD', '60d')
    period_note = ""
    # Reuse pre-fetched data (for parameter sweeps)
    if df_4h is not None and df_h1 is not None and df_15m is not None:
        if df_daily is None:
            df_daily = df_h1.resample('1D').agg(agg).dropna()
    elif csv_path:
        df = load_data_csv(csv_path)
        df_h1 = df.resample('1h').agg(agg).dropna()
        df_4h = df_h1.resample('4h').agg(agg).dropna()
        df_15m = df.resample('15min').agg(agg).dropna()
        df_daily = df_h1.resample('1D').agg(agg).dropna()
    else:
        symbol = symbol or getattr(config, 'KINGSLEY_BACKTEST_SYMBOL', KINGSLEY_BACKTEST_SYMBOL)
        period = period or getattr(config, 'BACKTEST_PERIOD', '60d')
        # Yahoo limits 15m to last 60 days; for 6mo+ use 60d and warn
        use_60d = period in ('6mo', '180d') or (isinstance(period, str) and ('mo' in period.lower() or 'y' in period.lower()))
        fetch_period = '60d' if use_60d else period
        period_note = f" (Yahoo 15m limit; {period} requested)" if use_60d and period != '60d' else ""
        display_period = fetch_period
        df_h1 = fetch_data_yfinance(symbol, period=fetch_period, interval='1h')
        df_4h = df_h1.resample('4h').agg(agg).dropna()
        df_15m = fetch_data_yfinance(symbol, period=fetch_period, interval='15m')
        df_daily = df_h1.resample('1D').agg(agg).dropna()
    if df_4h.index.tz is not None:
        df_4h.index = df_4h.index.tz_convert(None)
    if df_h1.index.tz is not None:
        df_h1.index = df_h1.index.tz_convert(None)
    if df_15m.index.tz is not None:
        df_15m.index = df_15m.index.tz_convert(None)
    if df_daily.index.tz is not None:
        df_daily.index = df_daily.index.tz_convert(None)
    strat = KingsleyGoldStrategy(df_4h, df_h1, df_15m, df_daily=df_daily, verbose=False)
    df_4h_processed, df_h1_processed, df_15m_processed = strat.prepare_data()
    strat.df_4h = df_4h_processed
    strat.df_h1 = df_h1_processed
    strat.df_15m = df_15m_processed
    signals = strat.run_backtest()
    # Validate SL (same as live): BUY needs sl < price, SELL needs sl > price
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
    risk = getattr(config, 'RISK_REWARD_RATIO', 3.0)
    if signals.empty:
        if return_stats:
            d = _stats_dict("kingsely_gold", 0, 0, 0, 0.0, 0.0, config.INITIAL_BALANCE)
            if include_trade_details:
                d["trade_details"] = []
            return d
        used_symbol = symbol or getattr(config, 'KINGSLEY_BACKTEST_SYMBOL', KINGSLEY_BACKTEST_SYMBOL)
        print()
        print("Backtest Parameters:")
        print(f"  Asset: {used_symbol}")
        print(f"  Risk per trade: {config.RISK_PER_TRADE * 100:.0f}%")
        print(f"  Risk:Reward: 1:{risk}")
        print(f"  Trade Limit: {'No trade limit' if getattr(config, 'BACKTEST_MAX_TRADES', None) is None else config.BACKTEST_MAX_TRADES}")
        print(f"  Duration: {display_period}{period_note}")
        print()
        print("| Strategy          | Trades | Wins | Losses | Win rate  | Final balance | Return      |")
        print("| :---------------- | :----- | :--- | :----- | :-------- | :------------ | :---------- |")
        print("| kingsely_gold     |      0 |    0 |      0 |     0.00% | $      100.00 |      0.00% |")
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
    trade_details = [] if include_trade_details else None
    used_symbol = symbol or getattr(config, 'KINGSLEY_BACKTEST_SYMBOL', KINGSLEY_BACKTEST_SYMBOL)
    for _, trade in signals.iterrows():
        entry_price = trade['price']
        stop_loss = trade['sl']
        trade_time = trade['time']
        adj_entry, adj_sl, commission = _apply_backtest_realism(
            entry_price, stop_loss, trade['type'], used_symbol, entry_price
        )
        spread_cost = abs(adj_entry - entry_price)
        future_prices = df_15m.loc[df_15m.index > trade_time]
        if future_prices.empty:
            continue
        if trade['type'] == 'BUY':
            sl_dist = adj_entry - adj_sl
            tp_price = trade.get('tp')
            if tp_price is None or tp_price <= adj_entry:
                tp_price = adj_entry + (sl_dist * risk)
            outcome = None
            for idx, bar in future_prices.iterrows():
                if bar['low'] <= adj_sl:
                    outcome = 'LOSS'
                    break
                if bar['high'] >= tp_price:
                    outcome = 'WIN'
                    break
            if outcome == 'WIN':
                profit = (balance * config.RISK_PER_TRADE) * risk - spread_cost - commission
                total_profit += profit
                balance += profit
                wins += 1
                if trade_details is not None:
                    trade_details.append((trade_time, 'WIN'))
            elif outcome == 'LOSS':
                loss = (balance * config.RISK_PER_TRADE) + spread_cost + commission
                total_loss += loss
                balance -= loss
                losses += 1
                if trade_details is not None:
                    trade_details.append((trade_time, 'LOSS'))
        elif trade['type'] == 'SELL':
            sl_dist = adj_sl - adj_entry
            tp_price = trade.get('tp')
            if tp_price is None or tp_price >= adj_entry:
                tp_price = adj_entry - (sl_dist * risk)
            outcome = None
            for idx, bar in future_prices.iterrows():
                if bar['high'] >= adj_sl:
                    outcome = 'LOSS'
                    break
                if bar['low'] <= tp_price:
                    outcome = 'WIN'
                    break
            if outcome == 'WIN':
                profit = (balance * config.RISK_PER_TRADE) * risk - spread_cost - commission
                total_profit += profit
                balance += profit
                wins += 1
                if trade_details is not None:
                    trade_details.append((trade_time, 'WIN'))
            elif outcome == 'LOSS':
                loss = (balance * config.RISK_PER_TRADE) + spread_cost + commission
                total_loss += loss
                balance -= loss
                losses += 1
                if trade_details is not None:
                    trade_details.append((trade_time, 'LOSS'))
    if return_stats:
        d = _stats_dict(
            "kingsely_gold", wins + losses, wins, losses,
            total_profit, total_loss, balance,
        )
        if include_trade_details:
            d["trade_details"] = trade_details or []
        return d
    # Display in image format: parameters + table
    used_symbol = symbol or getattr(config, 'KINGSLEY_BACKTEST_SYMBOL', KINGSLEY_BACKTEST_SYMBOL)
    trade_limit = getattr(config, 'BACKTEST_MAX_TRADES', None)
    trade_limit_str = "No trade limit" if trade_limit is None else str(trade_limit)
    risk_pct = config.RISK_PER_TRADE * 100
    return_pct = ((balance - config.INITIAL_BALANCE) / config.INITIAL_BALANCE) * 100
    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
    print()
    print("Backtest Parameters:")
    print(f"  Asset: {used_symbol}")
    print(f"  Risk per trade: {risk_pct:.0f}%")
    print(f"  Risk:Reward: 1:{risk}")
    print(f"  Trade Limit: {trade_limit_str}")
    print(f"  Duration: {display_period}{period_note}")
    print()
    print("| Strategy          | Trades | Wins | Losses | Win rate  | Final balance | Return      |")
    print("| :---------------- | :----- | :--- | :----- | :-------- | :------------ | :---------- |")
    ret_str = f"{'+' if return_pct >= 0 else ''}{return_pct:,.2f}%"
    print(f"| kingsely_gold     | {wins + losses:>5} | {wins:>4} | {losses:>6} | {win_rate:>8.2f}% | ${balance:>11,.2f} | {ret_str:>10} |")
    print()
    print(f"Invalid SL (rejected, would fail in live): {len(invalid_sl)}")
    if not invalid_sl.empty:
        for _, row in invalid_sl.iterrows():
            print(f"  {row['type']} @ {row['price']:.2f} sl={row['sl']:.2f} ({row['time']})")

if __name__ == "__main__":
    run_kingsley_backtest()
