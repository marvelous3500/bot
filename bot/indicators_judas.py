"""
NAS Judas Strategy indicators.
Structure shift after sweep (break of recent swing confirming direction).
"""
import pandas as pd

from .indicators_bos import detect_swing_highs_lows, detect_break_of_structure


def detect_structure_shift_after_sweep(
    df: pd.DataFrame, sweep_idx: int, idx: int, direction: str, swing_length: int = 3
) -> dict:
    """
    Check if price breaks recent swing in direction of bias after a sweep.
    Returns {shifted: bool, swing_level: float, reasoning: str}.
    """
    if df is None or df.empty or idx <= sweep_idx:
        return {"shifted": False, "swing_level": None, "reasoning": "invalid context"}

    if "swing_high" not in df.columns:
        df = detect_swing_highs_lows(df, swing_length=swing_length)
    if "bos_bull" not in df.columns:
        df = detect_break_of_structure(df)

    row = df.iloc[idx]
    window = df.iloc[sweep_idx : idx + 1]

    if direction == "BULLISH":
        past_lows = window[window["swing_low"] == True]["swing_low_price"]
        if past_lows.empty:
            return {"shifted": False, "swing_level": None, "reasoning": "no swing low to break"}
        swing_level = float(past_lows.iloc[-1])
        if row["close"] > swing_level:
            return {
                "shifted": True,
                "swing_level": swing_level,
                "reasoning": f"BOS: close {row['close']:.1f} > swing {swing_level:.1f}",
            }
    else:
        past_highs = window[window["swing_high"] == True]["swing_high_price"]
        if past_highs.empty:
            return {"shifted": False, "swing_level": None, "reasoning": "no swing high to break"}
        swing_level = float(past_highs.iloc[-1])
        if row["close"] < swing_level:
            return {
                "shifted": True,
                "swing_level": swing_level,
                "reasoning": f"BOS: close {row['close']:.1f} < swing {swing_level:.1f}",
            }

    return {"shifted": False, "swing_level": None, "reasoning": "no structure shift"}
