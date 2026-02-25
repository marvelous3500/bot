"""
LQ (Liquidity Sweep) indicators: session high/low, external sweep (PDH/PDL, session),
internal sweep (swing high/low).
"""
import pandas as pd
import numpy as np
from typing import Optional, Tuple, Dict, Any

try:
    import config
except ImportError:
    config = None


def get_session_for_hour(
    hour_utc: int,
    session_hours: Dict[str, Tuple[int, int]],
) -> Optional[str]:
    """Return session name if hour falls in a session window, else None."""
    for name, (start, end) in session_hours.items():
        if start <= hour_utc < end:
            return name
    return None


def get_session_high_low(
    df_m15: pd.DataFrame,
    bar_time,
    session_name: str,
    session_hours: Dict[str, Tuple[int, int]],
) -> Tuple[Optional[float], Optional[float]]:
    """
    Return (session_high, session_low) for the given session on the bar's date.
    session_hours: {session_name: (start_hour, end_hour)} UTC, end exclusive.
    Filters M15 bars by date and hour range.
    """
    if df_m15 is None or df_m15.empty:
        return None, None
    if session_name not in session_hours:
        return None, None
    start_h, end_h = session_hours[session_name]
    if hasattr(bar_time, 'normalize'):
        bar_date = bar_time.normalize()
    else:
        bar_date = pd.Timestamp(bar_time).normalize()
    if not isinstance(df_m15.index, pd.DatetimeIndex):
        df_m15 = df_m15.copy()
        df_m15.index = pd.to_datetime(df_m15.index)
    mask_date = df_m15.index.normalize() == bar_date
    hours = df_m15.index.hour
    mask_hour = (hours >= start_h) & (hours < end_h)
    session_bars = df_m15.loc[mask_date & mask_hour]
    if session_bars.empty:
        return None, None
    return float(session_bars['high'].max()), float(session_bars['low'].min())


def detect_external_sweep(
    open_: float,
    high: float,
    low: float,
    close: float,
    pdh: Optional[float],
    pdl: Optional[float],
    session_high: Optional[float],
    session_low: Optional[float],
) -> Dict[str, Any]:
    """
    Detect external liquidity sweep (PDH/PDL, session high/low).
    Returns dict with: sweep_pdh (bearish), sweep_pdl (bullish),
    sweep_session_high (bearish), sweep_session_low (bullish).
    Sweep above level: high > level and close < level.
    Sweep below level: low < level and close > level.
    """
    result = {
        'sweep_pdh': False,
        'sweep_pdl': False,
        'sweep_session_high': False,
        'sweep_session_low': False,
        'sweep_type': None,
        'direction': None,
    }
    if pdh is not None and high > pdh and close < pdh:
        result['sweep_pdh'] = True
        result['sweep_type'] = 'pdh'
        result['direction'] = 'bearish'
        return result
    if pdl is not None and low < pdl and close > pdl:
        result['sweep_pdl'] = True
        result['sweep_type'] = 'pdl'
        result['direction'] = 'bullish'
        return result
    if session_high is not None and high > session_high and close < session_high:
        result['sweep_session_high'] = True
        result['sweep_type'] = 'session_high'
        result['direction'] = 'bearish'
        return result
    if session_low is not None and low < session_low and close > session_low:
        result['sweep_session_low'] = True
        result['sweep_type'] = 'session_low'
        result['direction'] = 'bullish'
        return result
    return result


def detect_internal_sweep(
    df: pd.DataFrame,
    swing_high_col: str = 'swing_high_price',
    swing_low_col: str = 'swing_low_price',
    lookback: int = 10,
) -> pd.DataFrame:
    """
    Add sweep_high_internal and sweep_low_internal columns.
    Sweep of recent swing high (bearish): high > last swing high, close < last swing high.
    Sweep of recent swing low (bullish): low < last swing low, close > last swing low.
    Uses forward-fill of swing prices for the "last known" level.
    """
    df = df.copy()
    df['sweep_high_internal'] = False
    df['sweep_low_internal'] = False
    if swing_high_col not in df.columns or swing_low_col not in df.columns:
        return df
    sh = df[swing_high_col].replace(0, np.nan)
    sl = df[swing_low_col].replace(0, np.nan)
    last_swing_high = sh.ffill().shift(1)
    last_swing_low = sl.ffill().shift(1)
    for i in range(lookback, len(df)):
        lsh = last_swing_high.iloc[i]
        lsl = last_swing_low.iloc[i]
        if pd.isna(lsh):
            lsh = None
        if pd.isna(lsl):
            lsl = None
        h = df.iloc[i]['high']
        l_ = df.iloc[i]['low']
        c = df.iloc[i]['close']
        if lsh is not None and h > lsh and c < lsh:
            df.iloc[i, df.columns.get_loc('sweep_high_internal')] = True
        if lsl is not None and l_ < lsl and c > lsl:
            df.iloc[i, df.columns.get_loc('sweep_low_internal')] = True
    return df
