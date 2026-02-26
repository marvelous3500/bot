"""
VeeStrategy: 1H bias -> 15m CHOCH -> OB+FVG -> entry on return to OB zone with 1m confirmation (BOS or FVG in zone).
SL slightly beyond OB; TP 3R. Use --revert-vee to restore snapshot (candle-in-zone entry, no 1m confirmation).
"""

from typing import Optional, Dict, Any, Tuple, List

import numpy as np
import pandas as pd

import config
from .. import vee_config as vc
from ..indicators import detect_fvg
from ..indicators_bos import (
    detect_swing_highs_lows,
    detect_break_of_structure,
    identify_order_block,
)
from .base import BaseStrategy


def _price_in_zone(bar_low: float, bar_high: float, zone_top: float, zone_bottom: float) -> bool:
    """Check if bar intersects zone [zone_bottom, zone_top]."""
    return not (bar_high < zone_bottom or bar_low > zone_top)


class VeeStrategy(BaseStrategy):
    """
    Step 1: 1H for bias.
    Step 2: 15m find CHOCH (BOS).
    Step 3: Find OB that caused CHOCH, with FVG.
    Step 4: Entry when price returns to OB zone; SL slightly beyond OB; TP 3R.
    """

    def __init__(
        self,
        df_h1: pd.DataFrame,
        df_m15: pd.DataFrame,
        df_m1: pd.DataFrame,
        symbol: Optional[str] = None,
        verbose: bool = False,
    ):
        self.df_h1 = df_h1.copy() if df_h1 is not None and not df_h1.empty else df_h1
        self.df_m15 = df_m15.copy() if df_m15 is not None and not df_m15.empty else df_m15
        self.df_m1 = df_m1.copy() if df_m1 is not None and not df_m1.empty else df_m1
        self.symbol = symbol
        self.verbose = verbose

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"[Vee] {msg}")

    def prepare_data(self) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Run swing, BOS, FVG on H1, M15 and M1 (1m used for entry confirmation)."""
        swing_len = vc.SWING_LENGTH
        for name, ref in [("H1", "df_h1"), ("M15", "df_m15"), ("M1", "df_m1")]:
            df = getattr(self, ref)
            if df is None or df.empty:
                continue
            self._log(f"Detecting swing/BOS/FVG on {name}...")
            df = detect_swing_highs_lows(df, swing_length=swing_len)
            df = detect_break_of_structure(df)
            df = detect_fvg(df)
            setattr(self, ref, df)
        return self.df_h1, self.df_m15, self.df_m1

    # ---- HTF bias (1H) ----

    def _detect_htf_bias(self, ts: pd.Timestamp) -> Optional[str]:
        """Use most recent BOS in H1 lookback (more open: don't require last bar to be BOS)."""
        if self.df_h1 is None or self.df_h1.empty:
            return None
        df = self.df_h1[self.df_h1.index <= ts].tail(vc.HTF_LOOKBACK_HOURS)
        if df.empty or len(df) < 3:
            return None
        # Prefer last bar BOS; else use most recent BOS in lookback
        for idx in range(len(df) - 1, -1, -1):
            row = df.iloc[idx]
            if row.get("bos_bull"):
                return "BULLISH"
            if row.get("bos_bear"):
                return "BEARISH"
        return None

    # ---- 15m: CHOCH (BOS) + OB that caused it + FVG ----

    def _find_m15_setups(self) -> List[Dict[str, Any]]:
        """Step 2 & 3: Find 15m CHOCH (BOS), then OB that caused it; require FVG on/near CHOCH."""
        setups: List[Dict[str, Any]] = []
        df = self.df_m15
        if df is None or df.empty or "fvg_bull" not in df.columns:
            return setups
        ob_lookback = getattr(vc, "OB_LOOKBACK", 20)

        for i in range(2, len(df)):
            row = df.iloc[i]
            ts = df.index[i]

            # Step 2: CHOCH = BOS
            if row.get("bos_bull"):
                ob = identify_order_block(df, i, ob_lookback=ob_lookback)
                if ob is None:
                    continue
                # Step 3: require FVG (bullish) on CHOCH bar or OB bar
                has_fvg = bool(row.get("fvg_bull"))
                if not has_fvg and i >= 1:
                    has_fvg = bool(df.iloc[i - 1].get("fvg_bull"))
                ob_idx = max(0, i - ob_lookback)
                for j in range(i - 1, ob_idx - 1, -1):
                    if j >= 0 and df.iloc[j].get("fvg_bull"):
                        has_fvg = True
                        break
                if not has_fvg:
                    continue
                setups.append({
                    "direction": "BULLISH",
                    "ob_high": float(ob["high"]),
                    "ob_low": float(ob["low"]),
                    "choch_time": ts,
                })
                continue
            if row.get("bos_bear"):
                ob = identify_order_block(df, i, ob_lookback=ob_lookback)
                if ob is None:
                    continue
                has_fvg = bool(row.get("fvg_bear"))
                if not has_fvg and i >= 1:
                    has_fvg = bool(df.iloc[i - 1].get("fvg_bear"))
                ob_idx = max(0, i - ob_lookback)
                for j in range(i - 1, ob_idx - 1, -1):
                    if j >= 0 and df.iloc[j].get("fvg_bear"):
                        has_fvg = True
                        break
                if not has_fvg:
                    continue
                setups.append({
                    "direction": "BEARISH",
                    "ob_high": float(ob["high"]),
                    "ob_low": float(ob["low"]),
                    "choch_time": ts,
                })

        return setups

    def run_backtest(self) -> pd.DataFrame:
        """Step 4: Entry when price returns to OB zone; SL slightly beyond OB; TP 3R."""
        if self.df_h1 is None or self.df_m15 is None or self.df_m1 is None:
            return pd.DataFrame()

        self.prepare_data()

        setups = self._find_m15_setups()
        if not setups:
            return pd.DataFrame()

        entry_df = self.df_m1
        signals: List[Dict[str, Any]] = []
        trades_per_session: Dict[str, int] = {}
        entry_window = getattr(config, "VEE_ENTRY_WINDOW_MINUTES", 120)
        rr = vc.MIN_RR
        buffer_pts = getattr(vc, "SL_BUFFER_POINTS", 0.0) or 0.0
        if "XAU" in str(self.symbol or "") or "GC" in str(self.symbol or ""):
            pip = 0.01
        else:
            pip = 0.0001

        for i in range(20, len(entry_df)):
            idx = entry_df.index[i]
            current_time = idx if hasattr(idx, "hour") else pd.Timestamp(idx)

            if getattr(config, "BACKTEST_EXCLUDE_WEEKENDS", False) and current_time.weekday() >= 5:
                continue

            session_key = config.TRADE_SESSION_HOURS.get(current_time.hour, "other")
            if trades_per_session.get(session_key, 0) >= vc.MAX_TRADES_PER_SESSION:
                continue

            bias = self._detect_htf_bias(current_time)
            if bias is None:
                continue

            if vc.USE_PREMIUM_DISCOUNT and self.df_h1 is not None:
                df_slice = self.df_h1[self.df_h1.index <= current_time].tail(getattr(vc, "EQUILIBRIUM_LOOKBACK", 24))
                if not df_slice.empty:
                    eq = (df_slice["high"].max() + df_slice["low"].min()) / 2.0
                    close = float(entry_df.iloc[i]["close"])
                    if bias == "BULLISH" and close > eq:
                        continue
                    if bias == "BEARISH" and close < eq:
                        continue

            relevant = [
                s for s in setups
                if s["direction"] == bias
                and s["choch_time"] <= current_time
                and (current_time - s["choch_time"]).total_seconds() <= entry_window * 60
            ]
            if not relevant:
                continue
            setup = relevant[-1]
            ob_high = setup["ob_high"]
            ob_low = setup["ob_low"]

            bar = entry_df.iloc[i]
            if not _price_in_zone(bar["low"], bar["high"], ob_high, ob_low):
                continue

            direction = "BUY" if bias == "BULLISH" else "SELL"
            use_1m_conf = getattr(config, "VEE_USE_1M_CONFIRMATION", True)
            if use_1m_conf:
                if direction == "BUY":
                    m1_bos_ok = bool(bar.get("bos_bull"))
                    m1_fvg_ok = bool(bar.get("fvg_bull")) and bar["close"] > bar["open"]
                    if not (m1_bos_ok or m1_fvg_ok):
                        continue
                else:
                    m1_bos_ok = bool(bar.get("bos_bear"))
                    m1_fvg_ok = bool(bar.get("fvg_bear")) and bar["close"] < bar["open"]
                    if not (m1_bos_ok or m1_fvg_ok):
                        continue

            if direction == "BUY":
                if bar["close"] <= bar["open"]:
                    continue
                entry_price = float(bar["close"])
            else:
                if bar["close"] >= bar["open"]:
                    continue
                entry_price = float(bar["close"])

            if direction == "BUY":
                sl = ob_low - pip - buffer_pts
                sl_dist = entry_price - sl
                if sl_dist <= 0:
                    continue
                tp = entry_price + sl_dist * rr
            else:
                sl = ob_high + pip + buffer_pts
                sl_dist = sl - entry_price
                if sl_dist <= 0:
                    continue
                tp = entry_price - sl_dist * rr

            signals.append({
                "time": current_time,
                "type": direction,
                "price": entry_price,
                "sl": sl,
                "tp": tp,
                "reason": f"Vee: 1H {bias} + 15m CHOCH/OB+FVG + 1m conf, entry on OB zone",
                "setup_15m": setup["choch_time"],
            })
            trades_per_session[session_key] = trades_per_session.get(session_key, 0) + 1

        return pd.DataFrame(signals)

