"""Shared utilities for backtest runners."""
import config


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
