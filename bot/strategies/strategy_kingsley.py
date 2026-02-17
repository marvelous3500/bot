"""
Kingsley Gold Strategy: H1 trend + 15m BOS/ChoCH + zone→LQ + liquidity sweep + OB test.
Rules: 1) 1H trend, 2) 15m BOS/ChoCH, 3) Shallow tap → zone=LQ → sweep high/low,
4) Price returns, sweeps LQ, tests OB, 5) Entry, target high/low.
Gold only (XAUUSD/GC=F).
"""
import pandas as pd
import numpy as np
import config
from ..indicators_bos import (
    detect_swing_highs_lows,
    detect_break_of_structure,
    identify_order_block,
    detect_shallow_tap,
)


class KingsleyGoldStrategy:
    """ICT-style: H1 trend + 15m BOS/ChoCH + zone→LQ + sweep + OB test + entry."""

    def __init__(self, df_h1, df_15m, verbose=True):
        self.df_h1 = df_h1.copy()
        self.df_15m = df_15m.copy()
        self.verbose = verbose

    def _log(self, msg):
        if self.verbose:
            print(msg)

    def prepare_data(self):
        self._log("Detecting swing highs/lows on H1...")
        self.df_h1 = detect_swing_highs_lows(self.df_h1, swing_length=3)
        self._log("Detecting Break of Structure on H1...")
        self.df_h1 = detect_break_of_structure(self.df_h1)
        self._log("Detecting swing highs/lows on 15m...")
        self.df_15m = detect_swing_highs_lows(self.df_15m, swing_length=3)
        self._log("Detecting Break of Structure on 15m...")
        self.df_15m = detect_break_of_structure(self.df_15m)
        if getattr(config, 'KINGSLEY_USE_EMA_FILTER', False):
            from ..indicators import calculate_ema
            self.df_h1 = calculate_ema(self.df_h1, period=config.EMA_PERIOD)
            self.df_15m = calculate_ema(self.df_15m, period=config.EMA_PERIOD)
        return self.df_h1, self.df_15m

    def run_backtest(self):
        if self.df_h1.empty or self.df_15m.empty:
            return pd.DataFrame()
        signals = []
        use_kill_zone = getattr(config, 'KINGSLEY_USE_KILL_ZONES', True)
        use_ema = getattr(config, 'KINGSLEY_USE_EMA_FILTER', False)
        window_hours = getattr(config, 'KINGSLEY_15M_WINDOW_HOURS', 8)
        disp_ratio = getattr(config, 'KINGSLEY_DISPLACEMENT_RATIO', 0.6)

        for i_h1 in range(len(self.df_h1)):
            h1_idx = self.df_h1.index[i_h1]
            h1_row = self.df_h1.iloc[i_h1]
            if not h1_row['bos_bull'] and not h1_row['bos_bear']:
                continue
            current_bias = 'BULLISH' if h1_row['bos_bull'] else 'BEARISH'
            h1_ob = identify_order_block(self.df_h1, i_h1)
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

            for idx_15, row_15 in m15_window.iterrows():
                if use_kill_zone and idx_15.hour not in config.KILL_ZONE_HOURS:
                    continue

                # Rule 2: 15m BOS/ChoCH aligned with H1 bias
                if not m15_bos_seen:
                    try:
                        loc = self.df_15m.index.get_loc(idx_15)
                        i_15 = int(loc) if isinstance(loc, (int, np.integer)) else (loc.start if hasattr(loc, 'start') else 0)
                    except (KeyError, TypeError, ValueError):
                        continue
                    if current_bias == 'BULLISH' and row_15.get('bos_bull'):
                        m15_bos_seen = True
                        current_ob = identify_order_block(self.df_15m, i_15)
                    elif current_bias == 'BEARISH' and row_15.get('bos_bear'):
                        m15_bos_seen = True
                        current_ob = identify_order_block(self.df_15m, i_15)
                    if not m15_bos_seen or current_ob is None:
                        continue
                    self._log(f"[15m] BOS/ChoCH at {idx_15}, OB: {current_ob}")

                # Rule 3: Shallow tap into OB
                if not ob_tapped:
                    tapped = detect_shallow_tap(
                        row_15['low'], row_15['high'],
                        current_ob['high'], current_ob['low'], current_ob['midpoint']
                    )
                    if tapped and current_bias == 'BULLISH' and row_15['close'] >= current_ob['midpoint']:
                        ob_tapped = True
                        self._log(f"[15m] Shallow tap into bullish OB at {idx_15}")
                    elif tapped and current_bias == 'BEARISH' and row_15['close'] <= current_ob['midpoint']:
                        ob_tapped = True
                        self._log(f"[15m] Shallow tap into bearish OB at {idx_15}")
                    continue

                # Rule 3: Liquidity sweep (take out new high/low), zone becomes LQ
                if not lq_swept:
                    if current_bias == 'BULLISH':
                        recent_highs = self.df_15m[
                            (self.df_15m.index < idx_15) & (self.df_15m['swing_high'] == True)
                        ].tail(5)
                        if not recent_highs.empty:
                            liq_high = recent_highs.iloc[-1]['swing_high_price']
                            if row_15['high'] > liq_high:
                                lq_swept = True
                                lq_level = row_15['low']
                                self._log(f"[15m] Liq sweep (high) at {idx_15}, LQ={lq_level}")
                    elif current_bias == 'BEARISH':
                        recent_lows = self.df_15m[
                            (self.df_15m.index < idx_15) & (self.df_15m['swing_low'] == True)
                        ].tail(5)
                        if not recent_lows.empty:
                            liq_low = recent_lows.iloc[-1]['swing_low_price']
                            if row_15['low'] < liq_low:
                                lq_swept = True
                                lq_level = row_15['high']
                                self._log(f"[15m] Liq sweep (low) at {idx_15}, LQ={lq_level}")
                    if not lq_swept:
                        continue

                # Rule 4: Price returns, sweeps LQ
                if not lq_swept_back:
                    if current_bias == 'BULLISH' and lq_level is not None:
                        if row_15['low'] <= lq_level:
                            lq_swept_back = True
                            self._log(f"[15m] Price swept LQ at {idx_15}")
                    elif current_bias == 'BEARISH' and lq_level is not None:
                        if row_15['high'] >= lq_level:
                            lq_swept_back = True
                            self._log(f"[15m] Price swept LQ at {idx_15}")
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
                    elif tapped and current_bias == 'BEARISH' and row_15['close'] <= current_ob['midpoint']:
                        ob_tested = True
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
                        future_highs = self.df_15m[
                            (self.df_15m.index > idx_15) & (self.df_15m['swing_high'] == True)
                        ].head(3)
                        tp_price = future_highs.iloc[0]['swing_high_price'] if not future_highs.empty else None
                        signals.append({
                            'time': idx_15,
                            'type': 'BUY',
                            'price': entry,
                            'sl': lq_level,
                            'tp': tp_price,
                            'reason': 'Kingsley Gold: H1+15m BOS + OB tap + Liq sweep + OB test'
                        })
                        self._log(f"[15m] BUY signal at {idx_15}")
                        break
                elif current_bias == 'BEARISH':
                    is_bearish = row_15['close'] < row_15['open']
                    entry = row_15['close']
                    # SL must be above entry for SELL
                    if is_bearish and is_displacement and row_15['close'] < current_ob['high']:
                        if lq_level is None or float(lq_level) <= float(entry):
                            continue
                        future_lows = self.df_15m[
                            (self.df_15m.index > idx_15) & (self.df_15m['swing_low'] == True)
                        ].head(3)
                        tp_price = future_lows.iloc[0]['swing_low_price'] if not future_lows.empty else None
                        signals.append({
                            'time': idx_15,
                            'type': 'SELL',
                            'price': entry,
                            'sl': lq_level,
                            'tp': tp_price,
                            'reason': 'Kingsley Gold: H1+15m BOS + OB tap + Liq sweep + OB test'
                        })
                        self._log(f"[15m] SELL signal at {idx_15}")
                        break

        return pd.DataFrame(signals)
