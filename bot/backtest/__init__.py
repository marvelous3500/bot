"""Backtest runners for each strategy."""
from .common import _stats_dict
from .backtest_marvellous import run_marvellous_backtest
from .backtest_test import run_test_backtest
from .backtest_vester import run_vester_backtest

__all__ = [
    "_stats_dict",
    "run_marvellous_backtest",
    "run_test_backtest",
    "run_vester_backtest",
]