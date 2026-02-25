"""Backtest runners for each strategy."""
from .common import _stats_dict
from .backtest_marvellous import run_marvellous_backtest
from .backtest_vester import run_vester_backtest
from .backtest_kingsely import run_kingsely_backtest
from .backtest_follow import run_follow_backtest
from .backtest_lq import run_lq_backtest

__all__ = [
    "_stats_dict",
    "run_marvellous_backtest",
    "run_vester_backtest",
    "run_kingsely_backtest",
    "run_follow_backtest",
    "run_lq_backtest",
]