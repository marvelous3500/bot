"""
Backtest runner for V1 Strategy (H1 Bias -> 5M Confirmation).
"""
import pandas as pd
import config
from .. import v1_config as vc
from ..data_loader import fetch_data_yfinance, load_data_csv
from ..strategies import V1Strategy
from .common import _stats_dict, _apply_backtest_realism, _apply_gold_manual_sl_override, _calc_trade_pnl, _update_per_day_session


def _strip_tz(df):
    if df is None or df.empty:
        return df
    if df.index.tz is not None:
        df = df.copy()
        df.index = df.index.tz_convert(None)
    return df


def run_v1_backtest(
    csv_path=None,
    symbol=None,
    period=None,
    return_stats=False,
    include_trade_details=False,
    df_h1=None,
    df_m5=None,
    daily_df=None,
):
    """Run V1 backtest using H1 bias + 5M confirmation."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    display_period = period or getattr(config, "BACKTEST_PERIOD", "60d")

    if df_h1 is not None and df_m5 is not None:
        pass
    elif csv_path:
        df = load_data_csv(csv_path)
        df_h1 = df.resample("1h").agg(agg).dropna()
        df_m5 = df.resample("5min").agg(agg).dropna()
        daily_df = df.resample("1D").agg(agg).dropna()
    else:
        symbol = symbol or getattr(config, "V1_BACKTEST_SYMBOL", vc.V1_BACKTEST_SYMBOL)
        period = period or getattr(config, "BACKTEST_PERIOD", "60d")
        # Yahoo Finance: 5m data limited to 60 days
        fetch_period = period if period != "both" else "60d"
        if fetch_period not in ["1d", "7d"] and fetch_period != "60d":
            fetch_period = "7d"  # Safe default for 5m

        df_h1 = fetch_data_yfinance(symbol, period=fetch_period, interval="1h")
        df_m5 = fetch_data_yfinance(symbol, period=fetch_period, interval="5m")
        daily_df = fetch_data_yfinance(symbol, period=fetch_period, interval="1d")

    # Ensure all dataframes have timezone-naive indices (backtest convention)
    df_h1 = _strip_tz(df_h1)
    df_m5 = _strip_tz(df_m5)
    daily_df = _strip_tz(daily_df)

    used_symbol = symbol or getattr(config, "V1_BACKTEST_SYMBOL", vc.V1_BACKTEST_SYMBOL)
    strat = V1Strategy(
        df_h1=df_h1,
        df_m5=df_m5,
        daily_df=daily_df,
        symbol=used_symbol,
        verbose=False,
    )

    signals = strat.run_backtest()

    risk_pct = getattr(config, "V1_RISK_PER_TRADE", vc.V1_RISK_PER_TRADE)
    risk_reward = getattr(config, "V1_MIN_RR", vc.V1_MIN_RR)

    if signals.empty:
        if return_stats:
            return _stats_dict("v1", 0, 0, 0, 0.0, 0.0, config.INITIAL_BALANCE)
        print(f"\nNo signals for v1 on {used_symbol} over {display_period}")
        return

    balance = config.INITIAL_BALANCE
    wins = 0
    losses = 0
    total_profit = 0.0
    total_loss = 0.0
    per_day = {}
    per_session = {}
    trade_details = []

    for _, trade in signals.iterrows():
        entry_price = trade["price"]
        stop_loss = trade["sl"]
        trade_time = trade["time"]

        adj_entry, adj_sl, _ = _apply_backtest_realism(entry_price, stop_loss, trade["type"], used_symbol, entry_price)
        adj_sl = _apply_gold_manual_sl_override(used_symbol, adj_entry, adj_sl, trade["type"])
        spread_cost = abs(adj_entry - entry_price)

        future_prices = df_m5.loc[df_m5.index > trade_time]
        if future_prices.empty:
            continue

        sl_dist = abs(adj_entry - adj_sl)
        tp_price = trade["tp"]
        outcome = None

        for idx, bar in future_prices.iterrows():
            if trade["type"] == "BUY":
                if bar["low"] <= adj_sl:
                    outcome = "LOSS"
                    break
                if bar["high"] >= tp_price:
                    outcome = "WIN"
                    break
            else:
                if bar["high"] >= adj_sl:
                    outcome = "LOSS"
                    break
                if bar["low"] <= tp_price:
                    outcome = "WIN"
                    break

        if outcome == "WIN":
            profit = _calc_trade_pnl(used_symbol, balance, risk_pct, sl_dist, "WIN", risk_reward, spread_cost)
            total_profit += profit
            balance += profit
            wins += 1
        elif outcome == "LOSS":
            loss = _calc_trade_pnl(used_symbol, balance, risk_pct, sl_dist, "LOSS", 0, spread_cost)
            total_loss += loss
            balance -= loss
            losses += 1

        _update_per_day_session(trade_time, per_day, per_session)
        if include_trade_details:
            trade_details.append((trade_time, outcome, entry_price, stop_loss, tp_price, trade.get("reason", "")))

    if return_stats:
        res = _stats_dict("v1", wins + losses, wins, losses, total_profit, total_loss, balance)
        if include_trade_details:
            res["trade_details"] = trade_details
        return res

    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
    return_pct = ((balance - config.INITIAL_BALANCE) / config.INITIAL_BALANCE) * 100

    print(f"\nBacktest Results (v1) on {used_symbol}:")
    print(f"| Strategy | Trades | Wins | Losses | Win rate  | Final balance | Return      |")
    print(f"| :------- | :----- | :--- | :----- | :-------- | :------------ | :---------- |")
    ret_str = f"{'+' if return_pct >= 0 else ''}{return_pct:,.2f}%"
    print(f"| v1       | {wins+losses:>6} | {wins:>4} | {losses:>6} | {win_rate:>8.2f}% | ${balance:>11,.2f} | {ret_str:>10} |")
    print()
