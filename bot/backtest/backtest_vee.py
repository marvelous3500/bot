"""
Backtest runner for VeeStrategy (1H bias -> 15M setup -> 1M entry).
"""

import pandas as pd

import config
from .. import vee_config as vc
from ..data_loader import fetch_data_yfinance, load_data_csv
from ..strategies import VeeStrategy
from .common import (
    _stats_dict,
    _apply_backtest_realism,
    _apply_gold_manual_sl_override,
    _calc_trade_pnl,
    _update_per_day_session,
)


def _strip_tz(df):
    if df is None or df.empty:
        return df
    if df.index.tz is not None:
        df = df.copy()
        df.index = df.index.tz_convert(None)
    return df


def run_vee_backtest(
    csv_path=None,
    symbol=None,
    period=None,
    return_stats=False,
    include_trade_details=False,
    df_h1=None,
    df_m15=None,
    df_m1=None,
):
    """Run Vee backtest: 1H, 15M, 1M."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    display_period = period or getattr(config, "BACKTEST_PERIOD", "60d")

    if df_h1 is not None and df_m15 is not None and df_m1 is not None:
        pass
    elif csv_path:
        df = load_data_csv(csv_path)
        df_h1 = df.resample("1h").agg(agg).dropna()
        df_m15 = df.resample("15min").agg(agg).dropna()
        df_m1 = df.resample("1min").agg(agg).dropna()
    else:
        symbol = symbol or getattr(config, "VEE_BACKTEST_SYMBOL", vc.VEE_BACKTEST_SYMBOL)
        # Yahoo 1m limit: use 7d window
        fetch_period = "7d" if period not in ("1d", "7d") else period
        display_period = fetch_period
        df_h1 = fetch_data_yfinance(symbol, period=fetch_period, interval="1h")
        df_m15 = fetch_data_yfinance(symbol, period=fetch_period, interval="15m")
        df_m1 = fetch_data_yfinance(symbol, period=fetch_period, interval="1m")

    for d in (df_h1, df_m15, df_m1):
        if d is not None:
            _strip_tz(d)

    used_symbol = symbol or getattr(config, "VEE_BACKTEST_SYMBOL", vc.VEE_BACKTEST_SYMBOL)
    strat = VeeStrategy(
        df_h1=df_h1,
        df_m15=df_m15,
        df_m1=df_m1,
        symbol=used_symbol,
        verbose=False,
    )
    signals = strat.run_backtest()

    if signals.empty:
        if return_stats:
            return _stats_dict("vee", 0, 0, 0, 0.0, 0.0, config.INITIAL_BALANCE)
        print()
        print(f"Backtest Results (vee) on {used_symbol}:")
        print("| Strategy | Trades | Wins | Losses | Win rate  | Final balance | Return      |")
        print("| :------- | :----- | :--- | :----- | :-------- | :------------ | :---------- |")
        print("| vee      |      0 |    0 |      0 |     0.00% | $      100.00 |      0.00% |")
        return

    risk_pct = getattr(config, "VEE_RISK_PER_TRADE", vc.RISK_PER_TRADE)
    risk_rr = getattr(config, "VEE_MIN_RR", vc.MIN_RR)

    balance = config.INITIAL_BALANCE
    wins = 0
    losses = 0
    total_profit = 0.0
    total_loss = 0.0
    per_day = {}
    per_session = {}
    trade_details = [] if include_trade_details else None

    for _, trade in signals.iterrows():
        entry_price = trade["price"]
        stop_loss = trade["sl"]
        trade_time = trade["time"]

        adj_entry, adj_sl, _ = _apply_backtest_realism(
            entry_price, stop_loss, trade["type"], used_symbol, entry_price
        )
        adj_sl = _apply_gold_manual_sl_override(used_symbol, adj_entry, adj_sl, trade["type"])
        spread_cost = abs(adj_entry - entry_price)

        future_prices = df_m1.loc[df_m1.index > trade_time]
        if future_prices.empty:
            continue

        sl_dist = abs(adj_entry - adj_sl)
        tp_price = trade["tp"]
        if trade["type"] == "BUY":
            if tp_price is None or tp_price <= adj_entry:
                tp_price = adj_entry + sl_dist * risk_rr
        else:
            if tp_price is None or tp_price >= adj_entry:
                tp_price = adj_entry - sl_dist * risk_rr

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
            profit = _calc_trade_pnl(used_symbol, balance, risk_pct, sl_dist, "WIN", risk_rr, spread_cost)
            total_profit += profit
            balance += profit
            wins += 1
        elif outcome == "LOSS":
            loss = _calc_trade_pnl(used_symbol, balance, risk_pct, sl_dist, "LOSS", 0, spread_cost)
            total_loss += loss
            balance -= loss
            losses += 1

        _update_per_day_session(trade_time, per_day, per_session)
        if trade_details is not None:
            trade_details.append((trade_time, outcome, entry_price, stop_loss, tp_price, trade.get("reason", "")))

    if return_stats:
        res = _stats_dict("vee", wins + losses, wins, losses, total_profit, total_loss, balance)
        if include_trade_details:
            res["trade_details"] = trade_details or []
        return res

    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
    return_pct = ((balance - config.INITIAL_BALANCE) / config.INITIAL_BALANCE) * 100
    print()
    print(f"Backtest Results (vee) on {used_symbol}:")
    print("| Strategy | Trades | Wins | Losses | Win rate  | Final balance | Return      |")
    print("| :------- | :----- | :--- | :----- | :-------- | :------------ | :---------- |")
    ret_str = f"{'+' if return_pct >= 0 else ''}{return_pct:,.2f}%"
    print(f"| vee      | {wins+losses:>6} | {wins:>4} | {losses:>6} | {win_rate:>8.2f}% | ${balance:>11,.2f} | {ret_str:>10} |")
    print()

