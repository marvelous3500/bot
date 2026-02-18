"""Shared utilities for backtest runners."""
import config


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
