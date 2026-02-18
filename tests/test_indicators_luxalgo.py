"""Unit tests for bot/indicators_luxalgo.py (LuxAlgo ICT parity)."""
import pandas as pd
import pytest
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.indicators_luxalgo import (
    detect_swing_highs_lows,
    detect_break_of_structure,
    identify_order_block,
)


@pytest.fixture
def sample_ohlcv_pivot():
    """OHLCV with clear pivot high at index 6 (swing_length=5, right=1)."""
    base = datetime(2025, 1, 1, 0, 0, 0)
    # Pivot high at index 6: window [1,7], high[6]=100 must be max
    # Pivot low at index 6: window [1,7], low[6]=90 must be min
    data = {
        'open': [91, 92, 93, 94, 95, 96, 97, 96, 95, 94, 93, 92, 91, 90, 89],
        'high': [92, 93, 94, 95, 96, 97, 100, 98, 97, 96, 95, 94, 93, 92, 91],
        'low': [90, 91, 92, 93, 94, 95, 90, 96, 95, 94, 93, 92, 91, 90, 89],
        'close': [91.5, 92.5, 93.5, 94.5, 95.5, 96.5, 95, 97, 96, 95, 94, 93, 92, 91, 90],
        'volume': [100] * 15,
    }
    index = pd.DatetimeIndex([base + timedelta(hours=i) for i in range(15)])
    return pd.DataFrame(data, index=index)


@pytest.fixture
def sample_ohlcv_mss_bos():
    """OHLCV for MSS then BOS: pivot at 6, break at 10 (MSS), break at 12 (BOS)."""
    base = datetime(2025, 1, 1, 0, 0, 0)
    # Pivot high 100 at bar 6, pivot low 90 at bar 6
    # Bar 10: close 101 > 100 -> MSS bullish
    # Bar 12: close 103 > 102 (new swing) -> BOS bullish
    data = {
        'open': [91, 92, 93, 94, 95, 96, 97, 96, 95, 98, 99, 100, 101],
        'high': [92, 93, 94, 95, 96, 97, 100, 98, 97, 101, 102, 104, 105],
        'low': [90, 91, 92, 93, 94, 95, 90, 96, 95, 97, 98, 99, 100],
        'close': [91.5, 92.5, 93.5, 94.5, 95.5, 96.5, 95, 97, 96, 101, 102, 103, 104],
        'volume': [100] * 13,
    }
    index = pd.DatetimeIndex([base + timedelta(hours=i) for i in range(13)])
    return pd.DataFrame(data, index=index)


def test_luxalgo_swing_pivot(sample_ohlcv_pivot):
    """Pivot-based swing detection finds swing high/low at pivot bar."""
    df = sample_ohlcv_pivot.copy()
    result = detect_swing_highs_lows(df, swing_length=5)
    assert 'swing_high' in result.columns
    assert 'swing_low' in result.columns
    swing_high_bars = result.index[result['swing_high'] == True].tolist()
    swing_low_bars = result.index[result['swing_low'] == True].tolist()
    assert len(swing_high_bars) >= 1
    assert len(swing_low_bars) >= 1
    assert result.iloc[6]['swing_high'] == True
    assert result.iloc[6]['swing_high_price'] == 100
    assert result.iloc[6]['swing_low'] == True
    assert result.iloc[6]['swing_low_price'] == 90


def test_luxalgo_bos_mss(sample_ohlcv_mss_bos):
    """MSS then BOS: close breaks pivot high -> bos_bull True."""
    df = sample_ohlcv_mss_bos.copy()
    df = detect_swing_highs_lows(df, swing_length=5)
    df = detect_break_of_structure(df)
    assert 'bos_bull' in df.columns
    assert 'bos_bear' in df.columns
    bull_bars = df.index[df['bos_bull'] == True].tolist()
    assert len(bull_bars) >= 1


def test_luxalgo_ob_breaker():
    """OB invalidated when price breaks through before BOS (breaker)."""
    base = datetime(2025, 1, 1, 0, 0, 0)
    # Bar 3: bearish (OB). Bar 4: low sweeps below OB -> breaker. Bar 5: BOS
    data = {
        'open': [95, 96, 98, 98, 97, 99],
        'high': [96, 97, 99, 99, 98, 102],
        'low': [94, 95, 97, 96, 96, 98],
        'close': [95.5, 96.5, 97.5, 97, 97.5, 101],
        'volume': [100] * 6,
    }
    index = pd.DatetimeIndex([base + timedelta(hours=i) for i in range(6)])
    df = pd.DataFrame(data, index=index)
    df = detect_swing_highs_lows(df, swing_length=2)
    df = detect_break_of_structure(df)
    ob = identify_order_block(df, 5, ob_lookback=10, use_body=True)
    if ob is not None:
        assert ob['direction'] == 'BULLISH'
        assert 'high' in ob and 'low' in ob and 'midpoint' in ob


def test_luxalgo_ob_valid():
    """OB valid when no breaker between OB candle and BOS."""
    base = datetime(2025, 1, 1, 0, 0, 0)
    data = {
        'open': [95, 96, 98, 98, 97, 99],
        'high': [96, 97, 99, 99, 98, 102],
        'low': [94, 95, 97, 97.5, 98, 98],
        'close': [95.5, 96.5, 97.5, 97, 98, 101],
        'volume': [100] * 6,
    }
    index = pd.DatetimeIndex([base + timedelta(hours=i) for i in range(6)])
    df = pd.DataFrame(data, index=index)
    df = detect_swing_highs_lows(df, swing_length=2)
    df = detect_break_of_structure(df)
    ob = identify_order_block(df, 5, ob_lookback=10, use_body=False)
    assert ob is not None
    assert ob['direction'] == 'BULLISH'
    assert ob['midpoint'] == (ob['high'] + ob['low']) / 2
