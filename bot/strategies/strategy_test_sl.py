"""
TestSLStrategy: one-shot BUY at current price for lot-size testing.
Use with: --strategy test-sl --mode live
Takes a single trade and stops after 3 seconds.
"""
import pandas as pd
from typing import Optional

from .base import BaseStrategy


class TestSLStrategy(BaseStrategy):
    """
    Minimal strategy for testing lot size in live. No backtest logic.
    """

    def __init__(self, df: Optional[pd.DataFrame] = None, symbol: Optional[str] = None, verbose: bool = False):
        self.df = df
        self.symbol = symbol
        self.verbose = verbose

    def prepare_data(self) -> pd.DataFrame:
        return self.df if self.df is not None else pd.DataFrame()

    def run_backtest(self) -> pd.DataFrame:
        """No backtest for test-sl."""
        return pd.DataFrame()
