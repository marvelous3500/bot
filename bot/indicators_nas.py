"""
NAS-STRATEGY specific indicators.
Liquidity sweep with size, FVG with size/age validation.
"""
import pandas as pd
import numpy as np

from .indicators_bos import detect_swing_highs_lows
from .indicators import detect_fvg


def detect_liquidity_sweep_m15(df, lookback=5, min_sweep_points=None):
    """
    Detect liquidity sweep using swing highs/lows. Price wicks beyond swing then closes back inside.
    Returns DataFrame with sweep_high, sweep_low, sweep_high_price, sweep_low_price,
    sweep_high_size, sweep_low_size (points beyond swing).
    """
    if 'swing_high' not in df.columns:
        df = detect_swing_highs_lows(df, swing_length=3)
    df = df.copy()
    df['sweep_high'] = False
    df['sweep_low'] = False
    df['sweep_high_price'] = np.nan
    df['sweep_low_price'] = np.nan
    df['sweep_high_size'] = 0.0
    df['sweep_low_size'] = 0.0

    recent_highs = df[df['swing_high'] == True][['swing_high_price']].copy()
    recent_lows = df[df['swing_low'] == True][['swing_low_price']].copy()

    for i in range(lookback, len(df)):
        row = df.iloc[i]
        past_highs = df.iloc[max(0, i - lookback):i]
        past_lows = df.iloc[max(0, i - lookback):i]
        sh = past_highs[past_highs['swing_high'] == True]['swing_high_price']
        sl = past_lows[past_lows['swing_low'] == True]['swing_low_price']
        if not sh.empty:
            liq_high = float(sh.iloc[-1])
            if row['high'] > liq_high and row['close'] < liq_high:
                df.iloc[i, df.columns.get_loc('sweep_high')] = True
                df.iloc[i, df.columns.get_loc('sweep_high_price')] = row['low']
                size = row['high'] - liq_high
                df.iloc[i, df.columns.get_loc('sweep_high_size')] = size
        if not sl.empty:
            liq_low = float(sl.iloc[-1])
            if row['low'] < liq_low and row['close'] > liq_low:
                df.iloc[i, df.columns.get_loc('sweep_low')] = True
                df.iloc[i, df.columns.get_loc('sweep_low_price')] = row['high']
                size = liq_low - row['low']
                df.iloc[i, df.columns.get_loc('sweep_low_size')] = size

    return df


def detect_liquidity_sweep(df, lookback=5, min_sweep_points=0):
    """
    Detect liquidity sweep. Returns per-bar result dict.
    For bar at index i: {swept: bool, level: float, size: float, direction: 'high'|'low', reason: str}
    """
    df = detect_liquidity_sweep_m15(df, lookback=lookback)

    def _get_sweep(i):
        row = df.iloc[i]
        if row.get('sweep_high'):
            size = row.get('sweep_high_size', 0)
            if min_sweep_points and size < min_sweep_points:
                return {"swept": False, "level": None, "size": size, "direction": "high",
                        "reason": f"sweep too small ({size:.1f} < {min_sweep_points})"}
            return {"swept": True, "level": row['sweep_high_price'], "size": size, "direction": "high",
                    "reason": "liquidity sweep high"}
        if row.get('sweep_low'):
            size = row.get('sweep_low_size', 0)
            if min_sweep_points and size < min_sweep_points:
                return {"swept": False, "level": None, "size": size, "direction": "low",
                        "reason": f"sweep too small ({size:.1f} < {min_sweep_points})"}
            return {"swept": True, "level": row['sweep_low_price'], "size": size, "direction": "low",
                    "reason": "liquidity sweep low"}
        return {"swept": False, "level": None, "size": 0, "direction": None, "reason": "no sweep"}

    return _get_sweep


def get_fvg_zones(df, min_fvg_size=0, max_fvg_age=None, current_bar_idx=None):
    """
    Get FVG zones with size and age. Returns list of {top, bottom, size, bar_index, age, direction}.
    """
    if 'fvg_bull' not in df.columns:
        df = detect_fvg(df)
    zones = []
    for i in range(2, len(df)):
        row = df.iloc[i]
        if row.get('fvg_bull'):
            c1_high = df.iloc[i - 2]['high']
            c3_low = row['low']
            top, bottom = c3_low, c1_high
            if top <= bottom:
                continue
            size = top - bottom
            if min_fvg_size and size < min_fvg_size:
                continue
            age = (current_bar_idx - i) if current_bar_idx is not None else 0
            if max_fvg_age is not None and age > max_fvg_age:
                continue
            zones.append({"top": top, "bottom": bottom, "size": size, "bar_index": i, "age": age, "direction": "bull"})
        if row.get('fvg_bear'):
            c1_low = df.iloc[i - 2]['low']
            c3_high = row['high']
            top, bottom = c3_high, c1_low
            if top <= bottom:
                continue
            size = top - bottom
            if min_fvg_size and size < min_fvg_size:
                continue
            age = (current_bar_idx - i) if current_bar_idx is not None else 0
            if max_fvg_age is not None and age > max_fvg_age:
                continue
            zones.append({"top": top, "bottom": bottom, "size": size, "bar_index": i, "age": age, "direction": "bear"})
    return zones
