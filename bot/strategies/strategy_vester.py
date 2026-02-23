"""
VesterStrategy: multi-timeframe smart-money model (1H bias -> 5M setup -> 1M entry).
Uses market structure, liquidity sweeps, FVG, and order blocks. Rule-based detection only.
"""
import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime

import config
from .. import vester_config as vc
from ..indicators import detect_fvg, detect_rejection_candle, detect_displacement
from ..indicators_bos import (
    detect_swing_highs_lows,
    detect_break_of_structure,
    identify_order_block,
    detect_breaker_block,
)
from ..news_filter import is_news_safe
from .base import BaseStrategy


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


def _price_in_zone(bar_low: float, bar_high: float, zone_top: float, zone_bottom: float) -> bool:
    """Check if bar intersects zone [zone_bottom, zone_top]."""
    return not (bar_high < zone_bottom or bar_low > zone_top)


def _get_fvg_zones(df: pd.DataFrame, start_idx: int, end_idx: int) -> List[Tuple[float, float, str]]:
    """Return list of (zone_top, zone_bottom, direction) for FVGs in range. Bullish FVG: c3_low > c1_high -> zone = [c1_high, c3_low]."""
    zones = []
    for i in range(max(2, start_idx), min(end_idx, len(df) - 1)):
        row = df.iloc[i]
        if row.get("fvg_bull"):
            zone_bottom = df.iloc[i - 2]["high"]
            zone_top = row["low"]
            zones.append((zone_top, zone_bottom, "BULLISH"))
        if row.get("fvg_bear"):
            zone_top = df.iloc[i - 2]["low"]
            zone_bottom = row["high"]
            zones.append((zone_top, zone_bottom, "BEARISH"))
    return zones


class VesterStrategy(BaseStrategy):
    """
    Multi-timeframe smart-money strategy: 1H bias -> 5M setup -> 1M entry.
    Trades only when higher timeframe bias aligns with lower timeframe confirmation.
    """

    def __init__(
        self,
        df_h1: pd.DataFrame,
        df_m5: pd.DataFrame,
        df_m1: pd.DataFrame,
        df_h4: Optional[pd.DataFrame] = None,
        symbol: Optional[str] = None,
        verbose: bool = False,
    ):
        self.df_h1 = df_h1.copy() if df_h1 is not None and not df_h1.empty else df_h1
        self.df_m5 = df_m5.copy() if df_m5 is not None and not df_m5.empty else df_m5
        self.df_m1 = df_m1.copy() if df_m1 is not None and not df_m1.empty else df_m1
        self.df_h4 = df_h4.copy() if df_h4 is not None and not df_h4.empty else None
        self.symbol = symbol
        self.verbose = verbose

    def _log(self, msg: str):
        if self.verbose:
            print(msg)

    def prepare_data(self) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Run indicators on all timeframes: swing, BOS, FVG, rejection, displacement."""
        swing_len = vc.SWING_LENGTH
        frames = [("H1", "df_h1"), ("M5", "df_m5"), ("M1", "df_m1")]
        if self.df_h4 is not None:
            frames.insert(0, ("4H", "df_h4"))
        for name, df_ref in frames:
            df = getattr(self, df_ref)
            if df is None or df.empty:
                continue
            self._log(f"Vester: Detecting swing/BOS/FVG/rejection/displacement on {name}...")
            df = detect_swing_highs_lows(df, swing_length=swing_len)
            df = detect_break_of_structure(df)
            df = detect_fvg(df)
            df = detect_rejection_candle(df, wick_ratio=vc.REJECTION_WICK_RATIO)
            df = detect_displacement(df, threshold=1.5, window=10)
            setattr(self, df_ref, df)
        return self.df_h1, self.df_m5, self.df_m1

    def detect4HBias(
        self, df_h4_slice: pd.DataFrame
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        Determine 4H bias (same logic as 1H). Bullish: BOS + retrace into FVG/OB + rejection.
        Bearish: BOS + retrace into FVG/OB + rejection.
        Returns (bias, proof_dict) or (None, None).
        """
        if df_h4_slice is None or df_h4_slice.empty or len(df_h4_slice) < 5:
            return None, None

        lookback = getattr(vc, "H4_LOOKBACK_BARS", 24)
        df = df_h4_slice.tail(lookback)
        if len(df) < 5:
            return None, None

        last = df.iloc[-1]
        bias = None
        if last.get("bos_bull"):
            bias = "BULLISH"
        elif last.get("bos_bear"):
            bias = "BEARISH"
        if bias is None:
            return None, None

        if not getattr(vc, "REQUIRE_4H_ZONE_CONFIRMATION", True):
            return bias, {"zone_type": "BOS_ONLY"}

        wick_pct = vc.REJECTION_WICK_RATIO
        body_pct = vc.REJECTION_BODY_RATIO
        ob_lookback = vc.OB_LOOKBACK
        fvg_lookback = min(vc.FVG_LOOKBACK, len(df) - 1)

        for i in range(len(df) - 1, max(0, len(df) - fvg_lookback), -1):
            row = df.iloc[i]
            zone_top, zone_bottom = None, None
            zone_type = None

            if row.get("fvg_bull") and bias == "BULLISH":
                zone_bottom = df.iloc[i - 2]["high"]
                zone_top = row["low"]
                zone_type = "FVG"
            elif row.get("fvg_bear") and bias == "BEARISH":
                zone_top = df.iloc[i - 2]["low"]
                zone_bottom = row["high"]
                zone_type = "FVG"

            if zone_top is None:
                bos_bar = None
                for k in range(i, max(0, i - 10), -1):
                    if df.iloc[k].get("bos_bull") and bias == "BULLISH":
                        bos_bar = k
                        break
                    if df.iloc[k].get("bos_bear") and bias == "BEARISH":
                        bos_bar = k
                        break
                if bos_bar is not None:
                    ob = identify_order_block(df, bos_bar, ob_lookback=ob_lookback)
                    if ob is not None and ob.get("direction") == bias:
                        zone_top, zone_bottom = ob["high"], ob["low"]
                        zone_type = "OB"

            if zone_top is None or zone_bottom is None:
                continue

            for j in range(i, min(len(df), i + 20)):
                if j >= len(df):
                    break
                r = df.iloc[j]
                rng = r["high"] - r["low"]
                if rng <= 0:
                    continue
                touched = (zone_bottom <= r["low"] <= zone_top) or (zone_bottom <= r["high"] <= zone_top)
                if not touched:
                    continue
                lower_wick = min(r["open"], r["close"]) - r["low"]
                upper_wick = r["high"] - max(r["open"], r["close"])
                body = abs(r["close"] - r["open"])
                if bias == "BULLISH" and (lower_wick / rng >= wick_pct or (body / rng >= body_pct and r["close"] > r["open"])):
                    return bias, {"zone_type": zone_type}
                if bias == "BEARISH" and (upper_wick / rng >= wick_pct or (body / rng >= body_pct and r["close"] < r["open"])):
                    return bias, {"zone_type": zone_type}
        return None, None

    def detectHTFBias(
        self, df_h1_slice: pd.DataFrame
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        Determine HTF (1H) bias. Bullish: BOS above prev swing high + retrace into 1H FVG or bullish OB + rejection candle in zone.
        Bearish: BOS below prev swing low + retrace into 1H FVG or bearish OB + rejection in zone.
        Returns (bias, proof_dict) or (None, None).
        """
        if df_h1_slice is None or df_h1_slice.empty or len(df_h1_slice) < 5:
            return None, None

        df = df_h1_slice.tail(vc.HTF_LOOKBACK_HOURS)
        if len(df) < 5:
            return None, None

        last = df.iloc[-1]
        bias = None
        if last.get("bos_bull"):
            bias = "BULLISH"
        elif last.get("bos_bear"):
            bias = "BEARISH"
        if bias is None:
            return None, None

        if not getattr(vc, "REQUIRE_HTF_ZONE_CONFIRMATION", True):
            return bias, {"zone_type": "BOS_ONLY"}

        wick_pct = vc.REJECTION_WICK_RATIO
        body_pct = vc.REJECTION_BODY_RATIO
        ob_lookback = vc.OB_LOOKBACK

        for i in range(len(df) - 1, max(0, len(df) - vc.FVG_LOOKBACK), -1):
            row = df.iloc[i]
            zone_top, zone_bottom = None, None
            zone_type = None

            if row.get("fvg_bull") and bias == "BULLISH":
                zone_bottom = df.iloc[i - 2]["high"]
                zone_top = row["low"]
                zone_type = "FVG"
            elif row.get("fvg_bear") and bias == "BEARISH":
                zone_top = df.iloc[i - 2]["low"]
                zone_bottom = row["high"]
                zone_type = "FVG"

            if zone_top is None:
                bos_bar = None
                for k in range(i, max(0, i - 10), -1):
                    if df.iloc[k].get("bos_bull") and bias == "BULLISH":
                        bos_bar = k
                        break
                    if df.iloc[k].get("bos_bear") and bias == "BEARISH":
                        bos_bar = k
                        break
                if bos_bar is not None:
                    ob = identify_order_block(df, bos_bar, ob_lookback=ob_lookback)
                    if ob is not None and ob.get("direction") == bias:
                        zone_top, zone_bottom = ob["high"], ob["low"]
                        zone_type = "OB"

            if zone_top is None or zone_bottom is None:
                continue

            for j in range(i, min(len(df), i + 20)):
                if j >= len(df):
                    break
                r = df.iloc[j]
                rng = r["high"] - r["low"]
                if rng <= 0:
                    continue
                touched = (zone_bottom <= r["low"] <= zone_top) or (zone_bottom <= r["high"] <= zone_top)
                if not touched:
                    continue
                lower_wick = min(r["open"], r["close"]) - r["low"]
                upper_wick = r["high"] - max(r["open"], r["close"])
                body = abs(r["close"] - r["open"])
                if bias == "BULLISH" and (lower_wick / rng >= wick_pct or (body / rng >= body_pct and r["close"] > r["open"])):
                    return bias, {
                        "zone_top": zone_top,
                        "zone_bottom": zone_bottom,
                        "zone_type": zone_type,
                        "bar_idx": j,
                        "timestamp": df.index[j],
                    }
                if bias == "BEARISH" and (upper_wick / rng >= wick_pct or (body / rng >= body_pct and r["close"] < r["open"])):
                    return bias, {
                        "zone_top": zone_top,
                        "zone_bottom": zone_bottom,
                        "zone_type": zone_type,
                        "bar_idx": j,
                        "timestamp": df.index[j],
                    }
        return None, None

    def detectLiquiditySweep(
        self,
        df: pd.DataFrame,
        direction: str,
        lookback: int,
        end_idx: Optional[int] = None,
    ) -> Tuple[bool, Optional[float], Optional[int]]:
        """
        Detect liquidity sweep. BUY: sweep below recent swing lows (low < L, close > L).
        SELL: sweep above recent swing highs (high > H, close < H).
        Returns (swept, level, bar_index).
        """
        if df is None or df.empty or "swing_low" not in df.columns or "swing_high" not in df.columns:
            return False, None, None

        end = end_idx if end_idx is not None else len(df)
        start = max(0, end - lookback * 10)

        if direction == "BUY":
            last_swing_pos = None
            liq_level = None
            for j in range(start, end):
                if df.iloc[j].get("swing_low"):
                    last_swing_pos = j
                    liq_level = df.iloc[j]["swing_low_price"]
            if last_swing_pos is None or liq_level is None:
                return False, None, None
            for i in range(last_swing_pos + 1, end):
                if i >= len(df):
                    break
                r = df.iloc[i]
                if r["low"] < liq_level and r["close"] > liq_level:
                    return True, float(liq_level), i
        else:
            last_swing_pos = None
            liq_level = None
            for j in range(start, end):
                if df.iloc[j].get("swing_high"):
                    last_swing_pos = j
                    liq_level = df.iloc[j]["swing_high_price"]
            if last_swing_pos is None or liq_level is None:
                return False, None, None
            for i in range(last_swing_pos + 1, end):
                if i >= len(df):
                    break
                r = df.iloc[i]
                if r["high"] > liq_level and r["close"] < liq_level:
                    return True, float(liq_level), i
        return False, None, None

    def detectFVG(self, df: pd.DataFrame) -> pd.DataFrame:
        """Delegate to detect_fvg. Returns DataFrame with fvg_bull, fvg_bear columns."""
        return detect_fvg(df)

    def detectOrderBlock(
        self, df: pd.DataFrame, bos_index: int, ob_lookback: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """Identify order block before BOS. Returns OB dict or None."""
        lookback = ob_lookback or vc.OB_LOOKBACK
        return identify_order_block(df, bos_index, ob_lookback=lookback)

    def detectStructureShift(
        self, df: pd.DataFrame, end_idx: Optional[int] = None
    ) -> Tuple[Optional[str], Optional[int]]:
        """
        Structure shift = BOS on timeframe. Bullish = BOS up, Bearish = BOS down.
        Returns (direction, bos_bar_index).
        """
        if df is None or df.empty:
            return None, None
        end = end_idx if end_idx is not None else len(df)
        for i in range(end - 1, max(0, end - 50), -1):
            if i < 0:
                break
            row = df.iloc[i]
            if row.get("bos_bull"):
                return "BULLISH", i
            if row.get("bos_bear"):
                return "BEARISH", i
        return None, None

    def checkEntryTrigger(
        self,
        df_m1_slice: pd.DataFrame,
        direction: str,
        entry_zone_top: float,
        entry_zone_bottom: float,
        current_bar_idx: int,
    ) -> Tuple[bool, Optional[float], Optional[str]]:
        """
        Entry trigger on 1M. BUY: (1M BOS upward inside entry zone) OR (liquidity sweep low + bullish displacement).
        SELL: (1M BOS downward inside zone) OR (sweep high + bearish displacement).
        Returns (triggered, entry_price, reason).
        """
        if df_m1_slice is None or df_m1_slice.empty:
            return False, None, None

        bar = df_m1_slice.iloc[current_bar_idx]
        bar_low, bar_high = bar["low"], bar["high"]
        in_zone = _price_in_zone(bar_low, bar_high, entry_zone_top, entry_zone_bottom)

        disp_ratio = vc.DISPLACEMENT_RATIO
        candle_body = abs(bar["close"] - bar["open"])
        candle_range = bar["high"] - bar["low"]
        is_displacement = candle_body >= (candle_range * disp_ratio) if candle_range > 0 else False

        if direction == "BUY":
            if bar.get("bos_bull") and in_zone:
                return True, float(bar["close"]), "1M BOS upward in zone"
            swept, level, _ = self.detectLiquiditySweep(
                df_m1_slice, "BUY", vc.LIQUIDITY_LOOKBACK, end_idx=current_bar_idx + 1
            )
            if swept and bar.get("displacement_bull"):
                return True, float(bar["close"]), "1M sweep low + bullish displacement"
            if getattr(vc, "ALLOW_SIMPLE_ZONE_ENTRY", False) and in_zone and bar["close"] > bar["open"]:
                return True, float(bar["close"]), "1M price in zone + bullish candle"
        else:
            if bar.get("bos_bear") and in_zone:
                return True, float(bar["close"]), "1M BOS downward in zone"
            swept, level, _ = self.detectLiquiditySweep(
                df_m1_slice, "SELL", vc.LIQUIDITY_LOOKBACK, end_idx=current_bar_idx + 1
            )
            if swept and bar.get("displacement_bear"):
                return True, float(bar["close"]), "1M sweep high + bearish displacement"
            if getattr(vc, "ALLOW_SIMPLE_ZONE_ENTRY", False) and in_zone and bar["close"] < bar["open"]:
                return True, float(bar["close"]), "1M price in zone + bearish candle"
        return False, None, None

    def placeTrade(
        self,
        direction: str,
        entry_price: float,
        sl: float,
        tp: float,
        time_idx,
        reason: str,
    ) -> Dict[str, Any]:
        """Build and return a single signal dict for backtest/live."""
        return {
            "time": time_idx,
            "type": direction,
            "price": entry_price,
            "sl": sl,
            "tp": tp,
            "reason": reason,
        }

    def manageTrade(
        self,
        trade: Dict[str, Any],
        current_bar: pd.Series,
        balance: float,
        daily_loss_so_far: float,
    ) -> Optional[Dict[str, float]]:
        """
        Manage open trade: trailing stop, daily loss limit.
        Returns updated {sl, tp} or None. Backtest runner applies updates.
        """
        if not vc.USE_TRAILING_STOP:
            return None
        daily_limit = balance * (vc.DAILY_LOSS_LIMIT_PCT / 100.0)
        if daily_loss_so_far >= daily_limit:
            return {"close": True}
        return None

    def run_backtest(self) -> pd.DataFrame:
        """
        Run full backtest: loop over 1M bars, apply HTF bias -> 5M setup -> 1M entry.
        Enforces filters (spread, volatility, news) and risk limits.
        """
        if self.df_h1.empty or self.df_m5.empty or self.df_m1.empty:
            return pd.DataFrame()

        signals = []
        entry_df = self.df_m1
        atr_series = _atr(entry_df, 14)
        atr_m5 = _atr(self.df_m5, 14) if not self.df_m5.empty else None
        ob_lookback = vc.OB_LOOKBACK
        liq_lookback = vc.LIQUIDITY_LOOKBACK
        min_rr = vc.MIN_RR
        trades_per_session: Dict[str, int] = {}
        trades_per_day: Dict[str, int] = {}
        daily_loss: Dict[str, float] = {}
        max_per_setup = getattr(vc, "VESTER_MAX_TRADES_PER_SETUP", None)
        if max_per_setup is None:
            max_per_setup = 1 if getattr(vc, "VESTER_ONE_SIGNAL_PER_SETUP", True) else None
        trades_per_5m_setup: Dict = {}
        apply_limits = getattr(config, "BACKTEST_APPLY_TRADE_LIMITS", False)

        for i in range(100, len(entry_df)):
            idx = entry_df.index[i]
            current_time = idx if hasattr(idx, "hour") else pd.Timestamp(idx)
            session_key = config.TRADE_SESSION_HOURS.get(current_time.hour, "other")
            day_key = current_time.strftime("%Y-%m-%d") if hasattr(current_time, "strftime") else str(current_time.date())

            if apply_limits:
                max_per_day = getattr(config, "BACKTEST_MAX_TRADES_PER_DAY", config.MAX_TRADES_PER_DAY)
                max_per_session = getattr(config, "BACKTEST_MAX_TRADES_PER_SESSION", config.MAX_TRADES_PER_SESSION)
                if trades_per_day.get(day_key, 0) >= max_per_day:
                    continue
                if max_per_session is not None and session_key != "other":
                    if trades_per_session.get(session_key, 0) >= max_per_session:
                        continue
            else:
                if trades_per_session.get(session_key, 0) >= vc.MAX_TRADES_PER_SESSION:
                    continue
            if daily_loss.get(day_key, 0) >= config.INITIAL_BALANCE * (vc.DAILY_LOSS_LIMIT_PCT / 100.0):
                continue

            df_h1_slice = self.df_h1[self.df_h1.index <= idx].tail(vc.HTF_LOOKBACK_HOURS)
            if df_h1_slice.empty or len(df_h1_slice) < 5:
                continue

            bias, htf_proof = self.detectHTFBias(df_h1_slice)
            if bias is None:
                continue

            if getattr(vc, "REQUIRE_BREAKER_BLOCK", False):
                bb = detect_breaker_block(df_h1_slice, bias, ob_lookback=vc.OB_LOOKBACK)
                if bb is None:
                    continue

            if getattr(vc, "REQUIRE_4H_BIAS", False):
                if self.df_h4 is None or self.df_h4.empty:
                    continue
                h4_lookback = getattr(vc, "H4_LOOKBACK_BARS", 24)
                df_h4_slice = self.df_h4[self.df_h4.index <= idx].tail(h4_lookback)
                if df_h4_slice.empty or len(df_h4_slice) < 5:
                    continue
                bias_4h, _ = self.detect4HBias(df_h4_slice)
                as_filter = getattr(vc, "H4_AS_FILTER", True)
                if as_filter:
                    if bias_4h is not None and bias_4h != bias:
                        continue
                else:
                    if bias_4h is None or bias_4h != bias:
                        continue
                if getattr(vc, "BREAKER_BLOCK_4H", False):
                    bb = detect_breaker_block(df_h4_slice, bias, ob_lookback=vc.OB_LOOKBACK)
                    if bb is None:
                        continue

            m5_window = getattr(vc, "M5_WINDOW_HOURS", 12)
            df_m5_slice = self.df_m5[(self.df_m5.index <= idx) & (self.df_m5.index >= idx - pd.Timedelta(hours=m5_window))]
            if df_m5_slice.empty:
                continue

            swept, liq_level, _ = self.detectLiquiditySweep(df_m5_slice, "BUY" if bias == "BULLISH" else "SELL", liq_lookback)
            if getattr(vc, "REQUIRE_5M_SWEEP", True) and not swept:
                continue
            if not swept:
                liq_level = None

            struct_shift, bos_idx = self.detectStructureShift(df_m5_slice)
            if struct_shift != bias:
                continue

            entry_zone_top, entry_zone_bottom = None, None
            current_ob = None
            if bos_idx is not None:
                current_ob = self.detectOrderBlock(df_m5_slice, bos_idx)
            if current_ob is not None:
                entry_zone_top, entry_zone_bottom = current_ob["high"], current_ob["low"]
            if entry_zone_top is None:
                zones = _get_fvg_zones(df_m5_slice, 0, len(df_m5_slice))
                for zt, zb, zd in reversed(zones):
                    if zd == bias:
                        entry_zone_top, entry_zone_bottom = zt, zb
                        break
            if entry_zone_top is None and getattr(vc, "USE_LIQ_LEVEL_AS_ZONE", False) and liq_level is not None:
                bar_row = entry_df.iloc[i]
                atr_val = atr_series.iloc[i] if i < len(atr_series) and atr_series is not None else np.nan
                atr_val = float(atr_val) if not pd.isna(atr_val) and atr_val > 0 else (bar_row["high"] - bar_row["low"]) * 2
                half = atr_val * getattr(vc, "LIQ_ZONE_ATR_MULT", 0.5)
                if bias == "BULLISH":
                    entry_zone_bottom = float(liq_level) - half
                    entry_zone_top = float(liq_level) + half
                else:
                    entry_zone_top = float(liq_level) + half
                    entry_zone_bottom = float(liq_level) - half
            if entry_zone_top is None and not getattr(vc, "REQUIRE_5M_SWEEP", True):
                bar_row = entry_df.iloc[i]
                atr_val = atr_series.iloc[i] if i < len(atr_series) and atr_series is not None else np.nan
                atr_val = float(atr_val) if not pd.isna(atr_val) and atr_val > 0 else (bar_row["high"] - bar_row["low"]) * 2
                mid = (bar_row["high"] + bar_row["low"]) / 2
                half = atr_val * getattr(vc, "LIQ_ZONE_ATR_MULT", 0.5)
                entry_zone_bottom = mid - half
                entry_zone_top = mid + half
            if entry_zone_top is None:
                continue

            df_m1_slice = entry_df.iloc[: i + 1]
            if len(df_m1_slice) < 20:
                continue

            row = entry_df.iloc[i]
            in_zone = _price_in_zone(row["low"], row["high"], entry_zone_top, entry_zone_bottom)
            if not in_zone:
                continue

            triggered, entry_price, trigger_reason = self.checkEntryTrigger(
                df_m1_slice, "BUY" if bias == "BULLISH" else "SELL",
                entry_zone_top, entry_zone_bottom, i,
            )
            if not triggered or entry_price is None:
                continue

            m5_bar_ts = idx.floor("5min") if hasattr(idx, "floor") else pd.Timestamp(idx).floor("5min")
            if max_per_setup is not None and trades_per_5m_setup.get(m5_bar_ts, 0) >= max_per_setup:
                continue

            print(f"[Vester] HTF bias detected ({bias})")
            print("[Vester] 5M sweep detected")
            print("[Vester] 5M BOS detected")
            print("[Vester] 1M trigger detected")

            if current_ob is None:
                current_ob = {"high": entry_zone_top, "low": entry_zone_bottom, "midpoint": (entry_zone_top + entry_zone_bottom) / 2}

            sl_method = getattr(vc, "SL_METHOD", "OB")
            sl_atr_mult = getattr(vc, "SL_ATR_MULT", 0.5)
            sl_micro_tf = getattr(vc, "SL_MICRO_TF", "1m")
            pip = 0.01 if "XAU" in str(self.symbol or "") or "GC" in str(self.symbol or "") else 0.0001

            if sl_method == "HYBRID":
                micro_df = df_m1_slice if sl_micro_tf == "1m" else df_m5_slice
                micro_atr = atr_series if sl_micro_tf == "1m" else atr_m5
                base_swing = None
                if bias == "BULLISH":
                    swing_lows = micro_df[micro_df["swing_low"] == True]
                    if not swing_lows.empty:
                        base_swing = float(swing_lows.iloc[-1]["swing_low_price"])
                else:
                    swing_highs = micro_df[micro_df["swing_high"] == True]
                    if not swing_highs.empty:
                        base_swing = float(swing_highs.iloc[-1]["swing_high_price"])
                if base_swing is not None and micro_atr is not None:
                    if sl_micro_tf == "5m":
                        m5_up_to = self.df_m5[self.df_m5.index <= idx]
                        if not m5_up_to.empty:
                            last_m5_idx = m5_up_to.index[-1]
                            atr_val = atr_m5.loc[last_m5_idx] if last_m5_idx in atr_m5.index else np.nan
                        else:
                            atr_val = np.nan
                    else:
                        atr_val = atr_series.iloc[i] if i < len(atr_series) else np.nan
                    atr_val = float(atr_val) if not pd.isna(atr_val) and atr_val > 0 else (row["high"] - row["low"]) * 2
                    buf = atr_val * sl_atr_mult
                    if bias == "BULLISH":
                        sl = base_swing - buf
                        if sl >= entry_price:
                            sl = entry_price - pip
                    else:
                        sl = base_swing + buf
                        if sl <= entry_price:
                            sl = entry_price + pip
                else:
                    sl_method = "OB"
            if sl_method != "HYBRID":
                sl_buffer = config.get_symbol_config(self.symbol, "VESTER_SL_BUFFER") or vc.SL_BUFFER
                buf = sl_buffer * pip
                if bias == "BULLISH":
                    sl = current_ob["low"] - buf
                    if sl >= entry_price:
                        sl = entry_price - pip
                else:
                    sl = current_ob["high"] + buf
                    if sl <= entry_price:
                        sl = entry_price + pip

            if bias == "BULLISH":
                future_highs = self.df_m5[(self.df_m5.index > idx) & (self.df_m5["swing_high"] == True)].head(3)
                tp = future_highs.iloc[0]["swing_high_price"] if not future_highs.empty else None
                sl_dist = entry_price - sl
                min_tp = entry_price + sl_dist * min_rr
                if tp is None or tp < min_tp:
                    tp = min_tp
            else:
                future_lows = self.df_m5[(self.df_m5.index > idx) & (self.df_m5["swing_low"] == True)].head(3)
                tp = future_lows.iloc[0]["swing_low_price"] if not future_lows.empty else None
                sl_dist = sl - entry_price
                min_tp = entry_price - sl_dist * min_rr
                if tp is None or tp > min_tp:
                    tp = min_tp

            spread_pips = config.get_symbol_config(self.symbol, "BACKTEST_SPREAD_PIPS") or getattr(config, "BACKTEST_SPREAD_PIPS", 2.0)
            max_spread = config.get_symbol_config(self.symbol, "VESTER_MAX_SPREAD_POINTS") or vc.MAX_SPREAD_POINTS
            pip_size = 0.01 if "XAU" in str(self.symbol or "") or "GC" in str(self.symbol or "") else 0.0001
            spread_points = spread_pips * (pip_size * 10 if pip_size == 0.0001 else 1)
            if spread_points > max_spread:
                continue

            atr_val = atr_series.iloc[i] if i < len(atr_series) and atr_series is not None else np.nan
            if not pd.isna(atr_val) and atr_val > 0:
                bar_range = row["high"] - row["low"]
                if bar_range > atr_val * vc.MAX_CANDLE_VOLATILITY_ATR_MULT:
                    continue

            if vc.USE_NEWS_FILTER:
                if not is_news_safe(
                    current_time,
                    vc.NEWS_BUFFER_MINUTES,
                    vc.NEWS_BUFFER_MINUTES,
                    True,
                    ["United States", "Euro Zone"],
                    "investpy",
                    getattr(config, "FCSAPI_KEY", None),
                ):
                    continue

            htf_label = "1H+4H" if getattr(vc, "REQUIRE_4H_BIAS", False) else "1H"
            reason = f"Vester: {htf_label} {bias} + 5M setup + {trigger_reason}"
            sig = self.placeTrade("BUY" if bias == "BULLISH" else "SELL", entry_price, sl, tp, idx, reason)
            sig["setup_5m"] = m5_bar_ts
            signals.append(sig)
            trades_per_5m_setup[m5_bar_ts] = trades_per_5m_setup.get(m5_bar_ts, 0) + 1
            trades_per_session[session_key] = trades_per_session.get(session_key, 0) + 1
            trades_per_day[day_key] = trades_per_day.get(day_key, 0) + 1

        return pd.DataFrame(signals)
