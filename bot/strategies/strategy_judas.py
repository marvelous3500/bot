"""
NAS Judas Strategy: institutional Judas Swing manipulation setups on NAS100.
Trade ONLY after liquidity trap + displacement + confirmation.
Never trade sweeps directly.
"""
import logging
import pandas as pd
import numpy as np
from typing import Optional, Dict, Any

from .. import judas_config as jc
from ..indicators import detect_fvg, detect_displacement
from ..indicators_bos import detect_swing_highs_lows, detect_break_of_structure
from ..indicators_nas import detect_liquidity_sweep_m15
from ..indicators_judas import detect_structure_shift_after_sweep

logger = logging.getLogger("judas")


def _setup_judas_logging(verbose: bool = False):
    """Configure judas logger. Call when JUDAS_VERBOSE or verbose=True."""
    if verbose and not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("[%(name)s] %(levelname)s: %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)


def _parse_kz(kz_tuple) -> tuple:
    """Parse ('08:00','10:00') to (start_min, end_min) in minutes from midnight."""
    if not kz_tuple or len(kz_tuple) < 2:
        return None, None
    try:
        h1, m1 = map(int, str(kz_tuple[0]).split(":"))
        h2, m2 = map(int, str(kz_tuple[1]).split(":"))
        return h1 * 60 + m1, h2 * 60 + m2
    except (ValueError, AttributeError):
        return None, None


def detect_session(timestamp, cfg=None) -> Dict[str, Any]:
    """
    Check if timestamp is within London or NY kill zone.
    Returns {passed: bool, session: str, reasoning: str}.
    """
    cfg = cfg or jc
    ts = pd.Timestamp(timestamp) if not hasattr(timestamp, "hour") else timestamp
    hour = ts.hour
    minute = getattr(ts, "minute", 0)
    total_min = hour * 60 + minute

    london = _parse_kz(getattr(cfg, "LONDON_KZ", ("03:00", "05:00")))
    ny = _parse_kz(getattr(cfg, "NY_KZ", ("09:30", "11:30")))

    if getattr(cfg, "ENABLE_LONDON", True) and london[0] is not None and london[1] is not None:
        if london[0] <= total_min < london[1]:
            return {
                "passed": True,
                "session": "london",
                "reasoning": f"within London kill zone ({cfg.LONDON_KZ})",
            }

    if getattr(cfg, "ENABLE_NEWYORK", True) and ny[0] is not None and ny[1] is not None:
        if ny[0] <= total_min < ny[1]:
            return {
                "passed": True,
                "session": "newyork",
                "reasoning": f"within NY kill zone ({cfg.NY_KZ})",
            }

    return {
        "passed": False,
        "session": "none",
        "reasoning": "outside allowed kill zones",
    }


def detect_judas_move(
    df: pd.DataFrame, idx: int, direction: str, cfg=None
) -> Dict[str, Any]:
    """
    Identify Judas swing (fake move setup). A Judas move is a liquidity sweep:
    wick beyond swing high/low then close back inside.
    Returns {detected: bool, level: float, reasoning: str}.
    """
    cfg = cfg or jc
    if df is None or df.empty or idx < 0 or idx >= len(df):
        return {"detected": False, "level": None, "reasoning": "invalid df or idx"}

    row = df.iloc[idx]
    lookback = getattr(cfg, "LIQ_SWEEP_LOOKBACK", 5)

    if "sweep_high" not in df.columns:
        df = detect_swing_highs_lows(df, swing_length=getattr(cfg, "SWING_LENGTH", 3))
        df = detect_liquidity_sweep_m15(df, lookback=lookback)

    if direction == "BULLISH":
        if row.get("sweep_low"):
            level = row.get("sweep_low_price", row["high"])
            return {
                "detected": True,
                "level": float(level),
                "reasoning": "Judas move: sweep of lows (liquidity trap)",
            }
    else:
        if row.get("sweep_high"):
            level = row.get("sweep_high_price", row["low"])
            return {
                "detected": True,
                "level": float(level),
                "reasoning": "Judas move: sweep of highs (liquidity trap)",
            }

    return {
        "detected": False,
        "level": None,
        "reasoning": f"no {direction.lower()} Judas sweep at bar {idx}",
    }


def detect_sweep(
    df: pd.DataFrame, idx: int, direction: str, cfg=None
) -> Dict[str, Any]:
    """
    Detect liquidity sweep: wick beyond swing high/low, close back inside.
    Returns {swept: bool, level: float, size: float, reasoning: str}.
    """
    cfg = cfg or jc
    min_sweep = getattr(cfg, "MIN_SWEEP_POINTS", 35)

    judas = detect_judas_move(df, idx, direction, cfg)
    if not judas["detected"]:
        return {
            "swept": False,
            "level": None,
            "size": 0.0,
            "reasoning": judas["reasoning"],
        }

    row = df.iloc[idx]
    if direction == "BULLISH":
        size = row.get("sweep_low_size", 0)
        level = row.get("sweep_low_price")
    else:
        size = row.get("sweep_high_size", 0)
        level = row.get("sweep_high_price")

    if size < min_sweep:
        return {
            "swept": False,
            "level": level,
            "size": float(size),
            "reasoning": f"sweep size {size:.1f} < min {min_sweep}",
        }

    return {
        "swept": True,
        "level": float(level) if level is not None else None,
        "size": float(size),
        "reasoning": f"valid sweep: {size:.1f} pts",
    }


def detect_displacement_candle(
    df: pd.DataFrame, idx: int, direction: str, cfg=None
) -> Dict[str, Any]:
    """
    Detect displacement: candle body >= multiplier x average of last N candles.
    Returns {detected: bool, ratio: float, reasoning: str}.
    """
    cfg = cfg or jc
    if df is None or df.empty or idx < 0 or idx >= len(df):
        return {"detected": False, "ratio": 0.0, "reasoning": "invalid df or idx"}

    ratio_req = getattr(cfg, "MIN_DISPLACEMENT_RATIO", 1.8)
    window = 10

    if "displacement_bull" not in df.columns:
        df = detect_displacement(df, threshold=ratio_req, window=window)

    row = df.iloc[idx]
    if direction == "BULLISH" and row.get("displacement_bull"):
        body = abs(row["close"] - row["open"])
        avg = row.get("avg_body", body / ratio_req)
        ratio = body / avg if avg and avg > 0 else 0
        return {
            "detected": True,
            "ratio": float(ratio),
            "reasoning": f"displacement bull: body {ratio:.2f}x avg",
        }
    if direction == "BEARISH" and row.get("displacement_bear"):
        body = abs(row["close"] - row["open"])
        avg = row.get("avg_body", body / ratio_req)
        ratio = body / avg if avg and avg > 0 else 0
        return {
            "detected": True,
            "ratio": float(ratio),
            "reasoning": f"displacement bear: body {ratio:.2f}x avg",
        }

    return {
        "detected": False,
        "ratio": 0.0,
        "reasoning": f"no displacement at bar {idx}",
    }


def detect_structure_shift(
    df: pd.DataFrame, idx: int, direction: str, sweep_idx: int, cfg=None
) -> Dict[str, Any]:
    """
    Confirm structure shift: break of recent swing after sweep.
    Returns {shifted: bool, swing_level: float, reasoning: str}.
    """
    cfg = cfg or jc
    return detect_structure_shift_after_sweep(
        df, sweep_idx, idx, direction,
        swing_length=getattr(cfg, "SWING_LENGTH", 3),
    )


def detect_fvg_at_bar(
    df: pd.DataFrame, idx: int, direction: str, cfg=None
) -> Dict[str, Any]:
    """
    Detect FVG (three-candle imbalance gap) at bar idx.
    Returns {found: bool, top: float, bottom: float, size: float, reasoning: str}.
    """
    cfg = cfg or jc
    if df is None or df.empty or idx < 2:
        return {"found": False, "top": None, "bottom": None, "size": 0.0, "reasoning": "insufficient bars"}

    if "fvg_bull" not in df.columns:
        df = detect_fvg(df)

    min_size = getattr(cfg, "MIN_FVG_SIZE", 18)
    row = df.iloc[idx]

    if direction == "BULLISH" and row.get("fvg_bull"):
        c1_high = df.iloc[idx - 2]["high"]
        top = row["low"]
        bottom = c1_high
        size = top - bottom
        if size >= min_size:
            return {
                "found": True,
                "top": float(top),
                "bottom": float(bottom),
                "size": float(size),
                "reasoning": f"bull FVG size {size:.1f}",
            }
        return {"found": False, "top": top, "bottom": bottom, "size": size, "reasoning": f"FVG too small: {size:.1f}"}

    if direction == "BEARISH" and row.get("fvg_bear"):
        c1_low = df.iloc[idx - 2]["low"]
        top = row["high"]
        bottom = c1_low
        size = top - bottom
        if size >= min_size:
            return {
                "found": True,
                "top": float(top),
                "bottom": float(bottom),
                "size": float(size),
                "reasoning": f"bear FVG size {size:.1f}",
            }
        return {"found": False, "top": top, "bottom": bottom, "size": size, "reasoning": f"FVG too small: {size:.1f}"}

    return {"found": False, "top": None, "bottom": None, "size": 0.0, "reasoning": "no FVG"}


def confirm_entry(
    row: pd.Series, fvg_zone: Dict, bias: str, cfg=None
) -> Dict[str, Any]:
    """
    Confirm entry candle: close in FVG, body significant.
    Returns {confirmed: bool, reasoning: str}.
    """
    cfg = cfg or jc
    if fvg_zone is None:
        return {"confirmed": False, "reasoning": "no FVG zone"}

    top = fvg_zone.get("top")
    bottom = fvg_zone.get("bottom")
    if top is None or bottom is None:
        return {"confirmed": False, "reasoning": "invalid FVG zone"}

    close = row["close"]
    if bias == "BULLISH":
        if close <= row["open"]:
            return {"confirmed": False, "reasoning": "bearish candle"}
        if not (bottom <= close <= top):
            return {"confirmed": False, "reasoning": "close not in FVG"}
        body = close - row["open"]
    else:
        if close >= row["open"]:
            return {"confirmed": False, "reasoning": "bullish candle"}
        if not (bottom <= close <= top):
            return {"confirmed": False, "reasoning": "close not in FVG"}
        body = row["open"] - close

    rng = row["high"] - row["low"]
    if rng > 0 and body / rng < 0.3:
        return {"confirmed": False, "reasoning": "body too small"}

    return {"confirmed": True, "reasoning": "entry confirmed"}


def execute_trade(signal: Dict, cfg=None) -> Dict[str, Any]:
    """
    Execute trade. In backtest mode, returns signal for simulation.
    Returns {executed: bool, order_id: str, reasoning: str}.
    """
    cfg = cfg or jc
    if not signal:
        return {"executed": False, "order_id": None, "reasoning": "no signal"}
    return {
        "executed": True,
        "order_id": f"judas_{signal.get('time', '')}",
        "reasoning": "signal emitted for execution",
    }


def manage_trade(position: Dict, cfg=None) -> Dict[str, Any]:
    """
    Manage trade: TP ladder, SL. Returns {action: str, sl: float, tp: float, reasoning: str}.
    """
    cfg = cfg or jc
    sl = position.get("sl")
    tp = position.get("tp")
    tp_model = getattr(cfg, "TP_MODEL", "ladder")
    if tp_model == "ladder" and sl and position.get("price"):
        entry = position["price"]
        sl_dist = abs(entry - sl)
        tp1 = entry + sl_dist if position.get("type") == "BUY" else entry - sl_dist
        return {
            "action": "hold",
            "sl": sl,
            "tp": tp or tp1,
            "reasoning": f"TP ladder: TP1 at 1R",
        }
    return {"action": "hold", "sl": sl, "tp": tp, "reasoning": "standard TP"}


def _validate_confirmation_chain(steps: Dict) -> tuple:
    """If any step failed, reject trade. Returns (ok: bool, reason: str)."""
    required = ["session", "sweep", "sweep_size", "displacement", "structure_shift", "fvg", "retrace", "entry"]
    for k in required:
        if not steps.get(k, False):
            return False, f"Confirmation chain incomplete: {k} failed"
    return True, "ok"


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


class JudasStrategy:
    """
    NAS Judas Strategy: trade only after liquidity trap + displacement + confirmation.
    Never trade sweeps directly. Strict 10-step entry sequence.
    """

    def __init__(
        self,
        df_h1: pd.DataFrame,
        df_m15: pd.DataFrame,
        symbol: Optional[str] = None,
        verbose: bool = False,
    ):
        self.df_h1 = df_h1.copy() if df_h1 is not None else None
        self.df_m15 = df_m15.copy() if df_m15 is not None else None
        self.symbol = symbol
        self.verbose = verbose or getattr(jc, "VERBOSE", False)
        _setup_judas_logging(self.verbose)

    def _log(self, msg: str, level: str = "debug"):
        if self.verbose:
            print(f"[JUDAS] {msg}")
        if level == "info":
            logger.info(msg)
        elif level == "warning":
            logger.warning(msg)
        else:
            logger.debug(msg)

    def prepare_data(self):
        """Run indicators on H1 and M15."""
        cfg = jc
        for name, df in [("H1", self.df_h1), ("M15", self.df_m15)]:
            if df is None or df.empty:
                continue
            self._log(f"Preparing {name}...")
            df = detect_swing_highs_lows(df, swing_length=cfg.SWING_LENGTH)
            df = detect_break_of_structure(df)
            df = detect_fvg(df)
            df = detect_displacement(df, threshold=cfg.MIN_DISPLACEMENT_RATIO, window=10)
            df = detect_liquidity_sweep_m15(df, lookback=cfg.LIQ_SWEEP_LOOKBACK)
            if name == "H1":
                self.df_h1 = df
            else:
                self.df_m15 = df
        return self.df_h1, self.df_m15

    def run_backtest(self) -> pd.DataFrame:
        """Run backtest with strict 10-step entry sequence."""
        if self.df_h1 is None or self.df_h1.empty or self.df_m15 is None or self.df_m15.empty:
            return pd.DataFrame()

        cfg = jc
        signals = []
        atr_series = _atr(self.df_m15, 14)
        window_hours = cfg.ENTRY_WINDOW_HOURS

        for i_h1 in range(len(self.df_h1)):
            h1_idx = self.df_h1.index[i_h1]
            h1_row = self.df_h1.iloc[i_h1]
            if not h1_row.get("bos_bull") and not h1_row.get("bos_bear"):
                continue
            bias = "BULLISH" if h1_row.get("bos_bull") else "BEARISH"

            future_m15 = self.df_m15[self.df_m15.index > h1_idx]
            next_h1 = h1_idx + pd.Timedelta(hours=window_hours)
            m15_window = future_m15[future_m15.index < next_h1]

            sweep_seen = False
            sweep_idx = None
            sweep_high = None
            sweep_low = None
            displacement_seen = False
            structure_shift_seen = False
            fvg_zone = None
            retrace_seen = False

            for j, (idx_m15, row_m15) in enumerate(m15_window.iterrows()):
                current_time = idx_m15 if hasattr(idx_m15, "hour") else pd.Timestamp(idx_m15)
                try:
                    loc = self.df_m15.index.get_loc(idx_m15)
                    i_m15 = int(loc) if isinstance(loc, (int, np.integer)) else (loc.start if hasattr(loc, "start") else 0)
                except (KeyError, TypeError, ValueError):
                    i_m15 = j

                sess = detect_session(current_time, cfg)
                if not sess["passed"]:
                    continue

                if not sweep_seen:
                    sweep_res = detect_sweep(self.df_m15, i_m15, bias, cfg)
                    if sweep_res["swept"]:
                        sweep_seen = True
                        sweep_idx = i_m15
                        sweep_high = row_m15["high"]
                        sweep_low = row_m15["low"]
                    continue

                if not displacement_seen:
                    disp_res = detect_displacement_candle(self.df_m15, i_m15, bias, cfg)
                    if not disp_res["detected"]:
                        continue
                    displacement_seen = True

                    fvg_res = detect_fvg_at_bar(self.df_m15, i_m15, bias, cfg)
                    if not fvg_res["found"]:
                        displacement_seen = False
                        continue
                    fvg_zone = {"top": fvg_res["top"], "bottom": fvg_res["bottom"], "size": fvg_res["size"]}

                    shift_res = detect_structure_shift(self.df_m15, i_m15, bias, sweep_idx, cfg)
                    if not shift_res["shifted"]:
                        displacement_seen = False
                        fvg_zone = None
                        continue
                    structure_shift_seen = True
                    continue

                if fvg_zone is None:
                    continue

                if not retrace_seen:
                    top, bottom = fvg_zone["top"], fvg_zone["bottom"]
                    if bias == "BULLISH":
                        if row_m15["low"] <= top and row_m15["high"] >= bottom:
                            retrace_seen = True
                    else:
                        if row_m15["high"] >= bottom and row_m15["low"] <= top:
                            retrace_seen = True
                    if not retrace_seen:
                        continue

                conf = confirm_entry(row_m15, fvg_zone, bias, cfg)
                if not conf["confirmed"]:
                    continue

                steps = {
                    "session": True,
                    "sweep": True,
                    "sweep_size": True,
                    "displacement": True,
                    "structure_shift": structure_shift_seen,
                    "fvg": True,
                    "retrace": retrace_seen,
                    "entry": True,
                }
                ok, reason = _validate_confirmation_chain(steps)
                if not ok:
                    self._log(f"Rejected: {reason}", "warning")
                    continue

                buf = cfg.SL_BUFFER
                if bias == "BULLISH":
                    sl = sweep_low - buf
                    entry = row_m15["close"]
                    if sl >= entry:
                        self._log("Rejected: invalid SL (BUY)")
                        continue
                    sl_dist = entry - sl
                    tp = entry + sl_dist
                    sig = {
                        "time": idx_m15,
                        "type": "BUY",
                        "price": entry,
                        "sl": sl,
                        "tp": tp,
                        "reason": "JUDAS: liquidity trap + displacement + structure shift + FVG retrace",
                    }
                else:
                    sl = sweep_high + buf
                    entry = row_m15["close"]
                    if sl <= entry:
                        self._log("Rejected: invalid SL (SELL)")
                        continue
                    sl_dist = sl - entry
                    tp = entry - sl_dist
                    sig = {
                        "time": idx_m15,
                        "type": "SELL",
                        "price": entry,
                        "sl": sl,
                        "tp": tp,
                        "reason": "JUDAS: liquidity trap + displacement + structure shift + FVG retrace",
                    }

                signals.append(sig)
                self._log(f"Signal: {sig['type']} @ {entry}", "info")
                break

        return pd.DataFrame(signals)
