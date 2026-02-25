"""Backtest runner for Marvellous Strategy (XAUUSD gold, multi-TF bias + zone validation)."""
import pandas as pd
import config
from .. import marvellous_config as mc
from ..data_loader import fetch_data_yfinance, load_data_csv
from ..strategies import MarvellousStrategy
from .common import _stats_dict, get_pip_size_for_symbol, _apply_backtest_realism, _apply_gold_manual_sl_override, _calc_trade_pnl, _update_per_day_session


def _strip_tz(df):
    if df is None or df.empty:
        return df
    if df.index.tz is not None:
        df = df.copy()
        df.index = df.index.tz_convert(None)
    return df


def run_marvellous_backtest(
    csv_path=None,
    symbol=None,
    period=None,
    return_stats=False,
    include_trade_details=False,
    df_daily=None,
    df_4h=None,
    df_h1=None,
    df_m15=None,
    df_entry=None,
):
    """Run Marvellous backtest. Entry TF from config (5m, 15m, or 1m)."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    display_period = period or getattr(config, "BACKTEST_PERIOD", "60d")
    period_note = ""
    entry_tf = getattr(mc, "ENTRY_TIMEFRAME", "5m")

    if df_h1 is not None and df_m15 is not None and df_entry is not None:
        if df_daily is None:
            df_daily = df_h1.resample("1D").agg(agg).dropna()
        if df_4h is None:
            df_4h = df_h1.resample("4h").agg(agg).dropna()
    elif csv_path:
        df = load_data_csv(csv_path)
        df_h1 = df.resample("1h").agg(agg).dropna()
        df_4h = df_h1.resample("4h").agg(agg).dropna()
        df_daily = df_h1.resample("1D").agg(agg).dropna()
        df_m15 = df.resample("15min").agg(agg).dropna()
        if entry_tf == "15m":
            df_entry = df_m15.copy()
        else:
            resample_entry = "5min" if entry_tf == "5m" else "1min"
            df_entry = df.resample(resample_entry).agg(agg).dropna()
    else:
        symbol = symbol or getattr(mc, "MARVELLOUS_BACKTEST_SYMBOL", "GC=F")
        period = period or getattr(config, "BACKTEST_PERIOD", "60d")
        use_60d = period in ("6mo", "180d") or (
            isinstance(period, str) and ("mo" in period.lower() or "y" in period.lower())
        )
        if period == "1d":
            fetch_period = "1d"
        else:
            fetch_period = "7d" if entry_tf == "1m" else ("60d" if use_60d else period)
        
        period_note = f" (Yahoo 1m limit; {period} requested)" if entry_tf == "1m" and period not in ["1d", "7d"] else ""
        if use_60d and entry_tf != "1m":
            period_note = f" (Yahoo 15m limit; {period} requested)" if period != "60d" else ""
        display_period = fetch_period
        df_h1 = fetch_data_yfinance(symbol, period=fetch_period, interval="1h")
        df_4h = df_h1.resample("4h").agg(agg).dropna()
        df_daily = df_h1.resample("1D").agg(agg).dropna()
        df_m15 = fetch_data_yfinance(symbol, period=fetch_period, interval="15m")
        if entry_tf == "1m":
            df_entry = fetch_data_yfinance(symbol, period=fetch_period, interval="1m")
        elif entry_tf == "15m":
            df_entry = df_m15.copy()
        else:
            df_entry = fetch_data_yfinance(symbol, period=fetch_period, interval="5m")

    for d in (df_daily, df_4h, df_h1, df_m15, df_entry):
        if d is not None:
            _strip_tz(d)

    used_symbol = symbol or getattr(mc, "MARVELLOUS_BACKTEST_SYMBOL", "GC=F")
    strat = MarvellousStrategy(
        df_daily=df_daily,
        df_4h=df_4h,
        df_h1=df_h1,
        df_m15=df_m15,
        df_entry=df_entry,
        symbol=used_symbol,
        verbose=False,
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

    risk = getattr(config, "RISK_REWARD_RATIO", 5.0)
    lock_in_enabled = getattr(config, "LOCK_IN_ENABLED", True)
    lock_in_trigger = getattr(config, "LOCK_IN_TRIGGER_RR", 3.3)
    lock_in_at = getattr(config, "LOCK_IN_AT_RR", 3.0)

    if signals.empty:
        if return_stats:
            d = _stats_dict("marvellous", 0, 0, 0, 0.0, 0.0, config.INITIAL_BALANCE)
            d["buys"] = 0
            d["sells"] = 0
            if include_trade_details:
                d["trade_details"] = []
            return d
        print()
        print("Backtest Parameters:")
        print(f"  Asset: {used_symbol}")
        print(f"  Risk per trade: {config.RISK_PER_TRADE * 100:.0f}%")
        print(f"  Risk:Reward: 1:{risk}")
        print(f"  Entry TF: {entry_tf}")
        print(f"  Duration: {display_period}{period_note}")
        print()
        print("| Strategy   | Trades | Wins | Losses | Win rate  | Final balance | Return      |")
        print("| :----------| :----- | :--- | :----- | :-------- | :------------ | :---------- |")
        print("| marvellous |      0 |    0 |      0 |     0.00% | $      100.00 |      0.00% |")
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
    per_day = {}
    per_session = {}

    for _, trade in signals.iterrows():
        entry_price = trade["price"]
        stop_loss = trade["sl"]
        trade_time = trade["time"]
        adj_entry, adj_sl, commission = _apply_backtest_realism(
            entry_price, stop_loss, trade["type"], used_symbol, entry_price
        )
        adj_sl = _apply_gold_manual_sl_override(used_symbol, adj_entry, adj_sl, trade["type"])
        spread_cost = abs(adj_entry - entry_price)
        future_prices = df_entry.loc[df_entry.index > trade_time]
        if future_prices.empty:
            continue
        if trade["type"] == "BUY":
            sl_dist = adj_entry - adj_sl
            tp_price = trade.get("tp")
            if tp_price is None or tp_price <= adj_entry:
                tp_price = adj_entry + (sl_dist * risk)
            lock_in_sl = adj_entry + (sl_dist * lock_in_at) if lock_in_enabled else None
            lock_in_trigger_price = adj_entry + (sl_dist * lock_in_trigger) if lock_in_enabled else None
            outcome = None
            outcome_rr = risk
            lock_in_triggered = False
            for idx, bar in future_prices.iterrows():
                if lock_in_enabled and lock_in_trigger_price and lock_in_sl and bar["high"] >= lock_in_trigger_price:
                    lock_in_triggered = True
                effective_sl = lock_in_sl if lock_in_triggered else adj_sl
                if bar["low"] <= effective_sl:
                    outcome = "LOSS" if effective_sl == adj_sl else "WIN"
                    outcome_rr = 0.0 if outcome == "LOSS" else lock_in_at
                    break
                if bar["high"] >= tp_price:
                    outcome = "WIN"
                    outcome_rr = risk
                    break
            if outcome == "WIN":
                profit = _calc_trade_pnl(used_symbol, balance, config.RISK_PER_TRADE, sl_dist, "WIN", outcome_rr, spread_cost)
                total_profit += profit
                balance += profit
                wins += 1
                buys += 1
                _update_per_day_session(trade_time, per_day, per_session)
                if trade_details is not None:
                    trade_details.append((trade_time, "WIN"))
            elif outcome == "LOSS":
                loss = _calc_trade_pnl(used_symbol, balance, config.RISK_PER_TRADE, sl_dist, "LOSS", 0, spread_cost)
                total_loss += loss
                balance -= loss
                losses += 1
                buys += 1
                _update_per_day_session(trade_time, per_day, per_session)
                if trade_details is not None:
                    trade_details.append((trade_time, "LOSS"))
        elif trade["type"] == "SELL":
            sl_dist = adj_sl - adj_entry
            tp_price = trade.get("tp")
            if tp_price is None or tp_price >= adj_entry:
                tp_price = adj_entry - (sl_dist * risk)
            lock_in_sl = adj_entry - (sl_dist * lock_in_at) if lock_in_enabled else None
            lock_in_trigger_price = adj_entry - (sl_dist * lock_in_trigger) if lock_in_enabled else None
            outcome = None
            outcome_rr = risk
            lock_in_triggered = False
            for idx, bar in future_prices.iterrows():
                if lock_in_enabled and lock_in_trigger_price and lock_in_sl and bar["low"] <= lock_in_trigger_price:
                    lock_in_triggered = True
                effective_sl = lock_in_sl if lock_in_triggered else adj_sl
                if bar["high"] >= effective_sl:
                    outcome = "LOSS" if effective_sl == adj_sl else "WIN"
                    outcome_rr = 0.0 if outcome == "LOSS" else lock_in_at
                    break
                if bar["low"] <= tp_price:
                    outcome = "WIN"
                    outcome_rr = risk
                    break
            if outcome == "WIN":
                profit = _calc_trade_pnl(used_symbol, balance, config.RISK_PER_TRADE, sl_dist, "WIN", outcome_rr, spread_cost)
                total_profit += profit
                balance += profit
                wins += 1
                sells += 1
                _update_per_day_session(trade_time, per_day, per_session)
                if trade_details is not None:
                    trade_details.append((trade_time, "WIN"))
            elif outcome == "LOSS":
                loss = _calc_trade_pnl(used_symbol, balance, config.RISK_PER_TRADE, sl_dist, "LOSS", 0, spread_cost)
                total_loss += loss
                balance -= loss
                losses += 1
                sells += 1
                _update_per_day_session(trade_time, per_day, per_session)
                if trade_details is not None:
                    trade_details.append((trade_time, "LOSS"))

    if return_stats:
        d = _stats_dict(
            "marvellous", wins + losses, wins, losses, total_profit, total_loss, balance
        )
        d["buys"] = buys
        d["sells"] = sells
        if include_trade_details:
            d["trade_details"] = trade_details or []
        return d

    trade_limit = getattr(config, "BACKTEST_MAX_TRADES", None)
    trade_limit_str = "No trade limit" if trade_limit is None else str(trade_limit)
    apply_limits = getattr(config, "BACKTEST_APPLY_TRADE_LIMITS", False)
    max_day = getattr(config, "BACKTEST_MAX_TRADES_PER_DAY", config.MAX_TRADES_PER_DAY)
    max_sess = getattr(config, "BACKTEST_MAX_TRADES_PER_SESSION", config.MAX_TRADES_PER_SESSION)
    limits_str = f"{max_day}/day, {max_sess}/session" if apply_limits else "No"
    return_pct = ((balance - config.INITIAL_BALANCE) / config.INITIAL_BALANCE) * 100
    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
    print()
    print("Backtest Parameters:")
    print(f"  Asset: {used_symbol}")
    print(f"  Risk per trade: {config.RISK_PER_TRADE * 100:.0f}%")
    print(f"  Risk:Reward: 1:{risk}")
    print(f"  Entry TF: {entry_tf}")
    print(f"  Trade Limit: {trade_limit_str}")
    print(f"  Daily/Session limits: {limits_str}")
    print(f"  Duration: {display_period}{period_note}")
    print()
    print("| Strategy   | Trades | Wins | Losses | Win rate  | Final balance | Return      |")
    print("| :----------| :----- | :--- | :----- | :-------- | :------------ | :---------- |")
    ret_str = f"{'+' if return_pct >= 0 else ''}{return_pct:,.2f}%"
    print(f"| marvellous | {wins + losses:>5} | {wins:>4} | {losses:>6} | {win_rate:>8.2f}% | ${balance:>11,.2f} | {ret_str:>10} |")
    print()
    print(f"  BUY: {buys} | SELL: {sells}")
    if per_day or per_session:
        day_str = " | ".join(f"{d}: {c}" for d, c in sorted(per_day.items())) if per_day else "—"
        sess_str = " | ".join(f"{s}: {c}" for s, c in sorted(per_session.items())) if per_session else "—"
        print(f"  Trades per day:     {day_str}")
        print(f"  Trades per session: {sess_str}")
    print()
    if len(invalid_sl) > 0:
        print(f"Invalid SL (rejected): {len(invalid_sl)}")


if __name__ == "__main__":
    run_marvellous_backtest()
