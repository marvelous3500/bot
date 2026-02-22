"""Trading strategies."""
from .base import BaseStrategy
from .strategy_marvellous import MarvellousStrategy
from .strategy_vester import VesterStrategy

__all__ = [
    "BaseStrategy",
    "MarvellousStrategy",
    "VesterStrategy",
]