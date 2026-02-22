"""
Backtest runner for VesterStrategy (1H bias -> 5M setup -> 1M entry).
Multi-timeframe smart-money: market structure, liquidity sweeps, FVG, order blocks.

Example config:
  Symbol: GC=F (gold) or GBPUSD=X
  Period: 60d (or 7d if 1m data needed - Yahoo 1m limit)
  VESTER_SWING_LENGTH=3, VESTER_OB_LOOKBACK=20, VESTER_HTF_LOOKBACK_HOURS=48
  VESTER_MIN_RR=3, VESTER_RISK_PER_TRADE=0.10, VESTER_MAX_TRADES_PER_SESSION=2
  VESTER_DAILY_LOSS_LIMIT_PCT=5.0, VESTER_USE_TRAILING_STOP=False

Example CLI: python main.py --mode backtest --strategy vester --symbol GC=F --period 60d
"""
import pandas as pd
import config
from .. import vester_config as vc
from ..data_loader import fetch_data_yfinance, load_data_csv
from ..strategies import VesterStrategy
from .common import _stats_dict, get_pip_size_for_symbol, _apply_backtest_realism


def _strip_tz(df):
    if df is None or df.empty:
        return df
    if df.index.tz is not None:
        df = df.copy()
        df.index = df.index.tz_convert(None)
    return df


def run_vester_backtest(
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
    """Run Vester backtest. Uses 1H, 5M, 1M timeframes. Optional 4H when VESTER_REQUIRE_4H_BIAS=True."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    display_period = period or getattr(config, "BACKTEST_PERIOD", "60d")
    period_note = ""

    if df_h1 is not None and df_m5 is not None and df_m1 is not None:
        pass
    elif csv_path:
        df = load_data_csv(csv_path)
        df_h1 = df.resample("1h").agg(agg).dropna()
        df_m5 = df.resample("5min").agg(agg).dropna()
        df_m1 = df.resample("1min").agg(agg).dropna()
    else:
        symbol = symbol or getattr(config, "VESTER_BACKTEST_SYMBOL", vc.VESTER_BACKTEST_SYMBOL)
        period = period or getattr(config, "BACKTEST_PERIOD", "60d")
        fetch_period = "7d"
        period_note = f" (Yahoo 1m limit; {period} requested)" if period != "7d" else ""
        display_period = fetch_period
        df_h1 = fetch_data_yfinance(symbol, period=fetch_period, interval="1h")
        df_m5 = fetch_data_yfinance(symbol, period=fetch_period, interval="5m")
        df_m1 = fetch_data_yfinance(symbol, period=fetch_period, interval="1m")

    if df_h4 is None and df_h1 is not None:
        df_h4 = df_h1.resample("4h").agg(agg).dropna()
    for d in (df_h1, df_m5, df_m1, df_h4):
        if d is not None:
            _strip_tz(d)

    used_symbol = symbol or getattr(config, "VESTER_BACKTEST_SYMBOL", vc.VESTER_BACKTEST_SYMBOL)
    strat = VesterStrategy(
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

    risk = getattr(config, "RISK_REWARD_RATIO", 3.0)
    risk_pct = getattr(config, "VESTER_RISK_PER_TRADE", vc.RISK_PER_TRADE)

    if signals.empty:
        if return_stats:
            d = _stats_dict("vester", 0, 0, 0, 0.0, 0.0, config.INITIAL_BALANCE)
            d["buys"] = 0
            d["sells"] = 0
            if include_trade_details:
                d["trade_details"] = []
            return d
        print()
        print("Backtest Parameters (VesterStrategy):")
        print(f"  Asset: {used_symbol}")
        print(f"  Risk per trade: {risk_pct * 100:.0f}%")
        print(f"  Risk:Reward: 1:{risk}")
        htf_label = "1H+4H" if getattr(config, "VESTER_REQUIRE_4H_BIAS", False) else "1H"
        print(f"  Timeframes: {htf_label} bias, 5M setup, 1M entry")
        print(f"  Duration: {display_period}{period_note}")
        print()
        print("| Strategy | Trades | Wins | Losses | Win rate  | Final balance | Return      |")
        print("| :------- | :----- | :--- | :----- | :-------- | :------------ | :---------- |")
        print("| vester   |      0 |    0 |      0 |     0.00% | $      100.00 |      0.00% |")
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
    losing_trades = [] if include_trade_details else None

    for _, trade in signals.iterrows():
        entry_price = trade["price"]
        stop_loss = trade["sl"]
        trade_time = trade["time"]
        adj_entry, adj_sl, commission = _apply_backtest_realism(
            entry_price, stop_loss, trade["type"], used_symbol, entry_price
        )
        spread_cost = abs(adj_entry - entry_price)
        future_prices = df_m1.loc[df_m1.index > trade_time]
        if future_prices.empty:
            continue
        outcome_bar_time = None
        if trade["type"] == "BUY":
            sl_dist = adj_entry - adj_sl
            tp_price = trade.get("tp")
            if tp_price is None or tp_price <= adj_entry:
                tp_price = adj_entry + (sl_dist * risk)
            outcome = None
            for idx, bar in future_prices.iterrows():
                if bar["low"] <= adj_sl:
                    outcome = "LOSS"
                    outcome_bar_time = idx
                    break
                if bar["high"] >= tp_price:
                    outcome = "WIN"
                    outcome_bar_time = idx
                    break
            if outcome == "WIN":
                profit = (balance * risk_pct) * risk - spread_cost - commission
                total_profit += profit
                balance += profit
                wins += 1
                buys += 1
                if trade_details is not None:
                    trade_details.append((trade_time, "WIN", entry_price, stop_loss, tp_price, outcome_bar_time, trade.get("reason", "")))
            elif outcome == "LOSS":
                loss = (balance * risk_pct) + spread_cost + commission
                total_loss += loss
                balance -= loss
                losses += 1
                buys += 1
                if trade_details is not None:
                    trade_details.append((trade_time, "LOSS", entry_price, stop_loss, tp_price, outcome_bar_time, trade.get("reason", "")))
                if losing_trades is not None:
                    losing_trades.append((trade_time, entry_price, stop_loss, tp_price, outcome_bar_time, trade.get("reason", "")))
        elif trade["type"] == "SELL":
            sl_dist = adj_sl - adj_entry
            tp_price = trade.get("tp")
            if tp_price is None or tp_price >= adj_entry:
                tp_price = adj_entry - (sl_dist * risk)
            outcome = None
            outcome_bar_time = None
            for idx, bar in future_prices.iterrows():
                if bar["high"] >= adj_sl:
                    outcome = "LOSS"
                    outcome_bar_time = idx
                    break
                if bar["low"] <= tp_price:
                    outcome = "WIN"
                    outcome_bar_time = idx
                    break
            if outcome == "WIN":
                profit = (balance * risk_pct) * risk - spread_cost - commission
                total_profit += profit
                balance += profit
                wins += 1
                sells += 1
                if trade_details is not None:
                    trade_details.append((trade_time, "WIN", entry_price, stop_loss, tp_price, outcome_bar_time, trade.get("reason", "")))
            elif outcome == "LOSS":
                loss = (balance * risk_pct) + spread_cost + commission
                total_loss += loss
                balance -= loss
                losses += 1
                sells += 1
                if trade_details is not None:
                    trade_details.append((trade_time, "LOSS", entry_price, stop_loss, tp_price, outcome_bar_time, trade.get("reason", "")))
                if losing_trades is not None:
                    losing_trades.append((trade_time, entry_price, stop_loss, tp_price, outcome_bar_time, trade.get("reason", "")))

    if return_stats:
        d = _stats_dict(
            "vester", wins + losses, wins, losses, total_profit, total_loss, balance
        )
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
    print("Backtest Parameters (VesterStrategy):")
    print(f"  Asset: {used_symbol}")
    print(f"  Risk per trade: {risk_pct * 100:.0f}%")
    print(f"  Risk:Reward: 1:{risk}")
    htf_label = "1H+4H" if getattr(config, "VESTER_REQUIRE_4H_BIAS", False) else "1H"
    print(f"  Timeframes: {htf_label} bias, 5M setup, 1M entry")
    print(f"  Trade Limit: {trade_limit_str}")
    print(f"  Duration: {display_period}{period_note}")
    print()
    print("| Strategy | Trades | Wins | Losses | Win rate  | Final balance | Return      |")
    print("| :------- | :----- | :--- | :----- | :-------- | :------------ | :---------- |")
    ret_str = f"{'+' if return_pct >= 0 else ''}{return_pct:,.2f}%"
    print(f"| vester   | {wins + losses:>5} | {wins:>4} | {losses:>6} | {win_rate:>8.2f}% | ${balance:>11,.2f} | {ret_str:>10} |")
    print()
    print(f"  BUY: {buys} | SELL: {sells}")
    print()
    if len(invalid_sl) > 0:
        print(f"Invalid SL (rejected): {len(invalid_sl)}")
    if include_trade_details and trade_details:
        print()
        print("=" * 60)
        print("TRADE LOG")
        print("=" * 60)
        per_day = {}
        per_session = {}
        for i, t in enumerate(trade_details, 1):
            trade_time, outcome, entry, sl, tp, bar_time, reason = t[0], t[1], t[2], t[3], t[4], t[5], t[6] if len(t) > 6 else ""
            bar_str = str(bar_time) if bar_time is not None else "N/A"
            ts = pd.Timestamp(trade_time) if not hasattr(trade_time, "hour") else trade_time
            day_str = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts.date()) if hasattr(ts, "date") else "N/A"
            hour = ts.hour if ts.tzinfo is None else ts.tz_convert("UTC").hour
            session = config.TRADE_SESSION_HOURS.get(hour, "other")
            per_day[day_str] = per_day.get(day_str, 0) + 1
            per_session[session] = per_session.get(session, 0) + 1
            print(f"  #{i} {outcome:4} | Day: {day_str} | Session: {session} | Entry: {entry:.4f} | SL: {sl:.4f} | TP: {tp:.4f} | Bar hit: {bar_str}")
            if reason:
                print(f"       Reason: {reason[:70]}{'...' if len(reason) > 70 else ''}")
        print()
        print("TRADES BY DAY:   " + " | ".join(f"{d}: {c}" for d, c in sorted(per_day.items())))
        print("TRADES BY SESSION: " + " | ".join(f"{s}: {c}" for s, c in sorted(per_session.items())))
        if losing_trades:
            print()
            print("=" * 60)
            print("LOSING TRADES (for analysis)")
            print("=" * 60)
            for i, t in enumerate(losing_trades, 1):
                trade_time, entry, sl, tp, bar_time, reason = t
                ts = pd.Timestamp(trade_time) if not hasattr(trade_time, "hour") else trade_time
                day_str = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts.date()) if hasattr(ts, "date") else "N/A"
                hour = ts.hour if ts.tzinfo is None else ts.tz_convert("UTC").hour
                session = config.TRADE_SESSION_HOURS.get(hour, "other")
                sl_dist = abs(entry - sl)
                rr = abs(tp - entry) / sl_dist if sl_dist > 0 else 0
                print(f"  Loss #{i}: Day: {day_str} | Session: {session} | Entry {trade_time} @ {entry:.4f} | SL: {sl:.4f} | TP: {tp:.4f} | RR: 1:{rr:.1f}")
                print(f"           SL hit at bar: {bar_time}")
                if reason:
                    print(f"           Reason: {reason[:70]}{'...' if len(reason) > 70 else ''}")
        print()


if __name__ == "__main__":
    run_vester_backtest()
