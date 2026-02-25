"""
Marvellous Strategy: XAUUSD (gold) ICT-style with multi-timeframe bias validation.
Bias (H1/4H/Daily) + zone confirmation + session/news/volatility filters + precision entry.
Fully independent of Kingsley Strategy.
"""
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

import config
from .. import marvellous_config as mc
from ..indicators import (
    detect_fvg,
    get_equilibrium,
    get_equilibrium_from_daily,
    price_in_buyside_liquidity,
    price_in_sellside_liquidity,
)
from ..indicators_bos import (
    detect_swing_highs_lows,
    detect_break_of_structure,
    identify_order_block,
    detect_shallow_tap,
    detect_breaker_block,
)
from ..news_filter import is_news_safe


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _zone_respected(
    df: pd.DataFrame,
    zone_top: float,
    zone_bottom: float,
    wick_pct: float,
    body_pct: float,
    start_idx: int,
    end_idx: int,
    bullish: bool,
) -> bool:
    """Check if any candle in range touched zone and showed reaction (wick/body)."""
    for i in range(start_idx, min(end_idx, len(df))):
        row = df.iloc[i]
        rng = row["high"] - row["low"]
        if rng <= 0:
            continue
        touched = (zone_bottom <= row["low"] <= zone_top) or (zone_bottom <= row["high"] <= zone_top)
        if not touched:
            continue
        lower_wick = min(row["open"], row["close"]) - row["low"]
        upper_wick = row["high"] - max(row["open"], row["close"])
        body = abs(row["close"] - row["open"])
        if bullish and lower_wick / rng >= wick_pct:
            return True
        if bullish and body / rng >= body_pct and row["close"] > row["open"]:
            return True
        if not bullish and upper_wick / rng >= wick_pct:
            return True
        if not bullish and body / rng >= body_pct and row["close"] < row["open"]:
            return True
    return False


def calculate_h1_bias_with_zone_validation(
    df_h1: pd.DataFrame,
    lookback_hours: int,
    require_zone: bool,
    wick_pct: float,
    body_pct: float,
) -> Dict[str, Any]:
    """H1 bias with optional zone confirmation."""
    if df_h1 is None or df_h1.empty or len(df_h1) < 5:
        return {"bias": "NEUTRAL", "proof": None}
    df = df_h1.tail(lookback_hours)
    df = detect_break_of_structure(df.copy())
    df = detect_fvg(df)
    last = df.iloc[-1]
    bias = "NEUTRAL"
    if last.get("bos_bull"):
        bias = "BULLISH"
    elif last.get("bos_bear"):
        bias = "BEARISH"
    if bias == "NEUTRAL":
        return {"bias": "NEUTRAL", "proof": None}
    if not require_zone:
        if getattr(mc, "REQUIRE_BREAKER_BLOCK", False) and getattr(mc, "BREAKER_BLOCK_TF", "H1").upper() == "H1":
            if detect_breaker_block(df, bias, ob_lookback=getattr(mc, "MARVELLOUS_OB_LOOKBACK", 20)) is None:
                return {"bias": "NEUTRAL", "proof": None}
        return {"bias": bias, "proof": {"structure": "BOS", "zone_type": None, "zone_coordinates": None}}
    # Find FVG/OB in lookback
    for i in range(len(df) - 1, max(0, len(df) - 30), -1):
        row = df.iloc[i]
        zone_top, zone_bottom = None, None
        if row.get("fvg_bull"):
            zone_bottom = df.iloc[i - 2]["high"]
            zone_top = row["low"]
        elif row.get("fvg_bear"):
            zone_top = df.iloc[i - 2]["low"]
            zone_bottom = row["high"]
        if zone_top is not None and zone_bottom is not None:
            ob = identify_order_block(df, i, ob_lookback=10)
            if ob is not None:
                zone_top, zone_bottom = ob["high"], ob["low"]
            if _zone_respected(df, zone_top, zone_bottom, wick_pct, body_pct, i, len(df), bias == "BULLISH"):
                if getattr(mc, "REQUIRE_BREAKER_BLOCK", False) and getattr(mc, "BREAKER_BLOCK_TF", "H1").upper() == "H1":
                    if detect_breaker_block(df, bias, ob_lookback=getattr(mc, "MARVELLOUS_OB_LOOKBACK", 20)) is None:
                        return {"bias": "NEUTRAL", "proof": None}
                return {
                    "bias": bias,
                    "proof": {
                        "structure": "BOS",
                        "zone_type": "FVG" if "fvg" in str(row.get("fvg_bull", row.get("fvg_bear", ""))) else "OB",
                        "zone_coordinates": (zone_top, zone_bottom),
                        "timestamp": df.index[i],
                    },
                }
    return {"bias": "NEUTRAL", "proof": None}


def calculate_4h_bias_with_zone_validation(
    df_4h: pd.DataFrame,
    lookback_bars: int,
    require_zone: bool,
    wick_pct: float,
    body_pct: float,
) -> Dict[str, Any]:
    """4H bias with optional zone confirmation."""
    if df_4h is None or df_4h.empty or len(df_4h) < 5:
        return {"bias": "NEUTRAL", "proof": None}
    df = df_4h.tail(lookback_bars)
    df = detect_break_of_structure(df.copy())
    df = detect_fvg(df)
    last = df.iloc[-1]
    bias = "NEUTRAL"
    if last.get("bos_bull"):
        bias = "BULLISH"
    elif last.get("bos_bear"):
        bias = "BEARISH"
    if bias == "NEUTRAL":
        return {"bias": "NEUTRAL", "proof": None}
    if not require_zone:
        if getattr(mc, "REQUIRE_BREAKER_BLOCK", False) and getattr(mc, "BREAKER_BLOCK_TF", "H1").upper() == "4H":
            if detect_breaker_block(df, bias, ob_lookback=getattr(mc, "MARVELLOUS_OB_LOOKBACK", 20)) is None:
                return {"bias": "NEUTRAL", "proof": None}
        return {"bias": bias, "proof": {"structure": "BOS"}}
    for i in range(len(df) - 1, max(0, len(df) - 20), -1):
        row = df.iloc[i]
        zone_top, zone_bottom = None, None
        if row.get("fvg_bull"):
            zone_bottom = df.iloc[i - 2]["high"]
            zone_top = row["low"]
        elif row.get("fvg_bear"):
            zone_top = df.iloc[i - 2]["low"]
            zone_bottom = row["high"]
        if zone_top is not None and zone_bottom is not None:
            if _zone_respected(df, zone_top, zone_bottom, wick_pct, body_pct, i, len(df), bias == "BULLISH"):
                if getattr(mc, "REQUIRE_BREAKER_BLOCK", False) and getattr(mc, "BREAKER_BLOCK_TF", "H1").upper() == "4H":
                    if detect_breaker_block(df, bias, ob_lookback=getattr(mc, "MARVELLOUS_OB_LOOKBACK", 20)) is None:
                        return {"bias": "NEUTRAL", "proof": None}
                return {"bias": bias, "proof": {"structure": "BOS", "zone_coordinates": (zone_top, zone_bottom)}}
    return {"bias": "NEUTRAL", "proof": None}


def calculate_daily_bias_with_ict_rules_and_zone_validation(
    df_daily: pd.DataFrame,
    lookback_bars: int,
    require_zone: bool,
    wick_pct: float,
    body_pct: float,
) -> Dict[str, Any]:
    """Daily bias with ICT rules and zone validation."""
    if df_daily is None or df_daily.empty or len(df_daily) < 5:
        return {"bias": "NEUTRAL", "proof": None}
    df = df_daily.tail(lookback_bars)
    df = detect_break_of_structure(df.copy())
    df = detect_fvg(df)
    last = df.iloc[-1]
    bias = "NEUTRAL"
    if last.get("bos_bull"):
        bias = "BULLISH"
    elif last.get("bos_bear"):
        bias = "BEARISH"
    if bias == "NEUTRAL":
        return {"bias": "NEUTRAL", "proof": None}
    if not require_zone:
        if getattr(mc, "REQUIRE_BREAKER_BLOCK", False) and getattr(mc, "BREAKER_BLOCK_TF", "H1").upper() == "DAILY":
            if detect_breaker_block(df, bias, ob_lookback=getattr(mc, "MARVELLOUS_OB_LOOKBACK", 20)) is None:
                return {"bias": "NEUTRAL", "proof": None}
        return {"bias": bias, "proof": {"structure": "BOS"}}
    for i in range(len(df) - 1, max(0, len(df) - 15), -1):
        row = df.iloc[i]
        zone_top, zone_bottom = None, None
        if row.get("fvg_bull"):
            zone_bottom = df.iloc[i - 2]["high"]
            zone_top = row["low"]
        elif row.get("fvg_bear"):
            zone_top = df.iloc[i - 2]["low"]
            zone_bottom = row["high"]
        if zone_top is not None and zone_bottom is not None:
            if _zone_respected(df, zone_top, zone_bottom, wick_pct, body_pct, i, len(df), bias == "BULLISH"):
                if getattr(mc, "REQUIRE_BREAKER_BLOCK", False) and getattr(mc, "BREAKER_BLOCK_TF", "H1").upper() == "DAILY":
                    if detect_breaker_block(df, bias, ob_lookback=getattr(mc, "MARVELLOUS_OB_LOOKBACK", 20)) is None:
                        return {"bias": "NEUTRAL", "proof": None}
                return {"bias": bias, "proof": {"structure": "BOS", "zone_coordinates": (zone_top, zone_bottom)}}
    return {"bias": "NEUTRAL", "proof": None}


def combine_enabled_biases(
    h1_result: Dict,
    h4_result: Optional[Dict],
    daily_result: Optional[Dict],
    method: str,
) -> str:
    """Combine biases: unanimous, majority, or weighted."""
    enabled = []
    if mc.REQUIRE_H1_BIAS:
        enabled.append(("H1", h1_result))
    if mc.REQUIRE_4H_BIAS and h4_result:
        enabled.append(("4H", h4_result))
    if mc.REQUIRE_DAILY_BIAS and daily_result:
        enabled.append(("D", daily_result))
    if not enabled:
        return h1_result.get("bias", "NEUTRAL") if h1_result else "NEUTRAL"
    biases = [r.get("bias", "NEUTRAL") for _, r in enabled]
    if "NEUTRAL" in biases:
        return "NEUTRAL"
    if method == "unanimous":
        if len(set(biases)) == 1:
            return biases[0]
        return "NEUTRAL"
    if method == "majority":
        bull = sum(1 for b in biases if b == "BULLISH")
        bear = sum(1 for b in biases if b == "BEARISH")
        if bull >= 2 or bull > bear:
            return "BULLISH"
        if bear >= 2 or bear > bull:
            return "BEARISH"
        return "NEUTRAL"
    if method == "weighted":
        w = {"H1": 1, "4H": 2, "D": 3}
        score = 0
        for (tf, _), b in zip(enabled, biases):
            s = 1 if b == "BULLISH" else -1
            score += s * w.get(tf, 1)
        if score > 0:
            return "BULLISH"
        if score < 0:
            return "BEARISH"
    return "NEUTRAL"


def is_session_allowed(current_time: datetime, cfg: Any = None) -> bool:
    """Check if current UTC hour is in an enabled session."""
    cfg = cfg or mc
    hour = current_time.hour if hasattr(current_time, "hour") else current_time
    if isinstance(hour, datetime):
        hour = hour.hour
    sessions = {}
    if getattr(cfg, "ENABLE_LONDON_SESSION", True):
        sessions["london"] = [7, 8, 9, 10]
    if getattr(cfg, "ENABLE_NEWYORK_SESSION", True):
        sessions["ny"] = [13, 14, 15, 16]
    if getattr(cfg, "ENABLE_ASIA_SESSION", True):
        sessions["asian"] = getattr(cfg, "ASIAN_SESSION_HOURS", [0, 1, 2, 3, 4])
    allowed_hours = []
    for hlist in sessions.values():
        allowed_hours.extend(hlist)
    return hour in allowed_hours


def is_liquidity_map_valid(
    df: pd.DataFrame,
    strength_threshold: float,
    atr_series: pd.Series,
) -> bool:
    """Liquidity zones = clusters of swing highs/lows. Strength = touches."""
    if df is None or df.empty or "swing_high" not in df.columns:
        return True
    atr_val = atr_series.iloc[-1] if atr_series is not None and len(atr_series) > 0 else 0
    if pd.isna(atr_val) or atr_val <= 0:
        atr_val = (df["high"] - df["low"]).mean()
    threshold = atr_val * 0.5
    highs = df[df["swing_high"] == True]["swing_high_price"].dropna()
    lows = df[df["swing_low"] == True]["swing_low_price"].dropna()
    for prices in (highs, lows):
        for i, p in enumerate(prices):
            cluster = sum(1 for q in prices if abs(q - p) <= threshold)
            strength = min(1.0, cluster / 5.0)
            if strength >= strength_threshold:
                return True
    return False


class MarvellousStrategy:
    """Marvellous Strategy: XAUUSD gold, multi-TF bias + zone + filters + precision entry."""

    def __init__(
        self,
        df_daily: Optional[pd.DataFrame],
        df_4h: Optional[pd.DataFrame],
        df_h1: pd.DataFrame,
        df_m15: pd.DataFrame,
        df_entry: pd.DataFrame,
        df_daily_raw: Optional[pd.DataFrame] = None,
        symbol: Optional[str] = None,
        verbose: bool = False,
    ):
        self.df_daily = df_daily.copy() if df_daily is not None and not df_daily.empty else None
        self.df_4h = df_4h.copy() if df_4h is not None and not df_4h.empty else None
        self.df_h1 = df_h1.copy()
        self.df_m15 = df_m15.copy()
        self.df_entry = df_entry.copy()
        self.df_daily_raw = df_daily_raw or df_daily
        self.symbol = symbol
        self.verbose = verbose

    def _log(self, msg: str):
        if self.verbose:
            print(msg)

    def prepare_data(self):
        """Run indicators on all timeframes."""
        swing_len = mc.MARVELLOUS_SWING_LENGTH
        for name, df in [
            ("Daily", self.df_daily),
            ("4H", self.df_4h),
            ("H1", self.df_h1),
            ("M15", self.df_m15),
            ("Entry", self.df_entry),
        ]:
            if df is None or df.empty:
                continue
            self._log(f"Detecting swing/BOS/FVG on {name}...")
            df = detect_swing_highs_lows(df, swing_length=swing_len)
            df = detect_break_of_structure(df)
            df = detect_fvg(df)
            if name == "Daily":
                self.df_daily = df
            elif name == "4H":
                self.df_4h = df
            elif name == "H1":
                self.df_h1 = df
            elif name == "M15":
                self.df_m15 = df
            else:
                self.df_entry = df
        return self.df_daily, self.df_4h, self.df_h1, self.df_m15, self.df_entry

    def run_backtest(self) -> pd.DataFrame:
        """Run backtest; returns DataFrame of signals."""
        if self.df_h1.empty or self.df_m15.empty or self.df_entry.empty:
            return pd.DataFrame()
        rt = mc.REACTION_THRESHOLDS
        wick_pct = rt.get("wick_pct", 0.5)
        body_pct = rt.get("body_pct", 0.3)
        signals = []
        entry_df = self.df_entry
        atr_series = _atr(entry_df, 14)
        window_hours = mc.MARVELLOUS_ENTRY_WINDOW_HOURS
        ob_lookback = mc.MARVELLOUS_OB_LOOKBACK
        liq_lookback = mc.MARVELLOUS_LIQ_SWEEP_LOOKBACK
        tp_lookahead = mc.MARVELLOUS_TP_SWING_LOOKAHEAD
        max_per_setup = getattr(mc, "MARVELLOUS_MAX_TRADES_PER_SETUP", None)
        if max_per_setup is None:
            max_per_setup = 1 if getattr(mc, "MARVELLOUS_ONE_SIGNAL_PER_SETUP", True) else None
        trades_per_m15_setup: Dict = {}
        apply_limits = getattr(config, "BACKTEST_APPLY_TRADE_LIMITS", False)
        trades_per_day: Dict[str, int] = {}
        trades_per_session: Dict[str, int] = {}
        sl_method = getattr(mc, "MARVELLOUS_SL_METHOD", "OB")
        sl_atr_mult = getattr(mc, "MARVELLOUS_SL_ATR_MULT", 1.0)
        sl_micro_tf = getattr(mc, "MARVELLOUS_SL_MICRO_TF", "1m")
        entry_tf = getattr(mc, "ENTRY_TIMEFRAME", "5m")
        agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
        pip = 0.01 if ("XAU" in str(self.symbol or "") or "GC" in str(self.symbol or "")) else 0.0001

        for i in range(len(entry_df)):
            idx = entry_df.index[i]
            current_time = idx if hasattr(idx, "hour") else pd.Timestamp(idx)
            
            # Skip Saturday (5) and Sunday (6) in backtest
            if getattr(config, "BACKTEST_EXCLUDE_WEEKENDS", False) and current_time.weekday() >= 5:
                continue

            # 1. Bias
            df_h1_slice = self.df_h1[self.df_h1.index <= idx].tail(mc.LOOKBACK_H1_HOURS)
            h1_res = calculate_h1_bias_with_zone_validation(
                df_h1_slice,
                mc.LOOKBACK_H1_HOURS,
                mc.REQUIRE_H1_ZONE_CONFIRMATION,
                wick_pct,
                body_pct,
            )
            h4_res = None
            if self.df_4h is not None and mc.REQUIRE_4H_BIAS:
                df_4h_slice = self.df_4h[self.df_4h.index <= idx].tail(mc.LOOKBACK_4H_BARS)
                h4_res = calculate_4h_bias_with_zone_validation(
                    df_4h_slice,
                    mc.LOOKBACK_4H_BARS,
                    mc.REQUIRE_4H_ZONE_CONFIRMATION,
                    wick_pct,
                    body_pct,
                )
            daily_res = None
            if self.df_daily is not None and mc.REQUIRE_DAILY_BIAS:
                df_d_slice = self.df_daily[self.df_daily.index <= idx].tail(mc.LOOKBACK_DAILY_BARS)
                daily_res = calculate_daily_bias_with_ict_rules_and_zone_validation(
                    df_d_slice,
                    mc.LOOKBACK_DAILY_BARS,
                    mc.REQUIRE_DAILY_ZONE_CONFIRMATION,
                    wick_pct,
                    body_pct,
                )
            overall_bias = combine_enabled_biases(
                h1_res, h4_res, daily_res, mc.BIAS_COMBINATION_METHOD
            )
            if overall_bias == "NEUTRAL":
                continue

            if getattr(mc, "USE_PREMIUM_DISCOUNT", False):
                eq_lookback = getattr(mc, "EQUILIBRIUM_LOOKBACK", 24)
                eq_tf = getattr(mc, "EQUILIBRIUM_TF", "H1").upper()
                if eq_tf == "DAILY" and self.df_daily is not None and not self.df_daily.empty:
                    equilibrium = get_equilibrium_from_daily(self.df_daily, current_time)
                else:
                    df_eq = self.df_h1 if eq_tf == "H1" else (self.df_4h if self.df_4h is not None and not self.df_4h.empty else self.df_h1)
                    df_eq_slice = df_eq[df_eq.index <= idx].tail(eq_lookback)
                    equilibrium = get_equilibrium(df_eq_slice, eq_lookback)
                if equilibrium is not None:
                    current_close = float(entry_df.iloc[i]["close"])
                    if overall_bias == "BULLISH" and current_close > equilibrium:
                        continue
                    if overall_bias == "BEARISH" and current_close < equilibrium:
                        continue

            # 2–5. Extra filters (session, news, liquidity, ATR) — only when USE_EXTRA_FILTERS=True
            if getattr(config, "USE_EXTRA_FILTERS", True):
                if not is_session_allowed(current_time):
                    continue
                if not is_news_safe(
                    current_time,
                    mc.NEWS_BUFFER_BEFORE_MINUTES,
                    mc.NEWS_BUFFER_AFTER_MINUTES,
                    mc.AVOID_NEWS,
                    mc.MARVELLOUS_NEWS_COUNTRIES,
                    mc.MARVELLOUS_NEWS_API,
                    mc.FCSAPI_KEY,
                ):
                    continue
                if mc.USE_LIQUIDITY_MAP:
                    entry_slice = entry_df[entry_df.index <= idx]
                    if not is_liquidity_map_valid(
                        entry_slice,
                        mc.LIQUIDITY_ZONE_STRENGTH_THRESHOLD,
                        atr_series[atr_series.index <= idx] if atr_series is not None else None,
                    ):
                        continue
                atr_val = atr_series.iloc[i] if i < len(atr_series) and atr_series is not None else None
                min_atr = config.get_symbol_config(self.symbol, "MARVELLOUS_MIN_ATR_THRESHOLD") or mc.MIN_ATR_THRESHOLD
                if atr_val is not None and not pd.isna(atr_val) and atr_val < min_atr:
                    continue

            # 6. Lower-TF zone + structure + sweep + entry
            row = entry_df.iloc[i]
            h1_slice = self.df_h1[self.df_h1.index <= idx].tail(24)
            if h1_slice.empty:
                continue
            h1_last = h1_slice.iloc[-1]
            h1_bias = "BULLISH" if h1_last.get("bos_bull") else ("BEARISH" if h1_last.get("bos_bear") else None)
            if h1_bias is None:
                continue
            m15_slice = self.df_m15[(self.df_m15.index <= idx) & (self.df_m15.index > idx - pd.Timedelta(hours=window_hours))]
            if m15_slice.empty:
                continue
            m15_bos_seen = False
            current_ob = None
            ob_tapped = False
            lq_swept = False
            lq_level = None
            lq_swept_back = False
            ob_tested = False
            last_m15_signal_idx = None

            for _, m15_row in m15_slice.iterrows():
                m15_idx = m15_row.name
                if not m15_bos_seen:
                    try:
                        loc = self.df_m15.index.get_loc(m15_idx)
                        i_m15 = int(loc) if isinstance(loc, (int, np.integer)) else (loc.start if hasattr(loc, "start") else 0)
                    except (KeyError, TypeError, ValueError):
                        continue
                    if h1_bias == "BULLISH" and m15_row.get("bos_bull"):
                        m15_bos_seen = True
                        current_ob = identify_order_block(self.df_m15, i_m15, ob_lookback=ob_lookback)
                    elif h1_bias == "BEARISH" and m15_row.get("bos_bear"):
                        m15_bos_seen = True
                        current_ob = identify_order_block(self.df_m15, i_m15, ob_lookback=ob_lookback)
                    if not m15_bos_seen or current_ob is None:
                        if current_ob is None and m15_bos_seen:
                            m15_bos_seen = False
                        continue

                if current_ob is None:
                    continue
                if not ob_tapped:
                    tapped = detect_shallow_tap(
                        m15_row["low"], m15_row["high"],
                        current_ob["high"], current_ob["low"], current_ob["midpoint"],
                    )
                    if tapped and h1_bias == "BULLISH" and m15_row["close"] >= current_ob["midpoint"]:
                        ob_tapped = True
                    elif tapped and h1_bias == "BEARISH" and m15_row["close"] <= current_ob["midpoint"]:
                        ob_tapped = True
                    continue

                if not lq_swept:
                    if h1_bias == "BULLISH":
                        recent_highs = self.df_m15[
                            (self.df_m15.index < m15_idx) & (self.df_m15["swing_high"] == True)
                        ].tail(liq_lookback)
                        if not recent_highs.empty:
                            liq_high = recent_highs.iloc[-1]["swing_high_price"]
                            if m15_row["high"] > liq_high:
                                lq_swept = True
                                lq_level = m15_row["low"]
                    elif h1_bias == "BEARISH":
                        recent_lows = self.df_m15[
                            (self.df_m15.index < m15_idx) & (self.df_m15["swing_low"] == True)
                        ].tail(liq_lookback)
                        if not recent_lows.empty:
                            liq_low = recent_lows.iloc[-1]["swing_low_price"]
                            if m15_row["low"] < liq_low:
                                lq_swept = True
                                lq_level = m15_row["high"]
                    if not lq_swept:
                        continue

                if not lq_swept_back and lq_level is not None:
                    if h1_bias == "BULLISH" and m15_row["low"] <= lq_level:
                        lq_swept_back = True
                    elif h1_bias == "BEARISH" and m15_row["high"] >= lq_level:
                        lq_swept_back = True
                    if not lq_swept_back:
                        continue

                if not ob_tested:
                    tapped = detect_shallow_tap(
                        m15_row["low"], m15_row["high"],
                        current_ob["high"], current_ob["low"], current_ob["midpoint"],
                    )
                    if tapped and h1_bias == "BULLISH" and m15_row["close"] >= current_ob["midpoint"]:
                        ob_tested = True
                        last_m15_signal_idx = m15_idx
                    elif tapped and h1_bias == "BEARISH" and m15_row["close"] <= current_ob["midpoint"]:
                        ob_tested = True
                        last_m15_signal_idx = m15_idx
                    if not ob_tested:
                        continue
                    break  # State complete, exit M15 loop

            # Entry: setup complete and current entry bar is within window after signal
            if ob_tested and last_m15_signal_idx is not None and lq_level is not None:
                if max_per_setup is not None and trades_per_m15_setup.get(last_m15_signal_idx, 0) >= max_per_setup:
                    continue
                entry_window_minutes = getattr(mc, "MARVELLOUS_ENTRY_WINDOW_MINUTES", 15)
                window_end = last_m15_signal_idx + pd.Timedelta(minutes=entry_window_minutes)
                if last_m15_signal_idx <= idx < window_end:
                    disp_ratio = 0.6
                    candle_body = abs(row["close"] - row["open"])
                    candle_range = row["high"] - row["low"]
                    is_displacement = candle_body > (candle_range * disp_ratio) if candle_range > 0 else False
                    if is_displacement:
                        session_key = config.TRADE_SESSION_HOURS.get(current_time.hour, "other")
                        day_key = current_time.strftime("%Y-%m-%d") if hasattr(current_time, "strftime") else str(current_time.date())
                        if apply_limits:
                            max_per_day = getattr(config, "BACKTEST_MAX_TRADES_PER_DAY", config.MAX_TRADES_PER_DAY)
                            max_per_session = getattr(config, "BACKTEST_MAX_TRADES_PER_SESSION", config.MAX_TRADES_PER_SESSION)
                            if trades_per_day.get(day_key, 0) >= max_per_day:
                                continue
                            if max_per_session is not None and config.TRADE_SESSION_HOURS.get(current_time.hour) is not None:
                                if trades_per_session.get(session_key, 0) >= max_per_session:
                                    continue
                        entry_price = float(row["close"])
                        sl = float(lq_level)
                        if sl_method == "HYBRID":
                            micro_df = None
                            if sl_micro_tf == "1m" and entry_tf == "1m":
                                micro_df = entry_df[entry_df.index <= idx]
                            elif sl_micro_tf == "5m":
                                if entry_tf == "5m":
                                    micro_df = entry_df[entry_df.index <= idx]
                                elif entry_tf == "1m":
                                    entry_slice = entry_df[entry_df.index <= idx]
                                    micro_df = entry_slice.resample("5min").agg(agg).dropna()
                                    if not micro_df.empty:
                                        micro_df = detect_swing_highs_lows(micro_df, swing_length=mc.MARVELLOUS_SWING_LENGTH)
                                elif entry_tf == "15m":
                                    m15_slice = self.df_m15[self.df_m15.index <= idx]
                                    micro_df = m15_slice.resample("5min").agg(agg).ffill().dropna()
                                    if not micro_df.empty:
                                        micro_df = detect_swing_highs_lows(micro_df, swing_length=mc.MARVELLOUS_SWING_LENGTH)
                            if micro_df is not None and not micro_df.empty:
                                atr_val = atr_series.iloc[i] if i < len(atr_series) and atr_series is not None else np.nan
                                if sl_micro_tf == "5m" and entry_tf in ("5m", "15m"):
                                    atr_micro = _atr(micro_df, 14)
                                    atr_val = atr_micro.iloc[-1] if not atr_micro.empty else atr_val
                                atr_val = float(atr_val) if not pd.isna(atr_val) and atr_val > 0 else (row["high"] - row["low"]) * 2
                                buf = atr_val * sl_atr_mult
                                if h1_bias == "BULLISH":
                                    swing_lows = micro_df[micro_df["swing_low"] == True]
                                    if not swing_lows.empty:
                                        base_swing = float(swing_lows.iloc[-1]["swing_low_price"])
                                        sl = base_swing - buf
                                        if sl >= entry_price:
                                            sl = entry_price - pip
                                else:
                                    swing_highs = micro_df[micro_df["swing_high"] == True]
                                    if not swing_highs.empty:
                                        base_swing = float(swing_highs.iloc[-1]["swing_high_price"])
                                        sl = base_swing + buf
                                        if sl <= entry_price:
                                            sl = entry_price + pip
                        if getattr(config, "USE_ZONE_DIRECTION_FILTER", False):
                            m15_slice_zd = self.df_m15[self.df_m15.index <= idx].tail(
                                getattr(config, "ZONE_DIRECTION_FVG_LOOKBACK", 30)
                            )
                            lookback_zd = getattr(config, "ZONE_DIRECTION_FVG_LOOKBACK", 30)
                            buffer_pct_zd = getattr(config, "ZONE_DIRECTION_BUFFER_PCT", 0.001)
                            use_eq_zd = getattr(config, "ZONE_DIRECTION_USE_EQUILIBRIUM", True)
                            equilibrium_zd = None
                            if use_eq_zd:
                                eq_lookback = getattr(mc, "EQUILIBRIUM_LOOKBACK", 24)
                                eq_tf = getattr(mc, "EQUILIBRIUM_TF", "H1").upper()
                                if eq_tf == "DAILY" and self.df_daily is not None and not self.df_daily.empty:
                                    equilibrium_zd = get_equilibrium_from_daily(self.df_daily, idx)
                                else:
                                    df_eq = self.df_h1 if eq_tf == "H1" else (self.df_4h if self.df_4h is not None and not self.df_4h.empty else self.df_h1)
                                    if df_eq is not None and not df_eq.empty:
                                        df_eq_slice = df_eq[df_eq.index <= idx].tail(eq_lookback)
                                        equilibrium_zd = get_equilibrium(df_eq_slice, eq_lookback)
                            if h1_bias == "BULLISH":
                                if price_in_buyside_liquidity(
                                    entry_price, m15_slice_zd, lookback_zd,
                                    equilibrium=equilibrium_zd, buffer_pct=buffer_pct_zd, use_equilibrium=use_eq_zd,
                                ):
                                    continue
                            else:
                                if price_in_sellside_liquidity(
                                    entry_price, m15_slice_zd, lookback_zd,
                                    equilibrium=equilibrium_zd, buffer_pct=buffer_pct_zd, use_equilibrium=use_eq_zd,
                                ):
                                    continue
                        if h1_bias == "BULLISH":
                            is_bull = row["close"] > row["open"]
                            if is_bull and float(lq_level) < float(row["close"]):
                                future_highs = self.df_m15[
                                    (self.df_m15.index > idx) & (self.df_m15["swing_high"] == True)
                                ].head(tp_lookahead)
                                tp_price = future_highs.iloc[0]["swing_high_price"] if not future_highs.empty else None
                                sig = {
                                    "time": idx,
                                    "type": "BUY",
                                    "price": row["close"],
                                    "sl": sl,
                                    "tp": tp_price,
                                    "reason": "Marvellous: H1+zone bias + M15 BOS + OB tap + sweep + OB test",
                                    "setup_m15": last_m15_signal_idx,
                                }
                                signals.append(sig)
                                if apply_limits:
                                    trades_per_day[day_key] = trades_per_day.get(day_key, 0) + 1
                                    trades_per_session[session_key] = trades_per_session.get(session_key, 0) + 1
                                trades_per_m15_setup[last_m15_signal_idx] = trades_per_m15_setup.get(last_m15_signal_idx, 0) + 1
                        elif h1_bias == "BEARISH":
                            is_bear = row["close"] < row["open"]
                            if is_bear and float(lq_level) > float(row["close"]):
                                future_lows = self.df_m15[
                                    (self.df_m15.index > idx) & (self.df_m15["swing_low"] == True)
                                ].head(tp_lookahead)
                                tp_price = future_lows.iloc[0]["swing_low_price"] if not future_lows.empty else None
                                sig = {
                                    "time": idx,
                                    "type": "SELL",
                                    "price": row["close"],
                                    "sl": sl,
                                    "tp": tp_price,
                                    "reason": "Marvellous: H1+zone bias + M15 BOS + OB tap + sweep + OB test",
                                    "setup_m15": last_m15_signal_idx,
                                }
                                signals.append(sig)
                                if apply_limits:
                                    trades_per_day[day_key] = trades_per_day.get(day_key, 0) + 1
                                    trades_per_session[session_key] = trades_per_session.get(session_key, 0) + 1
                                trades_per_m15_setup[last_m15_signal_idx] = trades_per_m15_setup.get(last_m15_signal_idx, 0) + 1

        return pd.DataFrame(signals)
