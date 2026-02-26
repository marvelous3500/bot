"""
V1 Strategy: H1 Bias (FVG/OB/Sweep) -> 5M BOS + Displacement FVG -> Retest Entry.

Filters:
  1. 5M BOS required before FVG confirmation
  2. Displacement candle on FVG-creating move (1.2x threshold)
  3. Session filter on entry: London (07-10 UTC) and New York (13-16 UTC)
  4. Setup timeout: 144 bars (~12 hours on 5M)
  5. Recent H1 zones only (last 30 H1 bars)
  6. R:R 2:1 for higher win rate
"""
import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime

import config
from ..v1_config import (
    V1_HTF_LOOKBACK_BARS,
    V1_LIQUIDITY_LOOKBACK,
    V1_CONFIRMATION_LOOKBACK,
    V1_MIN_RR,
)
from ..indicators import (
    detect_fvg,
    detect_displacement,
    calculate_pdl_pdh,
)
from ..indicators_bos import (
    detect_swing_highs_lows,
    detect_break_of_structure,
    identify_order_block,
)
from .base import BaseStrategy

# Setup expires after this many 5M bars (~12 hours)
_SETUP_TIMEOUT_BARS = 144

# Displacement threshold
_DISPLACEMENT_THRESHOLD = 1.2

def _get_v1_rr() -> float:
    """Risk:Reward used for TP placement (closer TP = higher win rate)."""
    try:
        return float(getattr(config, "V1_MIN_RR", V1_MIN_RR))
    except (TypeError, ValueError):
        return float(V1_MIN_RR)


def _get_v1_sl_buffer() -> float:
    """Optional SL buffer in price units (e.g. XAU points)."""
    try:
        return float(getattr(config, "V1_SL_BUFFER", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _get_v1_require_rejection() -> bool:
    """Require a directional rejection candle on retest (fewer trades, better quality)."""
    return bool(getattr(config, "V1_REQUIRE_RETEST_REJECTION", True))


class V1Strategy(BaseStrategy):
    """
    Step 1: Bias Zone (H1 FVG/OB tap OR PDH/PDL Sweep)
    Step 2: 5M BOS in bias direction
    Step 3: 5M Displacement FVG in bias direction
    Step 4: 5M FVG Retest → Entry (London/NY only)
    """

    def __init__(
        self,
        df_h1: pd.DataFrame,
        df_m5: pd.DataFrame,
        daily_df: Optional[pd.DataFrame] = None,
        symbol: Optional[str] = None,
        verbose: bool = False,
    ):
        self.df_h1 = df_h1.copy() if df_h1 is not None else None
        self.df_m5 = df_m5.copy() if df_m5 is not None else None
        self.daily_df = daily_df.copy() if daily_df is not None else None
        self.symbol = symbol
        self.verbose = verbose

    def _log(self, msg: str):
        if self.verbose:
            print(f"[V1] {msg}")

    def prepare_data(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Run indicators on H1 and 5M."""
        if self.df_h1 is not None:
            self._log("Detecting structures on H1...")
            self.df_h1 = detect_swing_highs_lows(self.df_h1, swing_length=3)
            self.df_h1 = detect_break_of_structure(self.df_h1)
            self.df_h1 = detect_fvg(self.df_h1)

        if self.df_m5 is not None:
            self._log("Detecting structures on 5M...")
            self.df_m5 = detect_swing_highs_lows(self.df_m5, swing_length=3)
            self.df_m5 = detect_break_of_structure(self.df_m5)
            self.df_m5 = detect_fvg(self.df_m5)
            self.df_m5 = detect_displacement(self.df_m5, threshold=_DISPLACEMENT_THRESHOLD, window=10)

        return self.df_h1, self.df_m5

    def _get_h1_zones(self, bar_time: pd.Timestamp) -> List[Dict[str, Any]]:
        """Return RECENT H1 FVG and OB zones."""
        if self.df_h1 is None:
            return []

        df_lte = self.df_h1[self.df_h1.index <= bar_time]
        if len(df_lte) < 5:
            return []

        end_idx = len(df_lte)
        # Use configurable HTF lookback (more bars = more zones = more potential trades)
        lookback = max(10, int(V1_HTF_LOOKBACK_BARS or 50))
        start_idx = max(2, end_idx - lookback)
        zones = []

        for i in range(start_idx, end_idx):
            row = df_lte.iloc[i]
            if row.get("fvg_bull"):
                top = row["low"]
                bottom = df_lte.iloc[i - 2]["high"]
                if top > bottom:
                    zones.append({"type": "FVG", "direction": "BULLISH", "top": top, "bottom": bottom})
            if row.get("fvg_bear"):
                top = df_lte.iloc[i - 2]["low"]
                bottom = row["high"]
                if top > bottom:
                    zones.append({"type": "FVG", "direction": "BEARISH", "top": top, "bottom": bottom})
            if row.get("bos_bull"):
                ob = identify_order_block(df_lte, i, ob_lookback=20)
                if ob and ob["direction"] == "BULLISH":
                    zones.append({"type": "OB", "direction": "BULLISH", "top": ob["high"], "bottom": ob["low"]})
            if row.get("bos_bear"):
                ob = identify_order_block(df_lte, i, ob_lookback=20)
                if ob and ob["direction"] == "BEARISH":
                    zones.append({"type": "OB", "direction": "BEARISH", "top": ob["high"], "bottom": ob["low"]})
        return zones

    @staticmethod
    def _in_session(ts: pd.Timestamp) -> bool:
        """Return True if timestamp is in an allowed trading session.

        By default uses config.TRADE_SESSION_HOURS keys:
        - Asian 0-4, London 7-10, NY 13-16 (more opportunities per day).
        """
        if ts.tzinfo is not None:
            utc_hour = ts.tz_convert("UTC").hour
        else:
            utc_hour = ts.hour
        hours_map = getattr(config, "TRADE_SESSION_HOURS", None)
        if isinstance(hours_map, dict) and hours_map:
            return utc_hour in hours_map
        # Fallback: London + NY only
        return utc_hour in {7, 8, 9, 10, 13, 14, 15, 16}

    def _is_displacement(self, idx: int) -> bool:
        """Check if the candle at idx is a displacement candle."""
        row = self.df_m5.iloc[idx]
        return bool(row.get("displacement_bull") or row.get("displacement_bear"))

    def _last_swing_sl(self, end_idx: int, direction: str, lookback: int = 25) -> Optional[float]:
        """Return a swing-based SL candidate near end_idx (helps avoid tight stops)."""
        if self.df_m5 is None or self.df_m5.empty:
            return None
        start = max(0, end_idx - lookback)
        sl = None
        if direction == "BULLISH":
            for j in range(end_idx, start - 1, -1):
                r = self.df_m5.iloc[j]
                if r.get("swing_low") and r.get("swing_low_price") is not None:
                    try:
                        sl = float(r.get("swing_low_price"))
                    except (TypeError, ValueError):
                        sl = None
                    break
        else:
            for j in range(end_idx, start - 1, -1):
                r = self.df_m5.iloc[j]
                if r.get("swing_high") and r.get("swing_high_price") is not None:
                    try:
                        sl = float(r.get("swing_high_price"))
                    except (TypeError, ValueError):
                        sl = None
                    break
        return sl

    @staticmethod
    def _retest_rejection_ok(bar: pd.Series, direction: str, zone_top: float, zone_bottom: float) -> bool:
        """Simple rejection confirmation on retest bar."""
        try:
            o, h, l, c = float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])
        except (TypeError, ValueError, KeyError):
            return False
        if h <= l:
            return False
        mid = (zone_top + zone_bottom) / 2.0
        if direction == "BULLISH":
            touched = l <= zone_top and h >= zone_bottom
            return touched and (c > o) and (c >= mid)
        touched = h >= zone_bottom and l <= zone_top
        return touched and (c < o) and (c <= mid)

    def _is_premium_discount(self, bar_time: pd.Timestamp, direction: str) -> bool:
        """Check if current price is in the correct zone.
        BUY only in discount (below 50% of recent H1 range).
        SELL only in premium (above 50% of recent H1 range).
        """
        # Optional: when disabled, this filter is skipped for more trades
        if not getattr(config, "V1_USE_PREMIUM_DISCOUNT", False):
            return True
        if self.df_h1 is None:
            return True  # Skip filter if no H1 data
        df_lte = self.df_h1[self.df_h1.index <= bar_time]
        if len(df_lte) < 20:
            return True
        recent = df_lte.tail(20)
        range_high = recent["high"].max()
        range_low = recent["low"].min()
        mid = (range_high + range_low) / 2
        last_close = df_lte.iloc[-1]["close"]
        if direction == "BULLISH":
            return last_close <= mid  # Discount zone
        else:
            return last_close >= mid  # Premium zone

    def run_backtest(self) -> pd.DataFrame:
        """Run strategy with all quality filters."""
        if self.df_m5 is None or self.df_m5.empty:
            return pd.DataFrame()

        self.prepare_data()
        signals = []

        setup_active = None
        setup_zone = None
        setup_start_idx = None
        bos_confirmed = False
        confirmation_fvg = None

        for i in range(3, len(self.df_m5)):
            current_bar = self.df_m5.iloc[i]
            current_time = self.df_m5.index[i]

            # --- TIMEOUT ---
            if setup_active and setup_start_idx is not None:
                if (i - setup_start_idx) > _SETUP_TIMEOUT_BARS:
                    self._log(f"Timeout at {current_time}")
                    setup_active = None
                    setup_zone = None
                    setup_start_idx = None
                    bos_confirmed = False
                    confirmation_fvg = None

            # --- STEP 1: H1 BIAS ZONE TAP (any session) ---
            if setup_active is None:
                bias_zones = self._get_h1_zones(current_time)
                pdh, pdl = (None, None)
                if self.daily_df is not None:
                    pdh, pdl = calculate_pdl_pdh(self.daily_df, current_time)

                # Bullish
                bullish_tap = False
                for zone in bias_zones:
                    if zone["direction"] == "BULLISH" and current_bar["low"] <= zone["top"] and current_bar["high"] >= zone["bottom"]:
                        bullish_tap = True
                        setup_zone = zone
                        break
                if not bullish_tap and pdl and current_bar["low"] < pdl and current_bar["close"] > pdl:
                    bullish_tap = True
                    setup_zone = {"type": "LIQUIDITY", "direction": "BULLISH", "level": pdl}

                if bullish_tap:
                    setup_active = "BULLISH"
                    setup_start_idx = i
                    bos_confirmed = False
                    confirmation_fvg = None
                    self._log(f"Step 1: Bullish H1 setup at {current_time} ({setup_zone['type']})")
                    continue

                # Bearish
                bearish_tap = False
                for zone in bias_zones:
                    if zone["direction"] == "BEARISH" and current_bar["high"] >= zone["bottom"] and current_bar["low"] <= zone["top"]:
                        bearish_tap = True
                        setup_zone = zone
                        break
                if not bearish_tap and pdh and current_bar["high"] > pdh and current_bar["close"] < pdh:
                    bearish_tap = True
                    setup_zone = {"type": "LIQUIDITY", "direction": "BEARISH", "level": pdh}

                if bearish_tap:
                    setup_active = "BEARISH"
                    setup_start_idx = i
                    bos_confirmed = False
                    confirmation_fvg = None
                    self._log(f"Step 1: Bearish H1 setup at {current_time} ({setup_zone['type']})")
                continue

            # --- STEP 2: 5M BOS ---
            if not bos_confirmed:
                if setup_active == "BULLISH" and current_bar.get("bos_bull"):
                    bos_confirmed = True
                    self._log(f"Step 2: 5M Bullish BOS at {current_time}")
                elif setup_active == "BEARISH" and current_bar.get("bos_bear"):
                    bos_confirmed = True
                    self._log(f"Step 2: 5M Bearish BOS at {current_time}")
                continue

            # --- STEP 3: 5M FVG with displacement ---
            if confirmation_fvg is None:
                is_disp = self._is_displacement(i)
                if setup_active == "BULLISH" and current_bar.get("fvg_bull") and is_disp:
                    top = current_bar["low"]
                    bottom = self.df_m5.iloc[i - 2]["high"]
                    if top > bottom:
                        confirmation_fvg = {"top": top, "bottom": bottom, "time": current_time}
                        self._log(f"Step 3: 5M Bullish FVG at {current_time}")
                elif setup_active == "BEARISH" and current_bar.get("fvg_bear") and is_disp:
                    top = self.df_m5.iloc[i - 2]["low"]
                    bottom = current_bar["high"]
                    if top > bottom:
                        confirmation_fvg = {"top": top, "bottom": bottom, "time": current_time}
                        self._log(f"Step 3: 5M Bearish FVG at {current_time}")
                continue

            # --- STEP 4: RETEST ENTRY (London/NY + premium/discount filter) ---
            if not self._in_session(current_time):
                continue
            if not self._is_premium_discount(current_time, setup_active):
                continue
            if _get_v1_require_rejection():
                if not self._retest_rejection_ok(current_bar, setup_active, confirmation_fvg["top"], confirmation_fvg["bottom"]):
                    continue
            entered = False
            if setup_active == "BULLISH":
                if current_bar["low"] <= confirmation_fvg["top"] and current_bar["high"] >= confirmation_fvg["bottom"]:
                    price = float(confirmation_fvg["top"])
                    rr_ratio = _get_v1_rr()
                    buf = _get_v1_sl_buffer()
                    swing_sl = self._last_swing_sl(i, "BULLISH")
                    sl_raw = float(confirmation_fvg["bottom"])
                    if swing_sl is not None:
                        sl_raw = min(sl_raw, float(swing_sl))
                    sl = sl_raw - buf
                    sl_dist = price - sl
                    if sl_dist > 0:
                        tp = price + sl_dist * rr_ratio
                        signals.append({
                            "time": current_time, "type": "BUY", "price": price,
                            "sl": sl, "tp": tp,
                            "reason": f"V1: 5M FVG retest + BOS after H1 {setup_zone['type']}",
                        })
                        self._log(f"Step 4: BUY at {current_time}")
                        entered = True
            elif setup_active == "BEARISH":
                if current_bar["high"] >= confirmation_fvg["bottom"] and current_bar["low"] <= confirmation_fvg["top"]:
                    price = float(confirmation_fvg["bottom"])
                    rr_ratio = _get_v1_rr()
                    buf = _get_v1_sl_buffer()
                    swing_sl = self._last_swing_sl(i, "BEARISH")
                    sl_raw = float(confirmation_fvg["top"])
                    if swing_sl is not None:
                        sl_raw = max(sl_raw, float(swing_sl))
                    sl = sl_raw + buf
                    sl_dist = sl - price
                    if sl_dist > 0:
                        tp = price - sl_dist * rr_ratio
                        signals.append({
                            "time": current_time, "type": "SELL", "price": price,
                            "sl": sl, "tp": tp,
                            "reason": f"V1: 5M FVG retest + BOS after H1 {setup_zone['type']}",
                        })
                        self._log(f"Step 4: SELL at {current_time}")
                        entered = True

            if entered:
                setup_active = None
                setup_zone = None
                setup_start_idx = None
                bos_confirmed = False
                confirmation_fvg = None

        return pd.DataFrame(signals) if signals else pd.DataFrame()
