"""Backtest runners for each strategy."""
from .common import _stats_dict
from .backtest_bos import run_bos_backtest
from .backtest_kingsley import run_kingsley_backtest
from .backtest_test import run_test_backtest

__all__ = [
    "_stats_dict",
    "run_bos_backtest",
    "run_kingsley_backtest",
    "run_test_backtest",
]
