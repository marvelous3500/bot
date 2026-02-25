"""Trading strategies."""
from .base import BaseStrategy
from .strategy_marvellous import MarvellousStrategy
from .strategy_vester import VesterStrategy
from .strategy_follow import FollowStrategy
from .strategy_test_sl import TestSLStrategy
from .strategy_lq import LQStrategy

__all__ = [
    "BaseStrategy",
    "MarvellousStrategy",
    "VesterStrategy",
    "FollowStrategy",
    "TestSLStrategy",
    "LQStrategy",
]