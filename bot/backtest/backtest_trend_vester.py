"""
Backtest runner for TrendVesterStrategy (H1 trend BOS only + vester 1M entry).
More signals than vester: no H1 zone/sweep, no 5M sweep required.
"""
import pandas as pd
import config
from .. import vester_config as vc
from ..data_loader import fetch_data_yfinance, load_data_csv
from ..strategies import TrendVesterStrategy
from .common import _stats_dict, get_pip_size_for_symbol, _apply_backtest_realism, _apply_gold_manual_sl_override, _calc_trade_pnl, _update_per_day_session


def _strip_tz(df):
    if df is None or df.empty:
        return df
    if df.index.tz is not None:
        df = df.copy()
        df.index = df.index.tz_convert(None)
    return df


def run_trend_vester_backtest(
    csv_path=None,
    symbol=None,
    period=None,
    return_stats=False,
    include_trade_details=False,
    df_h1=None,
    df_m5=None,
    df_m1=None,
    df_h4=None,
):
    """Run TrendVester backtest. Same data as vester: 1H, 5M, 1M."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    display_period = period or getattr(config, "BACKTEST_PERIOD", "60d")
    period_note = ""
    used_symbol = symbol or getattr(config, "TREND_VESTER_BACKTEST_SYMBOL", "GC=F")

    if df_h1 is not None and df_m5 is not None and df_m1 is not None:
        pass
    elif csv_path:
        df = load_data_csv(csv_path)
        df_h1 = df.resample("1h").agg(agg).dropna()
        df_m5 = df.resample("5min").agg(agg).dropna()
        df_m1 = df.resample("1min").agg(agg).dropna()
    else:
        if period == "1d":
            fetch_period = "1d"
        else:
            fetch_period = "7d"
        period_note = f" (Yahoo 1m limit; {period} requested)" if period not in ["1d", "7d"] else ""
        display_period = fetch_period
        df_h1 = fetch_data_yfinance(used_symbol, period=fetch_period, interval="1h")
        df_m5 = fetch_data_yfinance(used_symbol, period=fetch_period, interval="5m")
        df_m1 = fetch_data_yfinance(used_symbol, period=fetch_period, interval="1m")

    if df_h4 is None and df_h1 is not None:
        df_h4 = df_h1.resample("4h").agg(agg).dropna()
    for d in (df_h1, df_m5, df_m1, df_h4):
        if d is not None:
            _strip_tz(d)

    strat = TrendVesterStrategy(
        df_h1=df_h1,
        df_m5=df_m5,
        df_m1=df_m1,
        df_h4=df_h4,
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
    trailing_enabled = getattr(config, "TRAILING_SL_ENABLED", False)
    trailing_activation_r = getattr(config, "TRAILING_SL_ACTIVATION_R", 1.0)
    trailing_pips = getattr(config, "TRAILING_SL_DISTANCE_PIPS", 20.0)
    risk_pct = getattr(config, "VESTER_RISK_PER_TRADE", vc.RISK_PER_TRADE)
    pip_size = get_pip_size_for_symbol(used_symbol)

    if signals.empty:
        if return_stats:
            d = _stats_dict("trend_vester", 0, 0, 0, 0.0, 0.0, config.INITIAL_BALANCE)
            d["buys"] = 0
            d["sells"] = 0
            if include_trade_details:
                d["trade_details"] = []
            return d
        print()
        print("Backtest Parameters (TrendVesterStrategy):")
        print(f"  Asset: {used_symbol}")
        print(f"  Risk per trade: {risk_pct * 100:.0f}%")
        print(f"  Timeframes: H1 trend (BOS only), 5M zone, 1M entry")
        print(f"  Duration: {display_period}{period_note}")
        print()
        print("| Strategy       | Trades | Wins | Losses | Win rate  | Final balance | Return      |")
        print("| trend_vester   |      0 |    0 |      0 |     0.00% | $      100.00 |      0.00% |")
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
        future_prices = df_m1.loc[df_m1.index > trade_time]
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
            effective_sl = adj_sl
            for idx, bar in future_prices.iterrows():
                if lock_in_enabled and lock_in_trigger_price and lock_in_sl and bar["high"] >= lock_in_trigger_price:
                    lock_in_triggered = True
                effective_sl = lock_in_sl if lock_in_triggered else adj_sl
                if trailing_enabled and sl_dist > 0 and bar["high"] >= adj_entry + sl_dist * trailing_activation_r:
                    trail_sl = bar["high"] - trailing_pips * pip_size
                    if trail_sl > effective_sl and trail_sl < bar["high"]:
                        effective_sl = trail_sl
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
            elif outcome == "LOSS":
                loss = _calc_trade_pnl(used_symbol, balance, risk_pct, sl_dist, "LOSS", 0, spread_cost)
                total_loss += loss
                balance -= loss
                losses += 1
                buys += 1
                if losing_trades is not None:
                    losing_trades.append((trade_time, entry_price, stop_loss, tp_price, outcome_bar_time, trade.get("reason", "")))
            if outcome:
                _update_per_day_session(trade_time, per_day, per_session)
                if trade_details is not None:
                    trade_details.append((trade_time, outcome, entry_price, stop_loss, tp_price, outcome_bar_time, trade.get("reason", "")))
        else:
            sl_dist = adj_sl - adj_entry
            tp_price = trade.get("tp") or adj_entry - (sl_dist * risk)
            lock_in_sl = adj_entry - (sl_dist * lock_in_at) if lock_in_enabled else None
            lock_in_trigger_price = adj_entry - (sl_dist * lock_in_trigger) if lock_in_enabled else None
            outcome = None
            outcome_rr = risk
            lock_in_triggered = False
            effective_sl = adj_sl
            for idx, bar in future_prices.iterrows():
                if lock_in_enabled and lock_in_trigger_price and lock_in_sl and bar["low"] <= lock_in_trigger_price:
                    lock_in_triggered = True
                effective_sl = lock_in_sl if lock_in_triggered else adj_sl
                if trailing_enabled and sl_dist > 0 and bar["low"] <= adj_entry - sl_dist * trailing_activation_r:
                    trail_sl = bar["low"] + trailing_pips * pip_size
                    if trail_sl < effective_sl and trail_sl > bar["low"]:
                        effective_sl = trail_sl
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
            elif outcome == "LOSS":
                loss = _calc_trade_pnl(used_symbol, balance, risk_pct, sl_dist, "LOSS", 0, spread_cost)
                total_loss += loss
                balance -= loss
                losses += 1
                sells += 1
                if losing_trades is not None:
                    losing_trades.append((trade_time, entry_price, stop_loss, tp_price, outcome_bar_time, trade.get("reason", "")))
            if outcome:
                _update_per_day_session(trade_time, per_day, per_session)
                if trade_details is not None:
                    trade_details.append((trade_time, outcome, entry_price, stop_loss, tp_price, outcome_bar_time, trade.get("reason", "")))

    if return_stats:
        d = _stats_dict("trend_vester", wins + losses, wins, losses, total_profit, total_loss, balance)
        d["buys"] = buys
        d["sells"] = sells
        if include_trade_details:
            d["trade_details"] = trade_details or []
        return d

    return_pct = ((balance - config.INITIAL_BALANCE) / config.INITIAL_BALANCE) * 100
    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
    print()
    print("Backtest Parameters (TrendVesterStrategy):")
    print(f"  Asset: {used_symbol}")
    print(f"  Risk per trade: {risk_pct * 100:.0f}%")
    print(f"  Timeframes: H1 trend (BOS only), 5M zone, 1M entry")
    print(f"  Duration: {display_period}{period_note}")
    print()
    print("| Strategy       | Trades | Wins | Losses | Win rate  | Final balance | Return      |")
    ret_str = f"{'+' if return_pct >= 0 else ''}{return_pct:,.2f}%"
    print(f"| trend_vester   | {wins + losses:>5} | {wins:>4} | {losses:>6} | {win_rate:>8.2f}% | ${balance:>11,.2f} | {ret_str:>10} |")
    print()
    print(f"  BUY: {buys} | SELL: {sells}")
    if include_trade_details and trade_details:
        print()
        print("=" * 60)
        print("TRADE LOG")
        print("=" * 60)
        for i, t in enumerate(trade_details, 1):
            trade_time, outcome, entry, sl, tp, bar_time, reason = t[0], t[1], t[2], t[3], t[4], t[5], t[6] if len(t) > 6 else ""
            bar_str = str(bar_time) if bar_time is not None else "N/A"
            print(f"  #{i} {outcome:4} | Entry: {entry:.4f} | SL: {sl:.4f} | TP: {tp:.4f} | Bar hit: {bar_str}")
            if reason:
                print(f"       Reason: {reason[:70]}{'...' if len(reason) > 70 else ''}")
        print()


if __name__ == "__main__":
    run_trend_vester_backtest()
