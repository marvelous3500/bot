"""Trading strategies."""
from .strategy_bos import H1M5BOSStrategy
from .strategy_kingsley import KingsleyGoldStrategy
from .strategy_marvellous import MarvellousStrategy
from .strategy_test import TestStrategy

__all__ = [
    "H1M5BOSStrategy",
    "KingsleyGoldStrategy",
    "MarvellousStrategy",
    "TestStrategy",
]
