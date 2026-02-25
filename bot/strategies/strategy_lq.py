"""
LQStrategy: liquidity sweep strategy (PDH/PDL + session LQ, internal/external).
Uses 15-minute bars for setup. Entry: next bar open, or Vester 1M trigger when LQ_USE_VESTER_ENTRY.
"""
import pandas as pd
import numpy as np
from typing import Optional, Dict, Tuple, Any

import config
from .base import BaseStrategy
from ..indicators import calculate_pdl_pdh, detect_rejection_candle
from ..indicators_bos import detect_swing_highs_lows, detect_break_of_structure
from ..indicators_lq import (
    get_session_high_low,
    get_session_for_hour,
    detect_external_sweep,
    detect_internal_sweep,
)


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


class LQStrategy(BaseStrategy):
    """
    Liquidity sweep: PDH/PDL (external), session high/low (session LQ),
    swing high/low (internal). Entry on 15M after sweep + confirmation.
    """

    def __init__(
        self,
        df_daily: pd.DataFrame,
        df_m15: pd.DataFrame,
        df_m1: Optional[pd.DataFrame] = None,
        symbol: Optional[str] = None,
        session_hours: Optional[Dict[str, Tuple[int, int]]] = None,
        swing_lookback: int = 10,
        verbose: bool = False,
    ):
        self.df_daily = df_daily
        self.df_m15 = df_m15.copy() if df_m15 is not None else None
        self.df_m1 = df_m1.copy() if df_m1 is not None else None
        self.symbol = symbol
        self.session_hours = session_hours or getattr(
            config, 'LQ_SESSION_HOURS_UTC',
            {'asian': (0, 5), 'london': (7, 11), 'ny': (13, 17)}
        )
        self.swing_lookback = swing_lookback or getattr(config, 'LQ_SWING_LOOKBACK', 10)
        self.verbose = verbose
        self.allow_sessions = getattr(config, 'LQ_ALLOW_SESSIONS', ['london', 'ny'])
        self.allow_pdh_pdl = getattr(config, 'LQ_ALLOW_PDH_PDL', True)
        self.allow_session_sweeps = getattr(config, 'LQ_ALLOW_SESSION_SWEEPS', True)
        self.rejection_wick_ratio = getattr(config, 'LQ_REJECTION_WICK_RATIO', 0.55)
        self.require_bos = getattr(config, 'LQ_REQUIRE_BOS', False)
        self.confirm_bars = getattr(config, 'LQ_CONFIRM_BARS', 2)
        self.use_vester_entry = getattr(config, 'LQ_USE_VESTER_ENTRY', False)
        self.vester_entry_bars = getattr(config, 'LQ_VESTER_ENTRY_BARS', 15)

    def prepare_data(self) -> pd.DataFrame:
        """Add PDH/PDL, session H/L, swings, internal/external sweep, rejection, BOS."""
        if self.df_m15 is None or self.df_m15.empty:
            return self.df_m15
        df = self.df_m15
        if self.df_daily is not None and not self.df_daily.empty:
            df = df.copy()
            df.index = pd.to_datetime(df.index)
            pdh_list = []
            pdl_list = []
            sess_high_list = []
            sess_low_list = []
            for i in range(len(df)):
                t = df.index[i]
                pdh, pdl = calculate_pdl_pdh(self.df_daily, t)
                pdh_list.append(pdh)
                pdl_list.append(pdl)
                sess = get_session_for_hour(t.hour, self.session_hours)
                if sess:
                    sh, sl = get_session_high_low(df, t, sess, self.session_hours)
                    sess_high_list.append(sh)
                    sess_low_list.append(sl)
                else:
                    sess_high_list.append(None)
                    sess_low_list.append(None)
            df['pdh'] = pdh_list
            df['pdl'] = pdl_list
            df['session_high'] = sess_high_list
            df['session_low'] = sess_low_list
        detect_swing_highs_lows(df, swing_length=3)
        detect_break_of_structure(df)
        detect_internal_sweep(df, lookback=self.swing_lookback)
        detect_rejection_candle(df, wick_ratio=self.rejection_wick_ratio)
        df['sweep_pdh'] = False
        df['sweep_pdl'] = False
        df['sweep_session_high'] = False
        df['sweep_session_low'] = False
        df['sweep_type'] = None
        df['sweep_direction'] = None
        for i in range(len(df)):
            row = df.iloc[i]
            res = detect_external_sweep(
                row['open'], row['high'], row['low'], row['close'],
                row.get('pdh'), row.get('pdl'),
                row.get('session_high'), row.get('session_low'),
            )
            df.iloc[i, df.columns.get_loc('sweep_pdh')] = res['sweep_pdh']
            df.iloc[i, df.columns.get_loc('sweep_pdl')] = res['sweep_pdl']
            df.iloc[i, df.columns.get_loc('sweep_session_high')] = res['sweep_session_high']
            df.iloc[i, df.columns.get_loc('sweep_session_low')] = res['sweep_session_low']
            df.iloc[i, df.columns.get_loc('sweep_type')] = res['sweep_type']
            df.iloc[i, df.columns.get_loc('sweep_direction')] = res['direction']
        self.df_m15 = df
        return df

    def run_backtest(self) -> pd.DataFrame:
        """
        Emit signals on external sweep + confirmation (rejection or BOS).
        One trade per level per day (PDH/PDL) or per session (session H/L).
        Entry at next bar open; SL beyond swept level + buffer; TP from RR.
        """
        df = self.df_m15
        if df is None or df.empty or len(df) < self.swing_lookback + 5:
            return pd.DataFrame()
        rr = getattr(config, 'LQ_MIN_RR', 2.0)
        one_per_level = getattr(config, 'LQ_ONE_TRADE_PER_LEVEL', True)
        signals = []
        traded_pdh = {}
        vest = None
        df_m1_prep = None
        if self.use_vester_entry and self.df_m1 is not None and not self.df_m1.empty:
            from .strategy_vester import VesterStrategy
            vest = VesterStrategy(df_h1=df, df_m5=df, df_m1=self.df_m1.copy(), symbol=self.symbol, verbose=False)
            vest.prepare_data()
            df_m1_prep = vest.df_m1
        traded_pdl = {}
        traded_sess_high = {}
        traded_sess_low = {}
        for i in range(self.swing_lookback, len(df) - 3):
            row = df.iloc[i]
            t = df.index[i]
            bar_date = t.normalize() if hasattr(t, 'normalize') else pd.Timestamp(t).normalize()
            sess = get_session_for_hour(t.hour, self.session_hours)
            sess_key = f"{bar_date}_{sess}" if sess else None
            sweep_type = row.get('sweep_type')
            direction = row.get('sweep_direction')
            if not sweep_type or not direction:
                continue
            if sweep_type in ('pdh', 'pdl') and not self.allow_pdh_pdl:
                continue
            if sweep_type in ('session_high', 'session_low') and not self.allow_session_sweeps:
                continue
            if self.allow_sessions and sess not in self.allow_sessions:
                continue
            if one_per_level:
                if sweep_type == 'pdh' and traded_pdh.get(bar_date):
                    continue
                if sweep_type == 'pdl' and traded_pdl.get(bar_date):
                    continue
                if sweep_type == 'session_high' and sess_key and traded_sess_high.get(sess_key):
                    continue
                if sweep_type == 'session_low' and sess_key and traded_sess_low.get(sess_key):
                    continue
            confirmed = False
            conf_bar_idx = None
            max_j = min(self.confirm_bars, 3)
            for j in range(1, max_j + 1):
                if i + j >= len(df):
                    break
                nxt = df.iloc[i + j]
                if direction == 'bearish':
                    has_bos = bool(nxt.get('bos_bear'))
                    has_rej = bool(nxt.get('rejection_bear'))
                    ok = has_bos or (has_rej and not self.require_bos)
                    if ok:
                        confirmed = True
                        conf_bar_idx = i + j
                        break
                else:
                    has_bos = bool(nxt.get('bos_bull'))
                    has_rej = bool(nxt.get('rejection_bull'))
                    ok = has_bos or (has_rej and not self.require_bos)
                    if ok:
                        confirmed = True
                        conf_bar_idx = i + j
                        break
            if not confirmed or conf_bar_idx is None:
                continue
            entry_bar_idx = conf_bar_idx + 1
            if entry_bar_idx >= len(df):
                continue
            swept_level = None
            if sweep_type == 'pdh':
                swept_level = float(row['high'])
            elif sweep_type == 'pdl':
                swept_level = float(row['low'])
            elif sweep_type == 'session_high':
                swept_level = float(row['high'])
            elif sweep_type == 'session_low':
                swept_level = float(row['low'])
            if swept_level is None:
                continue

            entry_time = df.index[entry_bar_idx]
            entry_price = None
            vester_reason = None

            if vest is not None and df_m1_prep is not None and not df_m1_prep.empty:
                from .. import vester_config as vc
                atr_m15 = _atr(df, 14)
                atr_val = atr_m15.iloc[entry_bar_idx - 1] if entry_bar_idx > 0 and entry_bar_idx - 1 < len(atr_m15) else np.nan
                atr_val = float(atr_val) if not pd.isna(atr_val) and atr_val > 0 else (row['high'] - row['low']) * 2
                half = atr_val * getattr(vc, 'LIQ_ZONE_ATR_MULT', 0.5)
                zone_top = swept_level + half
                zone_bottom = swept_level - half
                vester_dir = 'BUY' if direction == 'bullish' else 'SELL'
                m1_after = df_m1_prep.index >= entry_time
                if m1_after.any():
                    start_idx = df_m1_prep.index.get_indexer([df_m1_prep.index[m1_after][0]], method='nearest')[0]
                    for k in range(start_idx, min(start_idx + self.vester_entry_bars, len(df_m1_prep))):
                        df_slice = df_m1_prep.iloc[: k + 1]
                        triggered, ep, reason = vest.checkEntryTrigger(
                            df_slice, vester_dir, zone_top, zone_bottom, k
                        )
                        if triggered and ep is not None:
                            entry_price = ep
                            entry_time = df_m1_prep.index[k]
                            vester_reason = reason
                            break

            if entry_price is None:
                if self.use_vester_entry and self.df_m1 is not None:
                    continue
                entry_row = df.iloc[entry_bar_idx]
                entry_price = float(entry_row['open'])
                entry_time = df.index[entry_bar_idx]

            buf_pct = getattr(config, 'LQ_SL_BUFFER_PCT', 0.02)
            buf_min = getattr(config, 'LQ_SL_BUFFER_MIN', 0.5)
            buffer = max(abs(entry_price - swept_level) * buf_pct, buf_min)
            if direction == 'bearish':
                sl = swept_level + buffer
                sl_dist = sl - entry_price
                tp = entry_price - sl_dist * rr
                sig_type = 'SELL'
            else:
                sl = swept_level - buffer
                sl_dist = entry_price - sl
                tp = entry_price + sl_dist * rr
                sig_type = 'BUY'
            reason_str = f"LQ {sweep_type} sweep {direction}"
            if vester_reason:
                reason_str += f" + {vester_reason}"
            sig = {
                'time': entry_time,
                'type': sig_type,
                'price': entry_price,
                'sl': sl,
                'tp': tp,
                'reason': reason_str,
                'setup_m15': entry_time,
            }
            signals.append(sig)
            if one_per_level:
                if sweep_type == 'pdh':
                    traded_pdh[bar_date] = True
                elif sweep_type == 'pdl':
                    traded_pdl[bar_date] = True
                elif sweep_type == 'session_high' and sess_key:
                    traded_sess_high[sess_key] = True
                elif sweep_type == 'session_low' and sess_key:
                    traded_sess_low[sess_key] = True
        return pd.DataFrame(signals)
