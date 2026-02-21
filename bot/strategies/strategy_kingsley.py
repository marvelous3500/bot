"""
Kingsley Gold Strategy: H1 trend + entry-TF (5m/15m) BOS/ChoCH + zone→LQ + liquidity sweep + OB test.
Rules: 1) 1H trend, 2) Entry-TF BOS/ChoCH, 3) Shallow tap → zone=LQ → sweep high/low,
4) Price returns, sweeps LQ, tests OB, 5) Entry, target high/low.
Entry TF from KINGSLEY_ENTRY_TIMEFRAME (default 5m). Gold only (XAUUSD/GC=F).
When USE_EXTRA_FILTERS=True, uses same filters as Marvellous (MARVELLOUS_* config).
"""
import pandas as pd
import numpy as np

import config
from .. import marvellous_config as mc
from ..indicators_bos import (
    detect_swing_highs_lows,
    detect_break_of_structure,
    identify_order_block,
    detect_shallow_tap,
    higher_tf_bias_aligned,
)
from .strategy_marvellous import (
    calculate_h1_bias_with_zone_validation,
    is_session_allowed,
    is_liquidity_map_valid,
    _atr,
)
from ..news_filter import is_news_safe


class KingsleyGoldStrategy:
    """ICT-style: 4H + H1 trend + entry-TF (5m/15m) BOS/ChoCH + zone→LQ + sweep + OB test + entry."""

    def __init__(self, df_4h, df_h1, df_15m, df_daily=None, verbose=True):
        self.df_4h = df_4h.copy()
        self.df_h1 = df_h1.copy()
        self.df_15m = df_15m.copy()
        self.df_daily = df_daily.copy() if df_daily is not None and not df_daily.empty else None
        self.verbose = verbose

    def _log(self, msg):
        if self.verbose:
            print(msg)

    def prepare_data(self):
        if getattr(config, 'KINGSLEY_AGGRESSIVE', False):
            swing_len = 2
        else:
            swing_len = getattr(config, 'KINGSLEY_SWING_LENGTH', 3)
        self._log("Detecting swing highs/lows on 4H...")
        self.df_4h = detect_swing_highs_lows(self.df_4h, swing_length=swing_len)
        self._log("Detecting Break of Structure on 4H...")
        self.df_4h = detect_break_of_structure(self.df_4h)
        if self.df_daily is not None:
            self._log("Detecting swing highs/lows on Daily...")
            self.df_daily = detect_swing_highs_lows(self.df_daily, swing_length=swing_len)
            self._log("Detecting Break of Structure on Daily...")
            self.df_daily = detect_break_of_structure(self.df_daily)
        self._log("Detecting swing highs/lows on H1...")
        self.df_h1 = detect_swing_highs_lows(self.df_h1, swing_length=swing_len)
        self._log("Detecting Break of Structure on H1...")
        self.df_h1 = detect_break_of_structure(self.df_h1)
        self._log("Detecting swing highs/lows on entry TF...")
        self.df_15m = detect_swing_highs_lows(self.df_15m, swing_length=swing_len)
        self._log("Detecting Break of Structure on entry TF...")
        self.df_15m = detect_break_of_structure(self.df_15m)
        if getattr(config, 'KINGSLEY_USE_EMA_FILTER', False):
            from ..indicators import calculate_ema
            self.df_4h = calculate_ema(self.df_4h, period=config.EMA_PERIOD)
            self.df_h1 = calculate_ema(self.df_h1, period=config.EMA_PERIOD)
            self.df_15m = calculate_ema(self.df_15m, period=config.EMA_PERIOD)
        return self.df_4h, self.df_h1, self.df_15m

    def run_backtest(self):
        if self.df_4h.empty or self.df_h1.empty or self.df_15m.empty:
            return pd.DataFrame()
        signals = []
        use_kill_zone = getattr(config, 'KINGSLEY_USE_KILL_ZONES', True)
        use_asian = getattr(config, 'KINGSLEY_USE_ASIAN_SESSION', False)
        asian_hours = getattr(config, 'KINGSLEY_ASIAN_SESSION_HOURS', [0, 1, 2, 3, 4])
        allowed_hours = list(config.KILL_ZONE_HOURS) + (list(asian_hours) if use_asian else [])
        allowed_hours = sorted(set(allowed_hours))
        use_ema = getattr(config, 'KINGSLEY_USE_EMA_FILTER', False)
        window_hours = getattr(config, 'KINGSLEY_15M_WINDOW_HOURS', 8)
        if getattr(config, 'KINGSLEY_AGGRESSIVE', False):
            disp_ratio = 0.5
        else:
            disp_ratio = getattr(config, 'KINGSLEY_DISPLACEMENT_RATIO', 0.6)
        use_4h_filter = getattr(config, 'USE_4H_BIAS_FILTER', False)
        use_daily_filter = getattr(config, 'USE_DAILY_BIAS_FILTER', False)
        use_h1_zone = getattr(config, 'KINGSLEY_REQUIRE_H1_ZONE_CONFIRMATION', True)
        rt = mc.REACTION_THRESHOLDS
        h1_wick_pct = rt.get("wick_pct", 0.5)
        h1_body_pct = rt.get("body_pct", 0.3)
        liq_lookback = getattr(config, 'KINGSLEY_LIQ_SWEEP_LOOKBACK', 5)
        tp_lookahead = getattr(config, 'KINGSLEY_TP_SWING_LOOKAHEAD', 3)
        ob_lookback = getattr(config, 'KINGSLEY_OB_LOOKBACK', 20)
        use_extra_filters = getattr(config, 'USE_EXTRA_FILTERS', True)
        # When True, use Marvellous config (mc) for session, news, ATR, spread, liquidity — one config for both strategies
        atr_series = _atr(self.df_15m, 14) if use_extra_filters else None

        for i_h1 in range(len(self.df_h1)):
            h1_idx = self.df_h1.index[i_h1]
            h1_row = self.df_h1.iloc[i_h1]
            if not h1_row['bos_bull'] and not h1_row['bos_bear']:
                continue
            h1_bias = 'BULLISH' if h1_row['bos_bull'] else 'BEARISH'

            # Extra filters: news (skip H1 bar if not safe) — uses MARVELLOUS_* config
            if use_extra_filters:
                if not is_news_safe(
                    h1_idx,
                    buffer_before_minutes=mc.NEWS_BUFFER_BEFORE_MINUTES,
                    buffer_after_minutes=mc.NEWS_BUFFER_AFTER_MINUTES,
                    avoid_news=mc.AVOID_NEWS,
                    countries=mc.MARVELLOUS_NEWS_COUNTRIES,
                    api=mc.MARVELLOUS_NEWS_API,
                    api_key=mc.FCSAPI_KEY,
                ):
                    continue

            # Generic Daily filter: require Daily bias to match H1
            if use_daily_filter and not higher_tf_bias_aligned(self.df_daily, h1_idx, h1_bias):
                continue
            if use_daily_filter and self.df_daily is not None:
                self._log(f"[Daily+H1] {h1_bias} bias aligned at {h1_idx}")
            
            # Generic 4H filter: require 4H bias to match H1
            if use_4h_filter and not higher_tf_bias_aligned(self.df_4h, h1_idx, h1_bias):
                continue
            if use_4h_filter:
                self._log(f"[4H+H1] {h1_bias} bias aligned at {h1_idx}")

            # H1 zone confirmation (Marvellous-style): use Marvellous config for lookback, require_zone, thresholds
            if use_h1_zone:
                df_h1_slice = self.df_h1.iloc[: i_h1 + 1]
                zone_result = calculate_h1_bias_with_zone_validation(
                    df_h1_slice,
                    lookback_hours=mc.LOOKBACK_H1_HOURS,
                    require_zone=mc.REQUIRE_H1_ZONE_CONFIRMATION,
                    wick_pct=h1_wick_pct,
                    body_pct=h1_body_pct,
                )
                if zone_result["bias"] == "NEUTRAL":
                    continue
                if zone_result["proof"]:
                    self._log(f"[H1] {h1_bias} zone confirmed at {h1_idx} ({zone_result['proof'].get('zone_type', 'zone')})")

            current_bias = h1_bias
            h1_ob = identify_order_block(self.df_h1, i_h1, ob_lookback=ob_lookback)
            if h1_ob is None:
                continue
            self._log(f"[H1] {current_bias} BOS/ChoCH at {h1_idx}, OB: {h1_ob}")

            future_15m = self.df_15m[self.df_15m.index > h1_idx]
            next_h1_time = h1_idx + pd.Timedelta(hours=window_hours)
            m15_window = future_15m[future_15m.index < next_h1_time]

            # State: Rule 2→3→4→5
            m15_bos_seen = False
            current_ob = None
            ob_tapped = False
            lq_swept = False  # Rule 3: sweep new high/low, zone becomes LQ
            lq_level = None
            lq_swept_back = False  # Rule 4: price returns, sweeps LQ
            ob_tested = False  # Rule 4: tests unmitigated OB
            # Diagnostic timestamps (for debugging / chart verification)
            bos_bar_time = ob_tap_bar_time = liq_sweep_bar_time = None
            lq_sweep_back_bar_time = ob_test_bar_time = None

            for idx_15, row_15 in m15_window.iterrows():
                # Session filter: extra filters use Marvellous config (London/NY/Asian); else use kill zone
                if use_extra_filters:
                    if not is_session_allowed(idx_15, mc):
                        continue
                elif use_kill_zone and idx_15.hour not in allowed_hours:
                    continue

                # Rule 2: Entry-TF BOS/ChoCH aligned with H1 bias
                if not m15_bos_seen:
                    try:
                        loc = self.df_15m.index.get_loc(idx_15)
                        i_15 = int(loc) if isinstance(loc, (int, np.integer)) else (loc.start if hasattr(loc, 'start') else 0)
                    except (KeyError, TypeError, ValueError):
                        continue
                    if current_bias == 'BULLISH' and row_15.get('bos_bull'):
                        m15_bos_seen = True
                        current_ob = identify_order_block(self.df_15m, i_15, ob_lookback=ob_lookback)
                    elif current_bias == 'BEARISH' and row_15.get('bos_bear'):
                        m15_bos_seen = True
                        current_ob = identify_order_block(self.df_15m, i_15, ob_lookback=ob_lookback)
                    if not m15_bos_seen or current_ob is None:
                        if current_ob is None and m15_bos_seen:
                            m15_bos_seen = False
                        continue
                    bos_bar_time = idx_15
                    self._log(f"[Entry-TF] BOS/ChoCH at {idx_15}, OB: {current_ob}")

                # Rule 3: Shallow tap into OB
                if current_ob is None:
                    continue
                if not ob_tapped:
                    tapped = detect_shallow_tap(
                        row_15['low'], row_15['high'],
                        current_ob['high'], current_ob['low'], current_ob['midpoint']
                    )
                    if tapped and current_bias == 'BULLISH' and row_15['close'] >= current_ob['midpoint']:
                        ob_tapped = True
                        ob_tap_bar_time = idx_15
                        self._log(f"[Entry-TF] Shallow tap into bullish OB at {idx_15}")
                    elif tapped and current_bias == 'BEARISH' and row_15['close'] <= current_ob['midpoint']:
                        ob_tapped = True
                        ob_tap_bar_time = idx_15
                        self._log(f"[Entry-TF] Shallow tap into bearish OB at {idx_15}")
                    continue

                # Rule 3: Liquidity sweep (take out new high/low), zone becomes LQ
                if not lq_swept:
                    if current_bias == 'BULLISH':
                        recent_highs = self.df_15m[
                            (self.df_15m.index < idx_15) & (self.df_15m['swing_high'] == True)
                        ].tail(liq_lookback)
                        if not recent_highs.empty:
                            liq_high = recent_highs.iloc[-1]['swing_high_price']
                            if row_15['high'] > liq_high:
                                lq_swept = True
                                lq_level = row_15['low']
                                liq_sweep_bar_time = idx_15
                                self._log(f"[Entry-TF] Liq sweep (high) at {idx_15}, LQ={lq_level}")
                    elif current_bias == 'BEARISH':
                        recent_lows = self.df_15m[
                            (self.df_15m.index < idx_15) & (self.df_15m['swing_low'] == True)
                        ].tail(liq_lookback)
                        if not recent_lows.empty:
                            liq_low = recent_lows.iloc[-1]['swing_low_price']
                            if row_15['low'] < liq_low:
                                lq_swept = True
                                lq_level = row_15['high']
                                liq_sweep_bar_time = idx_15
                                self._log(f"[Entry-TF] Liq sweep (low) at {idx_15}, LQ={lq_level}")
                    if not lq_swept:
                        continue

                # Rule 4: Price returns, sweeps LQ
                if not lq_swept_back:
                    if current_bias == 'BULLISH' and lq_level is not None:
                        if row_15['low'] <= lq_level:
                            lq_swept_back = True
                            lq_sweep_back_bar_time = idx_15
                            self._log(f"[Entry-TF] Price swept LQ at {idx_15}")
                    elif current_bias == 'BEARISH' and lq_level is not None:
                        if row_15['high'] >= lq_level:
                            lq_swept_back = True
                            lq_sweep_back_bar_time = idx_15
                            self._log(f"[Entry-TF] Price swept LQ at {idx_15}")
                    if not lq_swept_back:
                        continue

                # Rule 4: Test unmitigated OB
                if not ob_tested:
                    tapped = detect_shallow_tap(
                        row_15['low'], row_15['high'],
                        current_ob['high'], current_ob['low'], current_ob['midpoint']
                    )
                    if tapped and current_bias == 'BULLISH' and row_15['close'] >= current_ob['midpoint']:
                        ob_tested = True
                        ob_test_bar_time = idx_15
                    elif tapped and current_bias == 'BEARISH' and row_15['close'] <= current_ob['midpoint']:
                        ob_tested = True
                        ob_test_bar_time = idx_15
                    if not ob_tested:
                        continue

                # Rule 5: Entry on displacement candle
                candle_body = abs(row_15['close'] - row_15['open'])
                candle_range = row_15['high'] - row_15['low']
                is_displacement = candle_body > (candle_range * disp_ratio) if candle_range > 0 else False
                if use_ema:
                    ema_val = row_15.get(f'ema_{config.EMA_PERIOD}')
                    if pd.isna(ema_val):
                        continue
                    if current_bias == 'BULLISH' and row_15['close'] <= ema_val:
                        continue
                    if current_bias == 'BEARISH' and row_15['close'] >= ema_val:
                        continue

                if current_bias == 'BULLISH':
                    is_bullish = row_15['close'] > row_15['open']
                    entry = row_15['close']
                    # SL must be below entry for BUY
                    if is_bullish and is_displacement and row_15['close'] > current_ob['low']:
                        if lq_level is None or float(lq_level) >= float(entry):
                            continue
                        # Extra filters: ATR, spread, liquidity map — uses MARVELLOUS_* config
                        if use_extra_filters:
                            atr_val = atr_series.loc[idx_15] if idx_15 in atr_series.index else None
                            if atr_val is not None and not pd.isna(atr_val) and float(atr_val) < mc.MIN_ATR_THRESHOLD:
                                continue
                            if getattr(config, 'BACKTEST_SPREAD_PIPS', 0) > mc.MAX_SPREAD_POINTS:
                                continue
                            if mc.USE_LIQUIDITY_MAP:
                                entry_slice = self.df_15m[self.df_15m.index <= idx_15]
                                atr_slice = atr_series[atr_series.index <= idx_15] if atr_series is not None else None
                                if not is_liquidity_map_valid(entry_slice, mc.LIQUIDITY_ZONE_STRENGTH_THRESHOLD, atr_slice):
                                    continue
                        future_highs = self.df_15m[
                            (self.df_15m.index > idx_15) & (self.df_15m['swing_high'] == True)
                        ].head(tp_lookahead)
                        tp_price = future_highs.iloc[0]['swing_high_price'] if not future_highs.empty else None
                        _ts = lambda t: t.strftime('%Y-%m-%d %H:%M') if hasattr(t, 'strftime') else str(t)
                        signals.append({
                            'time': idx_15,
                            'type': 'BUY',
                            'price': entry,
                            'sl': lq_level,
                            'tp': tp_price,
                            'reason': 'Kingsley Gold: 4H+H1+entry-TF BOS + OB tap + Liq sweep + OB test',
                            'kingsley_diagnostic': {
                                'h1_bar': _ts(h1_idx),
                                'bos_bar': _ts(bos_bar_time) if bos_bar_time is not None else None,
                                'ob_tap_bar': _ts(ob_tap_bar_time) if ob_tap_bar_time is not None else None,
                                'liq_sweep_bar': _ts(liq_sweep_bar_time) if liq_sweep_bar_time is not None else None,
                                'lq_sweep_back_bar': _ts(lq_sweep_back_bar_time) if lq_sweep_back_bar_time is not None else None,
                                'ob_test_bar': _ts(ob_test_bar_time) if ob_test_bar_time is not None else None,
                                'entry_bar': _ts(idx_15),
                            },
                        })
                        self._log(f"[Entry-TF] BUY signal at {idx_15}")
                        break
                elif current_bias == 'BEARISH':
                    is_bearish = row_15['close'] < row_15['open']
                    entry = row_15['close']
                    # SL must be above entry for SELL
                    if is_bearish and is_displacement and row_15['close'] < current_ob['high']:
                        if lq_level is None or float(lq_level) <= float(entry):
                            continue
                        # Extra filters: ATR, spread, liquidity map — uses MARVELLOUS_* config
                        if use_extra_filters:
                            atr_val = atr_series.loc[idx_15] if idx_15 in atr_series.index else None
                            if atr_val is not None and not pd.isna(atr_val) and float(atr_val) < mc.MIN_ATR_THRESHOLD:
                                continue
                            if getattr(config, 'BACKTEST_SPREAD_PIPS', 0) > mc.MAX_SPREAD_POINTS:
                                continue
                            if mc.USE_LIQUIDITY_MAP:
                                entry_slice = self.df_15m[self.df_15m.index <= idx_15]
                                atr_slice = atr_series[atr_series.index <= idx_15] if atr_series is not None else None
                                if not is_liquidity_map_valid(entry_slice, mc.LIQUIDITY_ZONE_STRENGTH_THRESHOLD, atr_slice):
                                    continue
                        future_lows = self.df_15m[
                            (self.df_15m.index > idx_15) & (self.df_15m['swing_low'] == True)
                        ].head(tp_lookahead)
                        tp_price = future_lows.iloc[0]['swing_low_price'] if not future_lows.empty else None
                        _ts = lambda t: t.strftime('%Y-%m-%d %H:%M') if hasattr(t, 'strftime') else str(t)
                        signals.append({
                            'time': idx_15,
                            'type': 'SELL',
                            'price': entry,
                            'sl': lq_level,
                            'tp': tp_price,
                            'reason': 'Kingsley Gold: 4H+H1+entry-TF BOS + OB tap + Liq sweep + OB test',
                            'kingsley_diagnostic': {
                                'h1_bar': _ts(h1_idx),
                                'bos_bar': _ts(bos_bar_time) if bos_bar_time is not None else None,
                                'ob_tap_bar': _ts(ob_tap_bar_time) if ob_tap_bar_time is not None else None,
                                'liq_sweep_bar': _ts(liq_sweep_bar_time) if liq_sweep_bar_time is not None else None,
                                'lq_sweep_back_bar': _ts(lq_sweep_back_bar_time) if lq_sweep_back_bar_time is not None else None,
                                'ob_test_bar': _ts(ob_test_bar_time) if ob_test_bar_time is not None else None,
                                'entry_bar': _ts(idx_15),
                            },
                        })
                        self._log(f"[Entry-TF] SELL signal at {idx_15}")
                        break

        return pd.DataFrame(signals)
