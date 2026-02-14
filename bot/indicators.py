import pandas as pd


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


def detect_displacement(df, threshold=1.5):
    """Detects displacement: strong candles that indicate institutional activity."""
    df['displacement_bull'] = False
    df['displacement_bear'] = False
    df['body_size'] = abs(df['close'] - df['open'])
    df['avg_body'] = df['body_size'].rolling(window=20).mean()
    is_green = df['close'] > df['open']
    is_large_bull = df['body_size'] > (df['avg_body'] * threshold)
    df.loc[is_green & is_large_bull, 'displacement_bull'] = True
    is_red = df['close'] < df['open']
    is_large_bear = df['body_size'] > (df['avg_body'] * threshold)
    df.loc[is_red & is_large_bear, 'displacement_bear'] = True
    return df
