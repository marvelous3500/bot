"""Shared utilities for backtest runners."""
import pandas as pd
import config


def _update_per_day_session(trade_time, per_day, per_session):
    """Update per_day and per_session dicts from trade_time."""
    ts = pd.Timestamp(trade_time) if not hasattr(trade_time, "strftime") else trade_time
    day_str = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts.date()) if hasattr(ts, "date") else "N/A"
    hour = ts.hour if ts.tzinfo is None else ts.tz_convert("UTC").hour if ts.tzinfo else ts.hour
    session = config.TRADE_SESSION_HOURS.get(hour, "other")
    per_day[day_str] = per_day.get(day_str, 0) + 1
    per_session[session] = per_session.get(session, 0) + 1


def get_pip_size_for_symbol(symbol):
    """Return pip size for Yahoo symbol. Gold ~0.01, forex ~0.0001, BTC ~1.0."""
    if symbol is None:
        return 0.0001
    pip = config.get_symbol_config(symbol, "PIP_SIZE")
    if pip is not None:
        return float(pip)
    s = str(symbol).upper()
    if 'GC=' in s or 'XAU' in s or 'GOLD' in s:
        return 0.01
    if 'BTC' in s:
        return 1.0
    return 0.0001


def _use_manual_lot_for_backtest(symbol):
    """True if gold + GOLD_USE_MANUAL_LOT (same logic as live)."""
    is_gold = config.is_gold_symbol(symbol) if hasattr(config, 'is_gold_symbol') else ("XAU" in str(symbol or "").upper() or "GOLD" in str(symbol or "").upper())
    return is_gold and getattr(config, 'GOLD_USE_MANUAL_LOT', False)


def _use_gold_fixed_sl(symbol):
    """True if gold and GOLD_MANUAL_SL_POINTS > 0 (apply fixed SL override)."""
    is_gold = config.is_gold_symbol(symbol) if hasattr(config, 'is_gold_symbol') else ("XAU" in str(symbol or "").upper() or "GOLD" in str(symbol or "").upper())
    sl_pts = getattr(config, 'GOLD_MANUAL_SL_POINTS', 0)
    return is_gold and sl_pts > 0


def _apply_gold_manual_sl_override(used_symbol, adj_entry, adj_sl, order_type):
    """When gold and GOLD_MANUAL_SL_POINTS set, override SL to fixed distance (50 pips = 5 points)."""
    if not _use_gold_fixed_sl(used_symbol):
        return adj_sl
    sl_points = getattr(config, 'GOLD_MANUAL_SL_POINTS', 5.0)
    if order_type == 'BUY':
        return adj_entry - sl_points
    return adj_entry + sl_points


def _calc_trade_pnl(used_symbol, balance, risk_pct, sl_dist, outcome, outcome_rr, spread_cost):
    """
    Return profit (WIN) or loss (LOSS) amount.
    Gold + GOLD_USE_MANUAL_LOT: use MAX_POSITION_SIZE and LOSS_PER_LOT_PER_POINT.
    Else: use risk-based (balance * risk_pct).
    """
    commission_per_lot = getattr(config, 'BACKTEST_COMMISSION_PER_LOT', 0.0)
    use_manual = _use_manual_lot_for_backtest(used_symbol)
    if use_manual:
        lot = getattr(config, 'MAX_POSITION_SIZE', 0.01)
        loss_per_lot = config.get_symbol_config(used_symbol, 'LOSS_PER_LOT_PER_POINT') or 100
        commission = commission_per_lot * lot if commission_per_lot else 0.0
        if outcome == "WIN":
            return sl_dist * outcome_rr * lot * loss_per_lot - spread_cost - commission
        return sl_dist * lot * loss_per_lot + spread_cost + commission
    commission = commission_per_lot * 0.01 if commission_per_lot else 0.0
    if outcome == "WIN":
        return (balance * risk_pct) * outcome_rr - spread_cost - commission
    return (balance * risk_pct) + spread_cost + commission


def _apply_backtest_realism(entry_price, stop_loss, order_type, symbol, bar_close=None):
    """Apply spread, slippage to entry/SL. Returns (adj_entry, adj_sl, commission)."""
    spread_pips = config.get_symbol_config(symbol, 'BACKTEST_SPREAD_PIPS') or getattr(config, 'BACKTEST_SPREAD_PIPS', 0.0)
    slippage_pips = config.get_symbol_config(symbol, 'BACKTEST_SLIPPAGE_PIPS') or getattr(config, 'BACKTEST_SLIPPAGE_PIPS', 0.0)
    commission_per_lot = getattr(config, 'BACKTEST_COMMISSION_PER_LOT', 0.0)
    pip_size = get_pip_size_for_symbol(symbol)
    default_lot = 0.01
    commission = commission_per_lot * default_lot if commission_per_lot else 0.0
    close = bar_close if bar_close is not None else entry_price
    adj_entry = entry_price
    if spread_pips > 0:
        half_spread = (spread_pips / 2.0) * pip_size
        if order_type == 'BUY':
            adj_entry = close + half_spread
        else:
            adj_entry = close - half_spread
    adj_sl = stop_loss
    if slippage_pips > 0:
        slip = slippage_pips * pip_size
        if order_type == 'BUY':
            adj_sl = stop_loss - slip
        else:
            adj_sl = stop_loss + slip
    return adj_entry, adj_sl, commission


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
