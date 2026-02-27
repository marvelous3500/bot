"""
LuxAlgo-style ICT indicators (pivot swings, MSS/BOS, order blocks with breaker).

Parity implementation of LuxAlgo ICT Concepts for use when USE_LUXALGO_ICT=True.
Uses pivot-based swing detection (ta.pivothigh/ta.pivotlow) instead of fractal,
MSS (Market Structure Shift) + BOS (Break of Structure), and order blocks with
breaker invalidation.

Config: USE_LUXALGO_ICT, LUXALGO_SWING_LENGTH, LUXALGO_OB_USE_BODY
"""
import pandas as pd
import numpy as np


def _pivot_high(high_series, left, right=1):
    """Pivot high: bar at (current - left - right) is highest in window."""
    result = pd.Series(index=high_series.index, dtype=float)
    arr = high_series.values
    n = len(arr)
    for i in range(left + right, n):
        pivot_idx = i - left - right
        start = max(0, pivot_idx - left)
        end = min(n, pivot_idx + right + 1)
        window_max = np.max(arr[start:end])
        if arr[pivot_idx] >= window_max:
            result.iloc[pivot_idx] = arr[pivot_idx]
    return result


def _pivot_low(low_series, left, right=1):
    """Pivot low: bar at (current - left - right) is lowest in window."""
    result = pd.Series(index=low_series.index, dtype=float)
    arr = low_series.values
    n = len(arr)
    for i in range(left + right, n):
        pivot_idx = i - left - right
        start = max(0, pivot_idx - left)
        end = min(n, pivot_idx + right + 1)
        window_min = np.min(arr[start:end])
        if arr[pivot_idx] <= window_min:
            result.iloc[pivot_idx] = arr[pivot_idx]
    return result


def detect_swing_highs_lows(df, swing_length=5):
    """Detects swing highs and lows using pivot logic (LuxAlgo ta.pivothigh/ta.pivotlow)."""
    df = df.copy()
    right = 1
    ph = _pivot_high(df['high'], swing_length, right)
    pl = _pivot_low(df['low'], swing_length, right)

    df['swing_high'] = ~ph.isna()
    df['swing_low'] = ~pl.isna()
    df['swing_high_price'] = ph
    df['swing_low_price'] = pl
    return df


def detect_break_of_structure(df):
    """Detects MSS (Market Structure Shift) and BOS (Break of Structure). Adds broken level for entry-TF confirmation."""
    df = df.copy()
    df['bos_bull'] = False
    df['bos_bear'] = False
    df['bos_direction'] = None
    df['bos_bull_broken_level'] = np.nan
    df['bos_bear_broken_level'] = np.nan

    last_swing_high = None
    last_swing_low = None
    mss_dir = 0  # -1 bearish, 0 neutral, 1 bullish

    for i in range(len(df)):
        row = df.iloc[i]
        if row['swing_high']:
            last_swing_high = row['swing_high_price']
        if row['swing_low']:
            last_swing_low = row['swing_low_price']

        if last_swing_high is not None and row['close'] > last_swing_high:
            if mss_dir < 1:
                mss_dir = 1
            df.iloc[i, df.columns.get_loc('bos_bull')] = True
            df.iloc[i, df.columns.get_loc('bos_direction')] = 'BULLISH'
            df.iloc[i, df.columns.get_loc('bos_bull_broken_level')] = last_swing_high
            last_swing_high = row['high']

        if last_swing_low is not None and row['close'] < last_swing_low:
            if mss_dir > -1:
                mss_dir = -1
            df.iloc[i, df.columns.get_loc('bos_bear')] = True
            df.iloc[i, df.columns.get_loc('bos_direction')] = 'BEARISH'
            df.iloc[i, df.columns.get_loc('bos_bear_broken_level')] = last_swing_low
            last_swing_low = row['low']

    return df


def identify_order_block(df, bos_index, ob_lookback=20, use_body=True):
    """Identifies order block before BOS, with breaker invalidation (LuxAlgo-style)."""
    if bos_index <= 0:
        return None
    bos_row = df.iloc[bos_index]
    bos_direction = bos_row['bos_direction']
    if pd.isna(bos_direction):
        return None

    for i in range(bos_index - 1, max(0, bos_index - ob_lookback), -1):
        candle = df.iloc[i]
        if bos_direction == 'BULLISH':
            if candle['close'] < candle['open']:
                ob_high = max(candle['open'], candle['close']) if use_body else candle['high']
                ob_low = min(candle['open'], candle['close']) if use_body else candle['low']
                ob_mid = (ob_high + ob_low) / 2
                for j in range(i + 1, bos_index):
                    if df.iloc[j]['low'] < ob_low:
                        return None
                return {
                    'high': ob_high,
                    'low': ob_low,
                    'midpoint': ob_mid,
                    'time': df.index[i],
                    'direction': 'BULLISH'
                }
        elif bos_direction == 'BEARISH':
            if candle['close'] > candle['open']:
                ob_high = max(candle['open'], candle['close']) if use_body else candle['high']
                ob_low = min(candle['open'], candle['close']) if use_body else candle['low']
                ob_mid = (ob_high + ob_low) / 2
                for j in range(i + 1, bos_index):
                    if df.iloc[j]['high'] > ob_high:
                        return None
                return {
                    'high': ob_high,
                    'low': ob_low,
                    'midpoint': ob_mid,
                    'time': df.index[i],
                    'direction': 'BEARISH'
                }
    return None
