"""Trading strategies."""
from .strategy_bos import H1M5BOSStrategy
from .strategy_kingsley import KingsleyGoldStrategy
from .strategy_marvellous import MarvellousStrategy
from .strategy_nas import NasStrategy
from .strategy_judas import JudasStrategy
from .strategy_test import TestStrategy

__all__ = [
    "H1M5BOSStrategy",
    "KingsleyGoldStrategy",
    "MarvellousStrategy",
    "NasStrategy",
    "JudasStrategy",
    "TestStrategy",
]
