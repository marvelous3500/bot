import pandas as pd
import numpy as np

try:
    import config
except ImportError:
    config = None


def detect_swing_highs_lows(df, swing_length=3):
    """Detects swing highs and lows. Dispatches to LuxAlgo or Kingsley per config."""
    if config and getattr(config, 'USE_LUXALGO_ICT', False):
        from .indicators_luxalgo import detect_swing_highs_lows as _lux
        return _lux(df, swing_length=getattr(config, 'LUXALGO_SWING_LENGTH', 5))
    return _detect_swing_fractal(df, swing_length)


def _detect_swing_fractal(df, swing_length=3):
    """Detects swing highs and swing lows using fractal logic (Kingsley)."""
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
    """Detects BOS/MSS. Dispatches to LuxAlgo or Kingsley per config."""
    if config and getattr(config, 'USE_LUXALGO_ICT', False):
        from .indicators_luxalgo import detect_break_of_structure as _lux
        return _lux(df)
    return _detect_bos_kingsley(df)


def _detect_bos_kingsley(df):
    """Detects Break of Structure (Kingsley). Adds broken level for entry-TF confirmation (fake vs real BOS)."""
    df['bos_bull'] = False
    df['bos_bear'] = False
    df['bos_direction'] = None
    df['bos_bull_broken_level'] = np.nan
    df['bos_bear_broken_level'] = np.nan
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
            df.iloc[i, df.columns.get_loc('bos_bull_broken_level')] = last_swing_high
            last_swing_high = row['high']
        if last_swing_low is not None and row['close'] < last_swing_low:
            df.iloc[i, df.columns.get_loc('bos_bear')] = True
            df.iloc[i, df.columns.get_loc('bos_direction')] = 'BEARISH'
            df.iloc[i, df.columns.get_loc('bos_bear_broken_level')] = last_swing_low
            last_swing_low = row['low']
    return df


def is_bos_still_valid_on_entry_df(
    df_1m: pd.DataFrame,
    bos_time,
    current_time,
    broken_level: float,
    direction: str,
) -> bool:
    """
    Return True if the BOS has not been invalidated on the entry TF (1m).
    Invalidated = any 1m bar after BOS time closed back through the broken level.
    direction: 'BULLISH' -> broken level was swing high; invalidation = close < level.
    direction: 'BEARISH' -> broken level was swing low; invalidation = close > level.
    """
    if df_1m is None or df_1m.empty or broken_level is None or pd.isna(broken_level):
        return True
    bos_ts = pd.Timestamp(bos_time)
    cur_ts = pd.Timestamp(current_time)
    if cur_ts <= bos_ts:
        return True
    subset = df_1m[(df_1m.index > bos_ts) & (df_1m.index <= cur_ts)]
    if subset.empty:
        return True
    if direction == "BULLISH":
        if (subset["close"] < broken_level).any():
            return False
    else:
        if (subset["close"] > broken_level).any():
            return False
    return True


def identify_order_block(df, bos_index, ob_lookback=20):
    """Identifies order block before BOS. Dispatches to LuxAlgo or Kingsley per config."""
    if config and getattr(config, 'USE_LUXALGO_ICT', False):
        from .indicators_luxalgo import identify_order_block as _lux
        use_body = getattr(config, 'LUXALGO_OB_USE_BODY', True)
        return _lux(df, bos_index, ob_lookback=ob_lookback, use_body=use_body)
    return _identify_ob_kingsley(df, bos_index, ob_lookback=ob_lookback)


def _identify_ob_kingsley(df, bos_index, ob_lookback=20):
    """Identifies the order block before a BOS (Kingsley)."""
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

def detect_breaker_block(df, bias, ob_lookback=20, use_body=True):
    """
    Find a breaker block (invalidated OB) that aligns with bias.
    - Bullish bias: need failed bearish OB (price swept ob_low before BOS)
    - Bearish bias: need failed bullish OB (price swept ob_high before BOS)
    Returns zone {high, low, midpoint, direction} or None.
    """
    if df is None or df.empty or len(df) < 5:
        return None
    # Find last BOS bar in bias direction
    bos_idx = None
    for i in range(len(df) - 1, -1, -1):
        if bias == "BULLISH" and df.iloc[i].get("bos_bull"):
            bos_idx = i
            break
        if bias == "BEARISH" and df.iloc[i].get("bos_bear"):
            bos_idx = i
            break
    if bos_idx is None or bos_idx <= 0:
        return None
    # Look backward for OB in OPPOSITE direction
    opp_direction = "BEARISH" if bias == "BULLISH" else "BULLISH"
    for i in range(bos_idx - 1, max(0, bos_idx - ob_lookback), -1):
        candle = df.iloc[i]
        if opp_direction == "BEARISH":
            if candle["close"] >= candle["open"]:
                continue
            ob_high = max(candle["open"], candle["close"]) if use_body else candle["high"]
            ob_low = min(candle["open"], candle["close"]) if use_body else candle["low"]
            # Check if broken: any bar between OB and BOS has low < ob_low
            broken = False
            for j in range(i + 1, bos_idx):
                if df.iloc[j]["low"] < ob_low:
                    broken = True
                    break
            if broken:
                return {
                    "high": ob_high,
                    "low": ob_low,
                    "midpoint": (ob_high + ob_low) / 2,
                    "time": df.index[i],
                    "direction": "BULLISH",
                }
        else:
            if candle["close"] <= candle["open"]:
                continue
            ob_high = max(candle["open"], candle["close"]) if use_body else candle["high"]
            ob_low = min(candle["open"], candle["close"]) if use_body else candle["low"]
            broken = False
            for j in range(i + 1, bos_idx):
                if df.iloc[j]["high"] > ob_high:
                    broken = True
                    break
            if broken:
                return {
                    "high": ob_high,
                    "low": ob_low,
                    "midpoint": (ob_high + ob_low) / 2,
                    "time": df.index[i],
                    "direction": "BEARISH",
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
