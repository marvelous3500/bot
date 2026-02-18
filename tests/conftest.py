"""Pytest fixtures for ICT Trading Bot tests."""
import pandas as pd
import numpy as np
import pytest
from datetime import datetime, timedelta


@pytest.fixture
def sample_ohlcv_df():
    """Minimal OHLCV DataFrame with 7 bars (swing high at index 3)."""
    base = datetime(2025, 1, 1, 0, 0, 0)
    # Index 3 has highest high (100) and lowest low (90) for swing high/low
    data = {
        'open': [95, 96, 97, 98, 97, 96, 95],
        'high': [96, 97, 98, 100, 98, 97, 96],  # index 3 = 100 (swing high)
        'low': [94, 95, 96, 90, 96, 95, 94],    # index 3 = 90 (swing low)
        'close': [95.5, 96.5, 97.5, 95, 97, 96, 95.5],
        'volume': [100] * 7,
    }
    index = pd.DatetimeIndex([base + timedelta(hours=i) for i in range(7)])
    return pd.DataFrame(data, index=index)


@pytest.fixture
def sample_ohlcv_bos_bull():
    """OHLCV with swing structure that triggers BULLISH BOS (close breaks swing high)."""
    base = datetime(2025, 1, 1, 0, 0, 0)
    # Swing high at index 2 (high=100); swing low at index 3 (low=93); bar 5 closes above 100 -> BOS bull
    data = {
        'open': [95, 96, 98, 98, 96, 99],   # index 3 open=98, close=97.5 -> bearish (for OB)
        'high': [96, 98, 100, 99, 98, 102],
        'low': [94, 95, 97, 93, 95, 98],   # index 3 low=93 is swing low (neighbors all > 93)
        'close': [95.5, 97, 98, 97.5, 96.5, 101],  # bar 5 close 101 > 100
        'volume': [100] * 6,
    }
    index = pd.DatetimeIndex([base + timedelta(hours=i) for i in range(6)])
    return pd.DataFrame(data, index=index)


@pytest.fixture
def pip_size_gold():
    """Pip size for gold (GC=F)."""
    return 0.01


@pytest.fixture
def pip_size_forex():
    """Pip size for forex (GBPUSD)."""
    return 0.0001
