import pandas as pd
import numpy as np
import config
from ..indicators_bos import (
    detect_swing_highs_lows,
    detect_break_of_structure,
    identify_order_block,
    detect_shallow_tap,
    higher_tf_bias_aligned,
)

class H1M5BOSStrategy:
    """Multi-timeframe ICT: H1 BOS + OB, M5 shallow tap + liquidity sweep + entry."""

    def __init__(self, df_h1, df_m5, df_4h=None, df_daily=None):
        self.df_h1 = df_h1.copy()
        self.df_m5 = df_m5.copy()
        self.df_4h = df_4h.copy() if df_4h is not None and not df_4h.empty else None
        self.df_daily = df_daily.copy() if df_daily is not None and not df_daily.empty else None

    def prepare_data(self):
        if self.df_4h is not None:
            self.df_4h = detect_swing_highs_lows(self.df_4h, swing_length=3)
            self.df_4h = detect_break_of_structure(self.df_4h)
        if self.df_daily is not None:
            self.df_daily = detect_swing_highs_lows(self.df_daily, swing_length=3)
            self.df_daily = detect_break_of_structure(self.df_daily)
        print("Detecting swing highs/lows on H1...")
        self.df_h1 = detect_swing_highs_lows(self.df_h1, swing_length=3)
        print("Detecting Break of Structure on H1...")
        self.df_h1 = detect_break_of_structure(self.df_h1)
        print("Detecting swing highs/lows on M5...")
        self.df_m5 = detect_swing_highs_lows(self.df_m5, swing_length=3)
        if getattr(config, 'BOS_USE_EMA_FILTER', False):
            from ..indicators import calculate_ema
            self.df_h1 = calculate_ema(self.df_h1, period=config.EMA_PERIOD)
            self.df_m5 = calculate_ema(self.df_m5, period=config.EMA_PERIOD)
        return self.df_h1, self.df_m5

    def run_backtest(self):
        signals = []
        current_bias = None
        current_ob = None
        ob_tapped = False
        liquidity_swept = False
        liquidity_level = None
        for i_h1 in range(len(self.df_h1)):
            h1_idx = self.df_h1.index[i_h1]
            h1_row = self.df_h1.iloc[i_h1]
            if h1_row['bos_bull']:
                current_bias = 'BULLISH'
                current_ob = identify_order_block(self.df_h1, i_h1)
                ob_tapped = False
                liquidity_swept = False
                if getattr(config, 'USE_4H_BIAS_FILTER', False) and not higher_tf_bias_aligned(self.df_4h, h1_idx, 'BULLISH'):
                    continue
                if getattr(config, 'USE_DAILY_BIAS_FILTER', False) and not higher_tf_bias_aligned(self.df_daily, h1_idx, 'BULLISH'):
                    continue
                print(f"[H1] Bullish BOS detected at {h1_idx}, OB: {current_ob}")
            elif h1_row['bos_bear']:
                current_bias = 'BEARISH'
                current_ob = identify_order_block(self.df_h1, i_h1)
                ob_tapped = False
                liquidity_swept = False
                if getattr(config, 'USE_4H_BIAS_FILTER', False) and not higher_tf_bias_aligned(self.df_4h, h1_idx, 'BEARISH'):
                    continue
                if getattr(config, 'USE_DAILY_BIAS_FILTER', False) and not higher_tf_bias_aligned(self.df_daily, h1_idx, 'BEARISH'):
                    continue
                print(f"[H1] Bearish BOS detected at {h1_idx}, OB: {current_ob}")
            if current_bias and current_ob:
                future_m5 = self.df_m5[self.df_m5.index > h1_idx]
                window_hours = getattr(config, 'BOS_M5_WINDOW_HOURS', 4)
                next_h1_time = h1_idx + pd.Timedelta(hours=window_hours)
                m5_window = future_m5[future_m5.index < next_h1_time]
                use_kill_zone = getattr(config, 'BOS_USE_KILL_ZONES', False)
                use_ema = getattr(config, 'BOS_USE_EMA_FILTER', False)
                entry_found = False
                for idx_m5, row_m5 in m5_window.iterrows():
                    if entry_found:
                        break
                    if use_kill_zone and idx_m5.hour not in config.KILL_ZONE_HOURS:
                        continue
                    if not ob_tapped:
                        tapped = detect_shallow_tap(
                            row_m5['low'], row_m5['high'],
                            current_ob['high'], current_ob['low'], current_ob['midpoint']
                        )
                        if tapped and current_bias == 'BULLISH' and row_m5['close'] >= current_ob['midpoint']:
                            ob_tapped = True
                            liquidity_level = None
                            print(f"[M5] Shallow tap into bullish OB at {idx_m5}")
                        elif tapped and current_bias == 'BEARISH' and row_m5['close'] <= current_ob['midpoint']:
                            ob_tapped = True
                            liquidity_level = None
                            print(f"[M5] Shallow tap into bearish OB at {idx_m5}")
                    if ob_tapped and not liquidity_swept:
                        if current_bias == 'BULLISH':
                            recent_m5_highs = self.df_m5[
                                (self.df_m5.index < idx_m5) & (self.df_m5['swing_high'] == True)
                            ].tail(5)
                            if not recent_m5_highs.empty:
                                liquidity_high = recent_m5_highs.iloc[-1]['swing_high_price']
                                if row_m5['high'] > liquidity_high:
                                    liquidity_swept = True
                                    liquidity_level = row_m5['low']
                                    print(f"[M5] Liquidity swept (high) at {idx_m5}, level: {liquidity_high}")
                        elif current_bias == 'BEARISH':
                            recent_m5_lows = self.df_m5[
                                (self.df_m5.index < idx_m5) & (self.df_m5['swing_low'] == True)
                            ].tail(5)
                            if not recent_m5_lows.empty:
                                liquidity_low = recent_m5_lows.iloc[-1]['swing_low_price']
                                if row_m5['low'] < liquidity_low:
                                    liquidity_swept = True
                                    liquidity_level = row_m5['high']
                                    print(f"[M5] Liquidity swept (low) at {idx_m5}, level: {liquidity_low}")
                    if ob_tapped and liquidity_swept and liquidity_level is not None:
                        candle_body = abs(row_m5['close'] - row_m5['open'])
                        candle_range = row_m5['high'] - row_m5['low']
                        disp_ratio = getattr(config, 'BOS_DISPLACEMENT_RATIO', 0.6)
                        is_displacement = candle_body > (candle_range * disp_ratio) if candle_range > 0 else False
                        if use_ema:
                            ema_val = row_m5.get(f'ema_{config.EMA_PERIOD}')
                            if pd.isna(ema_val):
                                continue
                            if current_bias == 'BULLISH' and row_m5['close'] <= ema_val:
                                continue
                            if current_bias == 'BEARISH' and row_m5['close'] >= ema_val:
                                continue
                        if current_bias == 'BULLISH':
                            is_bullish_candle = row_m5['close'] > row_m5['open']
                            if is_bullish_candle and is_displacement and row_m5['close'] > current_ob['low']:
                                signals.append({
                                    'time': idx_m5,
                                    'type': 'BUY',
                                    'price': row_m5['close'],
                                    'sl': liquidity_level,
                                    'reason': 'H1 BOS + OB + Liq Sweep + Displacement'
                                })
                                print(f"[M5] BUY signal at {idx_m5}")
                                current_bias = None
                                current_ob = None
                                ob_tapped = False
                                liquidity_swept = False
                                entry_found = True
                        elif current_bias == 'BEARISH':
                            is_bearish_candle = row_m5['close'] < row_m5['open']
                            if is_bearish_candle and is_displacement and row_m5['close'] < current_ob['high']:
                                signals.append({
                                    'time': idx_m5,
                                    'type': 'SELL',
                                    'price': row_m5['close'],
                                    'sl': liquidity_level,
                                    'reason': 'H1 BOS + OB + Liq Sweep + Displacement'
                                })
                                print(f"[M5] SELL signal at {idx_m5}")
                                current_bias = None
                                current_ob = None
                                ob_tapped = False
                                liquidity_swept = False
                                entry_found = True
        return pd.DataFrame(signals)
