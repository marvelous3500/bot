"""Abstract base class for trading strategies."""
from abc import ABC, abstractmethod
from typing import Any


class BaseStrategy(ABC):
    """Abstract base class for strategies. Requires prepare_data() and run_backtest()."""

    @abstractmethod
    def prepare_data(self) -> Any:
        """Run indicators and prepare DataFrames. Returns prepared data (strategy-specific)."""
        pass

    @abstractmethod
    def run_backtest(self):
        """Run backtest; returns DataFrame of signals (time, type, price, sl, tp, reason)."""
        pass
