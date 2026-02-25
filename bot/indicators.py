import pandas as pd
from typing import Optional, List, Tuple


def calculate_pdl_pdh(daily_df, current_date):
    """
    Returns the Previous Day High (PDH) and Previous Day Low (PDL)
    relative to the 'current_date'.

    daily_df: DataFrame with daily OHLC data.
    current_date: datetime object of the current trading day.
    """
    if not isinstance(daily_df.index, pd.DatetimeIndex):
        daily_df.index = pd.to_datetime(daily_df.index)

    mask = daily_df.index < current_date.normalize()
    past_data = daily_df.loc[mask]

    if past_data.empty:
        return None, None

    prev_day = past_data.iloc[-1]
    return prev_day['high'], prev_day['low']

def detect_fvg(df, lookback=3):
    """Adds is_fvg_bullish and is_fvg_bearish columns. ICT FVG."""
    df['fvg_bull'] = False
    df['fvg_bear'] = False
    c1_high = df['high'].shift(2)
    c1_low = df['low'].shift(2)
    c3_high = df['high']
    c3_low = df['low']
    df.loc[(c3_low > c1_high), 'fvg_bull'] = True
    df.loc[(c3_high < c1_low), 'fvg_bear'] = True
    return df

def detect_order_block(df):
    """Adds is_ob_bull and is_ob_bear columns."""
    df['ob_bull'] = False
    df['ob_bear'] = False
    prev_open = df['open'].shift(1)
    prev_close = df['close'].shift(1)
    curr_open = df['open']
    curr_close = df['close']
    is_prev_red = prev_close < prev_open
    is_curr_green = curr_close > curr_open
    is_engulfing_bull = (curr_close > prev_open) & (curr_open < prev_close)
    df.loc[is_prev_red & is_curr_green & is_engulfing_bull, 'ob_bull'] = True
    is_prev_green = prev_close > prev_open
    is_curr_red = curr_close < curr_open
    is_engulfing_bear = (curr_close < prev_open) & (curr_open > prev_close)
    df.loc[is_prev_green & is_curr_red & is_engulfing_bear, 'ob_bear'] = True
    return df

def detect_liquidity_sweep(df, lookback=5):
    """Detects if the current candle swept a high/low from the last lookback candles."""
    df['sweep_high'] = False
    df['sweep_low'] = False
    recent_high = df['high'].shift(1).rolling(window=lookback).max()
    recent_low = df['low'].shift(1).rolling(window=lookback).min()
    df.loc[(df['high'] > recent_high) & (df['close'] < recent_high), 'sweep_high'] = True
    df.loc[(df['low'] < recent_low) & (df['close'] > recent_low), 'sweep_low'] = True
    return df

def calculate_ema(df, period=200):
    """Calculates Exponential Moving Average."""
    df[f'ema_{period}'] = df['close'].ewm(span=period, adjust=False).mean()
    return df

def detect_rejection_candle(df, wick_ratio=0.55):
    """Adds rejection_bull (pin bar with long lower wick) and rejection_bear (long upper wick)."""
    df['rejection_bull'] = False
    df['rejection_bear'] = False
    rng = df['high'] - df['low']
    rng = rng.replace(0, 1e-10)  # avoid div by zero
    lower_wick = df[['open', 'close']].min(axis=1) - df['low']
    upper_wick = df['high'] - df[['open', 'close']].max(axis=1)
    df.loc[(lower_wick / rng > wick_ratio) & (df['close'] > df['open']), 'rejection_bull'] = True
    df.loc[(upper_wick / rng > wick_ratio) & (df['close'] < df['open']), 'rejection_bear'] = True
    return df


def get_equilibrium(df: pd.DataFrame, lookback: int) -> Optional[float]:
    """
    ICT equilibrium: 50% of high-low range over lookback bars.
    Returns (range_high + range_low) / 2, or None if insufficient data.
    """
    if df is None or df.empty or len(df) < 2:
        return None
    slice_df = df.tail(lookback)
    if slice_df.empty:
        return None
    rng_high = slice_df["high"].max()
    rng_low = slice_df["low"].min()
    return (rng_high + rng_low) / 2


def get_equilibrium_from_daily(daily_df: pd.DataFrame, current_date) -> Optional[float]:
    """
    ICT equilibrium from PDH/PDL: 50% of previous day's range.
    """
    pdh, pdl = calculate_pdl_pdh(daily_df, current_date)
    if pdh is None or pdl is None:
        return None
    return (pdh + pdl) / 2


def detect_displacement(df, threshold=1.5, window=10):
    """Detects displacement: body > average of previous N candles (default 10 per spec)."""
    df = df.copy()
    df['displacement_bull'] = False
    df['displacement_bear'] = False
    df['body_size'] = abs(df['close'] - df['open'])
    df['avg_body'] = df['body_size'].rolling(window=window).mean()
    is_green = df['close'] > df['open']
    is_large_bull = df['body_size'] > (df['avg_body'] * threshold)
    df.loc[is_green & is_large_bull, 'displacement_bull'] = True
    is_red = df['close'] < df['open']
    is_large_bear = df['body_size'] > (df['avg_body'] * threshold)
    df.loc[is_red & is_large_bear, 'displacement_bear'] = True
    return df


def get_recent_fvg_zones(
    df: pd.DataFrame,
    lookback: int,
    end_idx: Optional[int] = None,
) -> List[Tuple[float, float, str]]:
    """
    Return list of (zone_top, zone_bottom, direction) for FVGs in the last lookback bars.
    zone_top >= zone_bottom. BULLISH = demand/Sellside; BEARISH = supply/Buyside.
    Requires fvg_bull, fvg_bear columns (run detect_fvg first).
    """
    if df is None or df.empty or len(df) < 3:
        return []
    if "fvg_bull" not in df.columns or "fvg_bear" not in df.columns:
        return []
    end = end_idx if end_idx is not None else len(df)
    start = max(2, end - lookback)
    zones = []
    for i in range(start, end):
        if i >= len(df):
            break
        row = df.iloc[i]
        if row.get("fvg_bull"):
            zone_bottom = float(df.iloc[i - 2]["high"])
            zone_top = float(row["low"])
            if zone_top >= zone_bottom:
                zones.append((zone_top, zone_bottom, "BULLISH"))
        if row.get("fvg_bear"):
            zone_top = float(df.iloc[i - 2]["low"])
            zone_bottom = float(row["high"])
            if zone_top >= zone_bottom:
                zones.append((zone_top, zone_bottom, "BEARISH"))
    return zones


def _price_in_zone(price: float, zone_top: float, zone_bottom: float, buffer_pct: float = 0.0) -> bool:
    """True if price is inside [zone_bottom, zone_top] with optional buffer (fraction of price)."""
    if buffer_pct > 0:
        buf = price * buffer_pct
        return zone_bottom - buf <= price <= zone_top + buf
    return zone_bottom <= price <= zone_top


def price_in_buyside_liquidity(
    entry_price: float,
    df: pd.DataFrame,
    lookback: int = 30,
    equilibrium: Optional[float] = None,
    buffer_pct: float = 0.001,
    use_equilibrium: bool = True,
) -> bool:
    """
    True if entry is in Buyside liquidity (supply): bearish FVG zone or above equilibrium.
    Caller should block BUY when this returns True.
    """
    if df is None or df.empty:
        if use_equilibrium and equilibrium is not None and entry_price > equilibrium:
            return True
        return False
    zones = get_recent_fvg_zones(df, lookback)
    for zone_top, zone_bottom, direction in zones:
        if direction == "BEARISH" and _price_in_zone(entry_price, zone_top, zone_bottom, buffer_pct):
            return True
    if use_equilibrium and equilibrium is not None and entry_price > equilibrium:
        return True
    return False


def price_in_sellside_liquidity(
    entry_price: float,
    df: pd.DataFrame,
    lookback: int = 30,
    equilibrium: Optional[float] = None,
    buffer_pct: float = 0.001,
    use_equilibrium: bool = True,
) -> bool:
    """
    True if entry is in Sellside liquidity (demand): bullish FVG zone or below equilibrium.
    Caller should block SELL when this returns True.
    """
    if df is None or df.empty:
        if use_equilibrium and equilibrium is not None and entry_price < equilibrium:
            return True
        return False
    zones = get_recent_fvg_zones(df, lookback)
    for zone_top, zone_bottom, direction in zones:
        if direction == "BULLISH" and _price_in_zone(entry_price, zone_top, zone_bottom, buffer_pct):
            return True
    if use_equilibrium and equilibrium is not None and entry_price < equilibrium:
        return True
    return False
