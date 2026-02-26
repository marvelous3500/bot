"""Trading strategies."""
from .base import BaseStrategy
from .strategy_marvellous import MarvellousStrategy
from .strategy_vester import VesterStrategy
from .strategy_kingsely import KingselyStrategy
from .strategy_follow import FollowStrategy
from .strategy_test_sl import TestSLStrategy
from .strategy_lq import LQStrategy
from .strategy_v1 import V1Strategy
from .strategy_vee import VeeStrategy

__all__ = [
    "BaseStrategy",
    "MarvellousStrategy",
    "VesterStrategy",
    "KingselyStrategy",
    "FollowStrategy",
    "TestSLStrategy",
    "LQStrategy",
    "V1Strategy",
    "VeeStrategy",
]