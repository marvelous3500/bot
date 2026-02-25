"""
Backtest runner for LQStrategy (liquidity sweep: PDH/PDL + session LQ).
Uses M15 data for entry. Requires daily data for PDH/PDL.

Example: python main.py --mode backtest --strategy lq --symbol GC=F
"""
import pandas as pd
import config
from ..data_loader import fetch_data_yfinance, fetch_daily_data_yfinance, load_data_csv
from ..strategies import LQStrategy
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
    if hasattr(df.index, 'tz') and df.index.tz is not None:
        df = df.copy()
        df.index = df.index.tz_localize(None)
    return df


def run_lq_backtest(
    csv_path=None,
    symbol=None,
    period=None,
    return_stats=False,
    include_trade_details=False,
    df_daily=None,
    df_m15=None,
    df_m1=None,
):
    """Run LQ backtest. Uses daily + M15. M1 needed when LQ_USE_VESTER_ENTRY=True."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    display_period = period or getattr(config, "BACKTEST_PERIOD", "60d")
    used_symbol = symbol or getattr(config, "VESTER_BACKTEST_SYMBOL", "GC=F")
    period = period or getattr(config, "BACKTEST_PERIOD", "60d")
    use_vester_entry = getattr(config, "LQ_USE_VESTER_ENTRY", False)

    if df_m15 is not None and df_daily is not None:
        pass
    elif csv_path:
        df = load_data_csv(csv_path)
        if 'volume' not in df.columns:
            df['volume'] = 0
        df_m15 = df.resample("15min").agg(agg).dropna()
        df_daily = df.resample("1D").agg(agg).dropna()
        if use_vester_entry and df_m1 is None:
            try:
                df_m1 = df.resample("1min").agg(agg).dropna()
            except Exception:
                pass
    else:
        df_daily = fetch_daily_data_yfinance(used_symbol, period=period)
        try:
            df_m15 = fetch_data_yfinance(used_symbol, period=period, interval="15m")
        except Exception:
            df_m5 = fetch_data_yfinance(used_symbol, period=period, interval="5m")
            df_m15 = df_m5.resample("15min").agg(agg).dropna()
        df_daily = _strip_tz(df_daily)
        df_m15 = _strip_tz(df_m15)
        if use_vester_entry and df_m1 is None:
            try:
                fetch_1m_period = "7d"
                df_m1 = fetch_data_yfinance(used_symbol, period=fetch_1m_period, interval="1m")
                df_m1 = _strip_tz(df_m1)
                display_period = f"{fetch_1m_period} (1m for Vester entry)"
            except Exception:
                df_m1 = None

    df_daily = _strip_tz(df_daily)
    df_m15 = _strip_tz(df_m15)

    strat = LQStrategy(
        df_daily=df_daily,
        df_m15=df_m15,
        df_m1=df_m1,
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

    signals = signals[signals.apply(_valid_sl, axis=1)] if not signals.empty else pd.DataFrame()

    risk = getattr(config, "LQ_MIN_RR", 2.0)
    lock_in_enabled = getattr(config, "LOCK_IN_ENABLED", True)
    lock_in_trigger = getattr(config, "LOCK_IN_TRIGGER_RR", 3.3)
    lock_in_at = getattr(config, "LOCK_IN_AT_RR", 3.0)
    risk_pct = getattr(config, "RISK_PER_TRADE", 0.10)

    if signals.empty:
        if return_stats:
            d = _stats_dict("lq", 0, 0, 0, 0.0, 0.0, config.INITIAL_BALANCE)
            d["buys"] = 0
            d["sells"] = 0
            if include_trade_details:
                d["trade_details"] = []
            return d
        print()
        print("Backtest Parameters (LQStrategy):")
        print(f"  Asset: {used_symbol}")
        print(f"  Risk per trade: {risk_pct * 100:.0f}%")
        print(f"  Min R:R: 1:{risk}")
        print(f"  Duration: {display_period}")
        print()
        print("| Strategy | Trades | Wins | Losses | Win rate  | Final balance | Return      |")
        print("| :------- | :----- | :--- | :----- | :-------- | :------------ | :---------- |")
        print("| lq       |      0 |    0 |      0 |     0.00% | $      100.00 |      0.00% |")
        print()
        return

    balance = config.INITIAL_BALANCE
    wins = losses = buys = sells = 0
    total_profit = total_loss = 0.0
    trade_details = [] if include_trade_details else None
    losing_trades = [] if include_trade_details else None
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
        future_prices = df_m15.loc[df_m15.index > trade_time]
        if future_prices.empty:
            continue
        outcome_bar_time = None
        if trade["type"] == "BUY":
            sl_dist = adj_entry - adj_sl
            tp_price = trade.get("tp") or adj_entry + (sl_dist * risk)
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
                    outcome_bar_time = idx
                    break
                if bar["high"] >= tp_price:
                    outcome = "WIN"
                    outcome_rr = risk
                    outcome_bar_time = idx
                    break
            if outcome == "WIN":
                profit = _calc_trade_pnl(used_symbol, balance, risk_pct, sl_dist, "WIN", outcome_rr, spread_cost)
                total_profit += profit
                balance += profit
                wins += 1
                buys += 1
                _update_per_day_session(trade_time, per_day, per_session)
                if trade_details is not None:
                    trade_details.append((trade_time, "WIN", entry_price, stop_loss, tp_price, outcome_bar_time, trade.get("reason", "")))
            elif outcome == "LOSS":
                loss = _calc_trade_pnl(used_symbol, balance, risk_pct, sl_dist, "LOSS", 0, spread_cost)
                total_loss += loss
                balance -= loss
                losses += 1
                buys += 1
                _update_per_day_session(trade_time, per_day, per_session)
                if trade_details is not None:
                    trade_details.append((trade_time, "LOSS", entry_price, stop_loss, tp_price, outcome_bar_time, trade.get("reason", "")))
                if losing_trades is not None:
                    losing_trades.append((trade_time, entry_price, stop_loss, tp_price, outcome_bar_time, trade.get("reason", "")))
        elif trade["type"] == "SELL":
            sl_dist = adj_sl - adj_entry
            tp_price = trade.get("tp") or adj_entry - (sl_dist * risk)
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
                    outcome_bar_time = idx
                    break
                if bar["low"] <= tp_price:
                    outcome = "WIN"
                    outcome_rr = risk
                    outcome_bar_time = idx
                    break
            if outcome == "WIN":
                profit = _calc_trade_pnl(used_symbol, balance, risk_pct, sl_dist, "WIN", outcome_rr, spread_cost)
                total_profit += profit
                balance += profit
                wins += 1
                sells += 1
                _update_per_day_session(trade_time, per_day, per_session)
                if trade_details is not None:
                    trade_details.append((trade_time, "WIN", entry_price, stop_loss, tp_price, outcome_bar_time, trade.get("reason", "")))
            elif outcome == "LOSS":
                loss = _calc_trade_pnl(used_symbol, balance, risk_pct, sl_dist, "LOSS", 0, spread_cost)
                total_loss += loss
                balance -= loss
                losses += 1
                sells += 1
                _update_per_day_session(trade_time, per_day, per_session)
                if trade_details is not None:
                    trade_details.append((trade_time, "LOSS", entry_price, stop_loss, tp_price, outcome_bar_time, trade.get("reason", "")))
                if losing_trades is not None:
                    losing_trades.append((trade_time, entry_price, stop_loss, tp_price, outcome_bar_time, trade.get("reason", "")))

    total = wins + losses
    win_rate = (100.0 * wins / total) if total > 0 else 0.0
    ret_pct = ((balance - config.INITIAL_BALANCE) / config.INITIAL_BALANCE) * 100.0

    if return_stats:
        d = _stats_dict("lq", total, wins, losses, win_rate, balance, ret_pct)
        d["buys"] = buys
        d["sells"] = sells
        d["total_profit"] = total_profit
        d["total_loss"] = total_loss
        if include_trade_details:
            d["trade_details"] = trade_details
            d["losing_trades"] = losing_trades
        return d

    print()
    print("Backtest Parameters (LQStrategy):")
    print(f"  Asset: {used_symbol}")
    print(f"  Risk per trade: {risk_pct * 100:.0f}%")
    print(f"  Min R:R: 1:{risk}")
    print(f"  Duration: {display_period}")
    print()
    print("| Strategy | Trades | Wins | Losses | Win rate  | Final balance | Return      |")
    print("| :------- | :----- | :--- | :----- | :-------- | :------------ | :---------- |")
    ret_str = f"{'+' if ret_pct >= 0 else ''}{ret_pct:,.2f}%"
    print(f"| lq       | {total:>5} | {wins:>4} | {losses:>5} | {win_rate:>8.2f}% | ${balance:>12,.2f} | {ret_str:>10} |")
    print()
    print(f"  BUY: {buys} | SELL: {sells}")
    if per_day or per_session:
        day_str = " | ".join(f"{d}: {c}" for d, c in sorted(per_day.items()))
        sess_str = " | ".join(f"{s}: {c}" for s, c in sorted(per_session.items()))
        print(f"  Trades per day: {day_str}")
        print(f"  Trades per session: {sess_str}")
    print()
