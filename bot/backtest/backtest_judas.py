"""Backtest runner for NAS Judas Strategy (NAS100)."""
import pandas as pd
import config
from .. import judas_config as jc
from ..data_loader import fetch_data_yfinance, load_data_csv
from ..strategies import JudasStrategy
from .common import _stats_dict, _apply_backtest_realism


def _strip_tz(df):
    if df is None or df.empty:
        return df
    if df.index.tz is not None:
        df = df.copy()
        df.index = df.index.tz_convert(None)
    return df


def run_judas_backtest(
    csv_path=None,
    symbol=None,
    period=None,
    return_stats=False,
    include_trade_details=False,
    df_h1=None,
    df_m15=None,
):
    """Run NAS Judas Strategy backtest. Uses H1 bias, M15 entry."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    display_period = period or getattr(config, "BACKTEST_PERIOD", "60d")
    period_note = ""

    if df_h1 is not None and df_m15 is not None:
        pass
    elif csv_path:
        df = load_data_csv(csv_path)
        df_h1 = df.resample("1h").agg(agg).dropna()
        df_m15 = df.resample("15min").agg(agg).dropna()
    else:
        symbol = symbol or getattr(jc, "BACKTEST_SYMBOL", "^NDX")
        period = period or getattr(config, "BACKTEST_PERIOD", "60d")
        use_60d = period in ("6mo", "180d") or (
            isinstance(period, str) and ("mo" in period.lower() or "y" in period.lower())
        )
        fetch_period = "60d" if use_60d else period
        period_note = f" (Yahoo 15m limit; {period} requested)" if use_60d and period != "60d" else ""
        display_period = fetch_period
        df_h1 = fetch_data_yfinance(symbol, period=fetch_period, interval="1h")
        df_m15 = fetch_data_yfinance(symbol, period=fetch_period, interval="15m")

    for d in (df_h1, df_m15):
        if d is not None:
            _strip_tz(d)

    used_symbol = symbol or getattr(jc, "BACKTEST_SYMBOL", "^NDX")
    strat = JudasStrategy(
        df_h1=df_h1,
        df_m15=df_m15,
        symbol=used_symbol,
        verbose=getattr(jc, "VERBOSE", False),
    )
    strat.prepare_data()
    signals = strat.run_backtest()

    def _valid_sl(trade):
        sl, price = trade.get("sl"), trade.get("price")
        if sl is None or price is None:
            return False
        try:
            sl_f, price_f = float(sl), float(price)
        except (TypeError, ValueError):
            return False
        if trade["type"] == "BUY" and sl_f >= price_f:
            return False
        if trade["type"] == "SELL" and sl_f <= price_f:
            return False
        return True

    invalid_sl = signals[~signals.apply(_valid_sl, axis=1)] if not signals.empty else pd.DataFrame()
    signals = signals[signals.apply(_valid_sl, axis=1)] if not signals.empty else pd.DataFrame()

    risk = jc.RISK_PER_TRADE * 100
    rr = getattr(config, "RISK_REWARD_RATIO", 3.0)

    if signals.empty:
        if return_stats:
            d = _stats_dict("judas", 0, 0, 0, 0.0, 0.0, config.INITIAL_BALANCE)
            d["buys"] = 0
            d["sells"] = 0
            if include_trade_details:
                d["trade_details"] = []
            return d
        print()
        print("Backtest Parameters:")
        print(f"  Asset: {used_symbol}")
        print(f"  Risk per trade: {risk}%")
        print(f"  Risk:Reward: 1:{rr}")
        print(f"  Duration: {display_period}{period_note}")
        print()
        print("| Strategy | Trades | Wins | Losses | Win rate  | Final balance | Return      |")
        print("| :------- | :----- | :--- | :----- | :-------- | :------------ | :---------- |")
        print("| judas    |      0 |    0 |      0 |     0.00% | $      100.00 |      0.00% |")
        print()
        return

    balance = config.INITIAL_BALANCE
    wins = 0
    losses = 0
    buys = 0
    sells = 0
    total_profit = 0.0
    total_loss = 0.0
    trade_details = [] if include_trade_details else None

    for _, trade in signals.iterrows():
        entry_price = trade["price"]
        stop_loss = trade["sl"]
        trade_time = trade["time"]
        adj_entry, adj_sl, commission = _apply_backtest_realism(
            entry_price, stop_loss, trade["type"], used_symbol, entry_price
        )
        spread_cost = abs(adj_entry - entry_price)
        future_prices = df_m15.loc[df_m15.index > trade_time]
        if future_prices.empty:
            continue
        sl_dist = abs(adj_entry - adj_sl)
        tp_price = trade.get("tp")
        if trade["type"] == "BUY":
            if tp_price is None or tp_price <= adj_entry:
                tp_price = adj_entry + (sl_dist * rr)
            outcome = None
            for idx, bar in future_prices.iterrows():
                if bar["low"] <= adj_sl:
                    outcome = "LOSS"
                    break
                if bar["high"] >= tp_price:
                    outcome = "WIN"
                    break
            if outcome == "WIN":
                profit = (balance * jc.RISK_PER_TRADE) * rr - spread_cost - commission
                total_profit += profit
                balance += profit
                wins += 1
                buys += 1
                if trade_details is not None:
                    trade_details.append((trade_time, "WIN"))
            elif outcome == "LOSS":
                loss = (balance * jc.RISK_PER_TRADE) + spread_cost + commission
                total_loss += loss
                balance -= loss
                losses += 1
                buys += 1
                if trade_details is not None:
                    trade_details.append((trade_time, "LOSS"))
        else:
            if tp_price is None or tp_price >= adj_entry:
                tp_price = adj_entry - (sl_dist * rr)
            outcome = None
            for idx, bar in future_prices.iterrows():
                if bar["high"] >= adj_sl:
                    outcome = "LOSS"
                    break
                if bar["low"] <= tp_price:
                    outcome = "WIN"
                    break
            if outcome == "WIN":
                profit = (balance * jc.RISK_PER_TRADE) * rr - spread_cost - commission
                total_profit += profit
                balance += profit
                wins += 1
                sells += 1
                if trade_details is not None:
                    trade_details.append((trade_time, "WIN"))
            elif outcome == "LOSS":
                loss = (balance * jc.RISK_PER_TRADE) + spread_cost + commission
                total_loss += loss
                balance -= loss
                losses += 1
                sells += 1
                if trade_details is not None:
                    trade_details.append((trade_time, "LOSS"))

    if return_stats:
        d = _stats_dict("judas", wins + losses, wins, losses, total_profit, total_loss, balance)
        d["buys"] = buys
        d["sells"] = sells
        if include_trade_details:
            d["trade_details"] = trade_details or []
        return d

    trade_limit = getattr(config, "BACKTEST_MAX_TRADES", None)
    trade_limit_str = "No trade limit" if trade_limit is None else str(trade_limit)
    return_pct = ((balance - config.INITIAL_BALANCE) / config.INITIAL_BALANCE) * 100
    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
    print()
    print("Backtest Parameters:")
    print(f"  Asset: {used_symbol}")
    print(f"  Risk per trade: {risk}%")
    print(f"  Risk:Reward: 1:{rr}")
    print(f"  Trade Limit: {trade_limit_str}")
    print(f"  Duration: {display_period}{period_note}")
    print()
    print("| Strategy | Trades | Wins | Losses | Win rate  | Final balance | Return      |")
    print("| :------- | :----- | :--- | :----- | :-------- | :------------ | :---------- |")
    ret_str = f"{'+' if return_pct >= 0 else ''}{return_pct:,.2f}%"
    print(f"| judas    | {wins + losses:>5} | {wins:>4} | {losses:>6} | {win_rate:>8.2f}% | ${balance:>11,.2f} | {ret_str:>10} |")
    print()
    print(f"  BUY: {buys} | SELL: {sells}")
    print()
    if len(invalid_sl) > 0:
        print(f"Invalid SL (rejected): {len(invalid_sl)}")


if __name__ == "__main__":
    run_judas_backtest()
