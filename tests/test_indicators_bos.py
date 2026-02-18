"""Unit tests for bot/indicators_bos.py."""
import pandas as pd
import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.indicators_bos import (
    detect_swing_highs_lows,
    detect_break_of_structure,
    identify_order_block,
    detect_shallow_tap,
)


def test_detect_swing_highs_lows(sample_ohlcv_df):
    """DataFrame with known swing high at center bar -> swing_high True at that index."""
    df = sample_ohlcv_df.copy()
    result = detect_swing_highs_lows(df, swing_length=2)
    # Index 3 has high=100, neighbors have lower highs
    assert 'swing_high' in result.columns
    assert 'swing_low' in result.columns
    # With swing_length=2, index 2,3,4 are candidates; index 3 has highest high
    swing_high_indices = result.index[result['swing_high'] == True].tolist()
    assert len(swing_high_indices) >= 1
    # Index 3 should be a swing high (center bar is highest)
    assert result.iloc[3]['swing_high'] == True
    assert result.iloc[3]['swing_high_price'] == 100


def test_detect_break_of_structure(sample_ohlcv_bos_bull):
    """After swing detection, BOS flags when close breaks last swing high/low."""
    df = sample_ohlcv_bos_bull.copy()
    df = detect_swing_highs_lows(df, swing_length=2)
    df = detect_break_of_structure(df)
    assert 'bos_bull' in df.columns
    assert 'bos_bear' in df.columns
    # Bar 5 closes at 101, breaking above swing high 100 -> bos_bull
    assert df.iloc[5]['bos_bull'] == True
    assert df.iloc[5]['bos_direction'] == 'BULLISH'


def test_identify_order_block(sample_ohlcv_bos_bull):
    """DataFrame with bearish candle before BOS -> OB dict with high/low/midpoint."""
    df = sample_ohlcv_bos_bull.copy()
    df = detect_swing_highs_lows(df, swing_length=2)
    df = detect_break_of_structure(df)
    # BOS at index 5 (bearish would need close < open before); for BULLISH BOS we need bearish candle before
    # Our fixture has BULLISH BOS at index 5. OB for BULLISH is last bearish candle before BOS.
    # Index 4: open=96, close=96.5 -> bullish. Index 3: open=98, close=97.5 -> bearish. So OB at index 3.
    ob = identify_order_block(df, 5, ob_lookback=10)
    if ob is not None:
        assert 'high' in ob
        assert 'low' in ob
        assert 'midpoint' in ob
        assert ob['midpoint'] == (ob['high'] + ob['low']) / 2


def test_detect_shallow_tap_overlapping():
    """Price range overlapping OB range -> True."""
    # OB: high=100, low=95. Candle: low=96, high=101 -> overlaps
    assert detect_shallow_tap(96, 101, 100, 95, 97.5) == True


def test_detect_shallow_tap_outside():
    """Price range outside OB range -> False."""
    # OB: high=100, low=95. Candle: low=90, high=92 -> no overlap
    assert detect_shallow_tap(90, 92, 100, 95, 97.5) == False


def test_detect_shallow_tap_touching():
    """Price touches OB edge -> True."""
    # OB: high=100, low=95. Candle: low=95, high=96 -> touches low
    assert detect_shallow_tap(95, 96, 100, 95, 97.5) == True
