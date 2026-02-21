"""
NAS-STRATEGY: NAS100 (Nasdaq Index) ICT-style trading.
Only trades after manipulation is complete and real directional movement begins.
Strict 8-step entry sequence.
"""
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional, Dict, Any

import config
from ..diagnostics import NASDiagnosticCollector
from .. import nas_config as nc
from ..indicators import detect_fvg, detect_displacement
from ..indicators_bos import (
    detect_swing_highs_lows,
    detect_break_of_structure,
    identify_order_block,
)
from ..indicators_nas import detect_liquidity_sweep_m15, get_fvg_zones
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
    """Check if any candle touched zone and showed reaction."""
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


def calculate_h1_bias(
    df_h1: pd.DataFrame,
    lookback_hours: int,
    wick_pct: float,
    body_pct: float,
) -> Dict[str, Any]:
    """H1 bias: BOS + OB/FVG + zone respect. Returns {bias, proof, reason}."""
    if df_h1 is None or df_h1.empty or len(df_h1) < 5:
        return {"bias": "NEUTRAL", "proof": None, "reason": "missing H1 data"}
    df = df_h1.tail(lookback_hours).copy()
    df = detect_swing_highs_lows(df, swing_length=nc.SWING_LENGTH)
    df = detect_break_of_structure(df)
    df = detect_fvg(df)
    last = df.iloc[-1]
    bias = "NEUTRAL"
    if last.get("bos_bull"):
        bias = "BULLISH"
    elif last.get("bos_bear"):
        bias = "BEARISH"
    if bias == "NEUTRAL":
        return {"bias": "NEUTRAL", "proof": None, "reason": "no H1 BOS"}
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
                return {
                    "bias": bias,
                    "proof": {"structure": "BOS", "zone_coordinates": (zone_top, zone_bottom)},
                    "reason": f"H1 {bias} BOS + zone confirmed",
                }
    return {"bias": "NEUTRAL", "proof": None, "reason": "no zone respect"}


def calculate_4h_bias(
    df_4h: pd.DataFrame,
    h1_bias: str,
    lookback_bars: int,
    wick_pct: float,
    body_pct: float,
) -> Dict[str, Any]:
    """4H bias: directional validator. Returns {bias, confidence, reason}."""
    if df_4h is None or df_4h.empty or len(df_4h) < 5:
        return {"bias": "NEUTRAL", "confidence": "NEUTRAL", "reason": "missing 4H data"}
    df = df_4h.tail(lookback_bars).copy()
    df = detect_swing_highs_lows(df, swing_length=nc.SWING_LENGTH)
    df = detect_break_of_structure(df)
    df = detect_fvg(df)
    last = df.iloc[-1]
    bias = "NEUTRAL"
    if last.get("bos_bull"):
        bias = "BULLISH"
    elif last.get("bos_bear"):
        bias = "BEARISH"
    if bias == "NEUTRAL":
        return {"bias": "NEUTRAL", "confidence": "NEUTRAL", "reason": "4H neutral, H1-only"}
    if bias != h1_bias:
        return {"bias": bias, "confidence": "CONFLICT", "reason": "4H bias conflicts H1"}
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
                return {"bias": bias, "confidence": "HIGH", "reason": "4H agrees with H1"}
    return {"bias": bias, "confidence": "NEUTRAL", "reason": "4H agrees, no zone"}


def _parse_kz(kz_tuple):
    """Parse ('08:00','10:00') to (8, 10) hours."""
    if not kz_tuple or len(kz_tuple) < 2:
        return None, None
    try:
        h1, m1 = map(int, str(kz_tuple[0]).split(":"))
        h2, m2 = map(int, str(kz_tuple[1]).split(":"))
        return h1 * 60 + m1, h2 * 60 + m2
    except (ValueError, AttributeError):
        return None, None


def is_nas_session_allowed(current_time, cfg=None) -> bool:
    """Check if current time is in allowed session/kill zone."""
    cfg = cfg or nc
    hour = current_time.hour if hasattr(current_time, "hour") else getattr(current_time, "hour", 0)
    if hasattr(current_time, "minute"):
        minute = current_time.minute
    else:
        minute = 0
    total_min = hour * 60 + minute
    if getattr(cfg, "TRADE_ONLY_KILLZONES", True):
        london = _parse_kz(getattr(cfg, "LONDON_KZ", ("08:00", "10:00")))
        ny = _parse_kz(getattr(cfg, "NY_KZ", ("14:30", "16:30")))
        if london[0] is not None and london[1] is not None:
            if getattr(cfg, "ENABLE_LONDON", True) and london[0] <= total_min < london[1]:
                return True
        if ny[0] is not None and ny[1] is not None:
            if getattr(cfg, "ENABLE_NEWYORK", True) and ny[0] <= total_min < ny[1]:
                return True
        return False
    if getattr(cfg, "ENABLE_LONDON", True):
        if 8 <= hour < 12:
            return True
    if getattr(cfg, "ENABLE_NEWYORK", True):
        if 14 <= hour < 18:
            return True
    if getattr(cfg, "ENABLE_ASIA", False):
        if 0 <= hour < 5:
            return True
    return False


def apply_filters(
    current_time,
    atr_val: float,
    spread: float,
    cfg=None,
) -> Dict[str, Any]:
    """Apply session, news, volatility filters. Returns {passed, reason}."""
    cfg = cfg or nc
    if not is_nas_session_allowed(current_time, cfg):
        return {"passed": False, "reason": "outside session"}
    if getattr(cfg, "AVOID_NEWS", True):
        if not is_news_safe(
            current_time,
            getattr(cfg, "NEWS_BUFFER_BEFORE", 20),
            getattr(cfg, "NEWS_BUFFER_AFTER", 20),
            True,
            getattr(cfg, "NEWS_COUNTRIES", ["United States", "Euro Zone"]),
            getattr(cfg, "NEWS_API", "investpy"),
            getattr(cfg, "FCSAPI_KEY", None),
        ):
            return {"passed": False, "reason": "news buffer"}
    min_atr = getattr(cfg, "MIN_ATR", 40)
    if atr_val is not None and not np.isnan(atr_val) and float(atr_val) < min_atr:
        return {"passed": False, "reason": "ATR below threshold"}
    max_spread = getattr(cfg, "MAX_SPREAD", 2.5)
    if spread is not None and float(spread) > max_spread:
        return {"passed": False, "reason": "spread too high"}
    return {"passed": True, "reason": "ok"}


def confirm_entry_candle(row, bias: str, fvg_zone: Dict) -> Dict[str, Any]:
    """Check if candle confirms entry: close in FVG, body significant."""
    if fvg_zone is None:
        return {"confirmed": False, "reason": "no FVG zone"}
    top, bottom = fvg_zone.get("top"), fvg_zone.get("bottom")
    if top is None or bottom is None:
        return {"confirmed": False, "reason": "invalid FVG"}
    close = row["close"]
    if bias == "BULLISH":
        if close <= row["open"]:
            return {"confirmed": False, "reason": "bearish candle"}
        if not (bottom <= close <= top):
            return {"confirmed": False, "reason": "close not in FVG"}
        body = close - row["open"]
        rng = row["high"] - row["low"]
        if rng > 0 and body / rng < 0.3:
            return {"confirmed": False, "reason": "body too small"}
        return {"confirmed": True, "reason": "entry confirmed"}
    else:
        if close >= row["open"]:
            return {"confirmed": False, "reason": "bullish candle"}
        if not (bottom <= close <= top):
            return {"confirmed": False, "reason": "close not in FVG"}
        body = row["open"] - close
        rng = row["high"] - row["low"]
        if rng > 0 and body / rng < 0.3:
            return {"confirmed": False, "reason": "body too small"}
        return {"confirmed": True, "reason": "entry confirmed"}


class NasStrategy:
    """NAS-STRATEGY: NAS100 optimized, strict 8-step entry."""

    def __init__(
        self,
        df_h1: pd.DataFrame,
        df_m15: pd.DataFrame,
        df_entry: pd.DataFrame,
        df_4h: Optional[pd.DataFrame] = None,
        symbol: Optional[str] = None,
        verbose: bool = False,
        diagnostic: Optional[NASDiagnosticCollector] = None,
    ):
        self.df_h1 = df_h1.copy() if df_h1 is not None else None
        self.df_4h = df_4h.copy() if df_4h is not None and not df_4h.empty else None
        self.df_m15 = df_m15.copy() if df_m15 is not None else None
        self.df_entry = df_entry.copy() if df_entry is not None else None
        self.symbol = symbol
        self.verbose = verbose
        self.diagnostic = diagnostic

    def _log(self, msg: str):
        if self.verbose:
            print(msg)

    def _reject(self, step: str, reason: str, timestamp=None, h1_idx=None, bias=None, **ctx):
        """Record rejection if diagnostic collector is set."""
        if self.diagnostic is not None:
            self.diagnostic.reject(
                step=step,
                reason=reason,
                timestamp=timestamp,
                h1_idx=h1_idx,
                bias=bias,
                **ctx,
            )

    def prepare_data(self):
        """Run indicators on all timeframes."""
        rt = nc.REACTION_THRESHOLDS
        wick_pct = rt.get("wick_pct", 0.5)
        body_pct = rt.get("body_pct", 0.3)
        for name, df in [("H1", self.df_h1), ("4H", self.df_4h), ("M15", self.df_m15), ("Entry", self.df_entry)]:
            if df is None or df.empty:
                continue
            self._log(f"[NAS] Preparing {name}...")
            df = detect_swing_highs_lows(df, swing_length=nc.SWING_LENGTH)
            df = detect_break_of_structure(df)
            df = detect_fvg(df)
            df = detect_displacement(df, threshold=1.5, window=10)
            df = detect_liquidity_sweep_m15(df, lookback=nc.LIQ_SWEEP_LOOKBACK)
            if name == "H1":
                self.df_h1 = df
            elif name == "4H":
                self.df_4h = df
            elif name == "M15":
                self.df_m15 = df
            else:
                self.df_entry = df
        return self.df_h1, self.df_4h, self.df_m15, self.df_entry

    def run_backtest(self) -> pd.DataFrame:
        """Run backtest with strict 8-step entry sequence."""
        if self.df_h1 is None or self.df_h1.empty or self.df_m15 is None or self.df_m15.empty:
            return pd.DataFrame()
        if self.df_entry is None or self.df_entry.empty:
            self.df_entry = self.df_m15
        rt = nc.REACTION_THRESHOLDS
        wick_pct, body_pct = rt.get("wick_pct", 0.5), rt.get("body_pct", 0.3)
        signals = []
        atr_series = _atr(self.df_m15, 14)
        window_hours = nc.ENTRY_WINDOW_HOURS

        for i_h1 in range(len(self.df_h1)):
            h1_idx = self.df_h1.index[i_h1]
            h1_row = self.df_h1.iloc[i_h1]
            if not h1_row.get("bos_bull") and not h1_row.get("bos_bear"):
                continue
            h1_bias = "BULLISH" if h1_row.get("bos_bull") else "BEARISH"
            if self.diagnostic is not None:
                self.diagnostic.record_h1_bos()

            df_h1_slice = self.df_h1.iloc[: i_h1 + 1].tail(nc.LOOKBACK_H1_HOURS)
            h1_res = calculate_h1_bias(df_h1_slice, nc.LOOKBACK_H1_HOURS, wick_pct, body_pct)
            if h1_res["bias"] == "NEUTRAL":
                self._reject("h1_bias", h1_res.get("reason", "no H1 bias"), h1_idx=h1_idx, bias=h1_bias)
                self._log(f"[NAS] Rejected: no H1 bias")
                continue

            if nc.REQUIRE_4H_BIAS and self.df_4h is not None:
                df_4h_slice = self.df_4h[self.df_4h.index <= h1_idx].tail(nc.LOOKBACK_4H_BARS)
                if not df_4h_slice.empty:
                    h4_res = calculate_4h_bias(
                        df_4h_slice, h1_bias, nc.LOOKBACK_4H_BARS, wick_pct, body_pct
                    )
                    if h4_res.get("confidence") == "CONFLICT":
                        self._reject("4h_conflict", "4H bias conflicts H1", h1_idx=h1_idx, bias=h1_bias)
                        self._log(f"[NAS] Rejected: 4H bias conflict")
                        continue

            future_m15 = self.df_m15[self.df_m15.index > h1_idx]
            next_h1 = h1_idx + pd.Timedelta(hours=window_hours)
            m15_window = future_m15[future_m15.index < next_h1]

            sweep_seen = False
            sweep_level = None
            sweep_high = None
            sweep_low = None
            displacement_seen = False
            fvg_zone = None
            return_to_fvg = False

            for idx_m15, row_m15 in m15_window.iterrows():
                current_time = idx_m15 if hasattr(idx_m15, "hour") else pd.Timestamp(idx_m15)
                atr_val = atr_series.loc[idx_m15] if idx_m15 in atr_series.index else None
                spread = getattr(config, "BACKTEST_SPREAD_PIPS", 0) or 0
                filt = apply_filters(current_time, atr_val, spread, nc)
                if not filt["passed"]:
                    if self.diagnostic is not None:
                        self.diagnostic.record_filter_reject(filt["reason"])
                    continue

                if not sweep_seen:
                    if h1_bias == "BULLISH" and row_m15.get("sweep_low"):
                        size = row_m15.get("sweep_low_size", 0)
                        if size >= nc.MIN_SWEEP_POINTS:
                            sweep_seen = True
                            sweep_level = row_m15["sweep_low_price"]
                            sweep_high = row_m15["high"]
                            sweep_low = row_m15["low"]
                        else:
                            self._reject("sweep_size", f"sweep too small ({size:.1f} < {nc.MIN_SWEEP_POINTS})",
                                        timestamp=idx_m15, h1_idx=h1_idx, bias=h1_bias, size=size, min_required=nc.MIN_SWEEP_POINTS)
                            self._log(f"[NAS] Rejected: sweep too small ({size:.1f})")
                    elif h1_bias == "BEARISH" and row_m15.get("sweep_high"):
                        size = row_m15.get("sweep_high_size", 0)
                        if size >= nc.MIN_SWEEP_POINTS:
                            sweep_seen = True
                            sweep_level = row_m15["sweep_high_price"]
                            sweep_high = row_m15["high"]
                            sweep_low = row_m15["low"]
                        else:
                            self._reject("sweep_size", f"sweep too small ({size:.1f} < {nc.MIN_SWEEP_POINTS})",
                                        timestamp=idx_m15, h1_idx=h1_idx, bias=h1_bias, size=size, min_required=nc.MIN_SWEEP_POINTS)
                            self._log(f"[NAS] Rejected: sweep too small ({size:.1f})")
                    continue

                if not displacement_seen:
                    is_disp = (h1_bias == "BULLISH" and row_m15.get("displacement_bull")) or (
                        h1_bias == "BEARISH" and row_m15.get("displacement_bear")
                    )
                    if not is_disp:
                        continue
                    displacement_seen = True
                    try:
                        loc = self.df_m15.index.get_loc(idx_m15)
                        i_m15 = int(loc) if isinstance(loc, (int, np.integer)) else (loc.start if hasattr(loc, "start") else 0)
                    except (KeyError, TypeError, ValueError):
                        i_m15 = 0
                    if i_m15 < 2:
                        self._reject("displacement_fvg", "displacement did not create FVG (insufficient bars)",
                                    timestamp=idx_m15, h1_idx=h1_idx, bias=h1_bias)
                        self._log(f"[NAS] Rejected: displacement did not create FVG (insufficient bars)")
                        displacement_seen = False
                        continue
                    if h1_bias == "BULLISH" and row_m15.get("fvg_bull"):
                        c1_high = self.df_m15.iloc[i_m15 - 2]["high"]
                        fvg_size = row_m15["low"] - c1_high
                        if fvg_size >= nc.MIN_FVG_SIZE:
                            fvg_zone = {"top": row_m15["low"], "bottom": c1_high, "size": fvg_size}
                        else:
                            self._reject("displacement_fvg", f"FVG too small ({fvg_size:.1f} < {nc.MIN_FVG_SIZE})",
                                        timestamp=idx_m15, h1_idx=h1_idx, bias=h1_bias, fvg_size=fvg_size, min_required=nc.MIN_FVG_SIZE)
                            self._log(f"[NAS] Rejected: FVG too small ({fvg_size:.1f})")
                            displacement_seen = False
                    elif h1_bias == "BEARISH" and row_m15.get("fvg_bear"):
                        c1_low = self.df_m15.iloc[i_m15 - 2]["low"]
                        fvg_size = c1_low - row_m15["high"]
                        if fvg_size >= nc.MIN_FVG_SIZE:
                            fvg_zone = {"top": c1_low, "bottom": row_m15["high"], "size": fvg_size}
                        else:
                            self._reject("displacement_fvg", f"FVG too small ({fvg_size:.1f} < {nc.MIN_FVG_SIZE})",
                                        timestamp=idx_m15, h1_idx=h1_idx, bias=h1_bias, fvg_size=fvg_size, min_required=nc.MIN_FVG_SIZE)
                            self._log(f"[NAS] Rejected: FVG too small ({fvg_size:.1f})")
                            displacement_seen = False
                    else:
                        self._reject("displacement_fvg", "displacement did not create FVG (no fvg_bull/fvg_bear)",
                                    timestamp=idx_m15, h1_idx=h1_idx, bias=h1_bias)
                        self._log(f"[NAS] Rejected: displacement did not create FVG")
                        displacement_seen = False
                    continue

                if fvg_zone is None:
                    continue

                if not return_to_fvg:
                    top, bottom = fvg_zone["top"], fvg_zone["bottom"]
                    if h1_bias == "BULLISH":
                        if row_m15["low"] <= top and row_m15["high"] >= bottom:
                            return_to_fvg = True
                    else:
                        if row_m15["high"] >= bottom and row_m15["low"] <= top:
                            return_to_fvg = True
                    if not return_to_fvg:
                        continue

                conf = confirm_entry_candle(row_m15, h1_bias, fvg_zone)
                if not conf["confirmed"]:
                    self._reject("entry_candle", conf.get("reason", "entry not confirmed"),
                                timestamp=idx_m15, h1_idx=h1_idx, bias=h1_bias)
                    continue

                buf = nc.SL_BUFFER
                if h1_bias == "BULLISH":
                    sl = sweep_low - buf
                    entry = row_m15["close"]
                    if sl >= entry:
                        self._reject("invalid_sl", "invalid SL (BUY): sl >= entry",
                                    timestamp=idx_m15, h1_idx=h1_idx, bias=h1_bias, sl=sl, entry=entry)
                        self._log(f"[NAS] Rejected: invalid SL (BUY)")
                        continue
                    sl_dist = entry - sl
                    tp = entry + sl_dist
                    signals.append({
                        "time": idx_m15,
                        "type": "BUY",
                        "price": entry,
                        "sl": sl,
                        "tp": tp,
                        "reason": "NAS: H1 bias + sweep + displacement FVG + return + confirm",
                    })
                else:
                    sl = sweep_high + buf
                    entry = row_m15["close"]
                    if sl <= entry:
                        self._reject("invalid_sl", "invalid SL (SELL): sl <= entry",
                                    timestamp=idx_m15, h1_idx=h1_idx, bias=h1_bias, sl=sl, entry=entry)
                        self._log(f"[NAS] Rejected: invalid SL (SELL)")
                        continue
                    sl_dist = sl - entry
                    tp = entry - sl_dist
                    signals.append({
                        "time": idx_m15,
                        "type": "SELL",
                        "price": entry,
                        "sl": sl,
                        "tp": tp,
                        "reason": "NAS: H1 bias + sweep + displacement FVG + return + confirm",
                    })
                self._log(f"[NAS] Signal: {signals[-1]['type']} @ {entry}")
                break

        return pd.DataFrame(signals)
