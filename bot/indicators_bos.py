import pandas as pd
import numpy as np

def detect_swing_highs_lows(df, swing_length=3):
    """Detects swing highs and swing lows using fractal logic."""
    df['swing_high'] = False
    df['swing_low'] = False
    df['swing_high_price'] = np.nan
    df['swing_low_price'] = np.nan

    for i in range(swing_length, len(df) - swing_length):
        is_swing_high = True
        center_high = df.iloc[i]['high']
        for j in range(1, swing_length + 1):
            if df.iloc[i - j]['high'] >= center_high:
                is_swing_high = False
                break
        if is_swing_high:
            for j in range(1, swing_length + 1):
                if df.iloc[i + j]['high'] >= center_high:
                    is_swing_high = False
                    break
        if is_swing_high:
            df.iloc[i, df.columns.get_loc('swing_high')] = True
            df.iloc[i, df.columns.get_loc('swing_high_price')] = center_high

        is_swing_low = True
        center_low = df.iloc[i]['low']
        for j in range(1, swing_length + 1):
            if df.iloc[i - j]['low'] <= center_low:
                is_swing_low = False
                break
        if is_swing_low:
            for j in range(1, swing_length + 1):
                if df.iloc[i + j]['low'] <= center_low:
                    is_swing_low = False
                    break
        if is_swing_low:
            df.iloc[i, df.columns.get_loc('swing_low')] = True
            df.iloc[i, df.columns.get_loc('swing_low_price')] = center_low

    return df

def detect_break_of_structure(df):
    """Detects Break of Structure (BOS)."""
    df['bos_bull'] = False
    df['bos_bear'] = False
    df['bos_direction'] = None
    swing_highs = df[df['swing_high'] == True].copy()
    swing_lows = df[df['swing_low'] == True].copy()
    if swing_highs.empty or swing_lows.empty:
        return df
    last_swing_high = None
    last_swing_low = None
    for i in range(len(df)):
        row = df.iloc[i]
        if row['swing_high']:
            last_swing_high = row['swing_high_price']
        if row['swing_low']:
            last_swing_low = row['swing_low_price']
        if last_swing_high is not None and row['close'] > last_swing_high:
            df.iloc[i, df.columns.get_loc('bos_bull')] = True
            df.iloc[i, df.columns.get_loc('bos_direction')] = 'BULLISH'
            last_swing_high = row['high']
        if last_swing_low is not None and row['close'] < last_swing_low:
            df.iloc[i, df.columns.get_loc('bos_bear')] = True
            df.iloc[i, df.columns.get_loc('bos_direction')] = 'BEARISH'
            last_swing_low = row['low']
    return df

def identify_order_block(df, bos_index, ob_lookback=20):
    """Identifies the order block before a BOS."""
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
                return {
                    'high': candle['high'],
                    'low': candle['low'],
                    'midpoint': (candle['high'] + candle['low']) / 2,
                    'time': df.index[i],
                    'direction': 'BULLISH'
                }
        elif bos_direction == 'BEARISH':
            if candle['close'] > candle['open']:
                return {
                    'high': candle['high'],
                    'low': candle['low'],
                    'midpoint': (candle['high'] + candle['low']) / 2,
                    'time': df.index[i],
                    'direction': 'BEARISH'
                }
    return None

def detect_shallow_tap(price_low, price_high, ob_high, ob_low, ob_midpoint):
    """Checks if price tapped into the OB."""
    entered_ob = price_low <= ob_high and price_high >= ob_low
    return entered_ob


def higher_tf_bias_aligned(df_higher, idx, bias_str):
    """Check if higher TF has BOS matching bias at idx. Returns True if aligned, False if not."""
    if df_higher is None or df_higher.empty:
        return True
    bars = df_higher[df_higher.index <= idx]
    if bars.empty:
        return False
    row = bars.iloc[-1]
    if not row.get('bos_bull') and not row.get('bos_bear'):
        return False
    higher_bias = 'BULLISH' if row.get('bos_bull') else 'BEARISH'
    return higher_bias == bias_str
