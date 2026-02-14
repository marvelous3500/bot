import pandas as pd
import config
from ..indicators import detect_fvg, detect_order_block, detect_liquidity_sweep

class ICTStrategy:
    def __init__(self, dataframe):
        self.df = dataframe.copy()

    def prepare_data(self):
        self.df = detect_fvg(self.df)
        self.df = detect_order_block(self.df)
        self.df = detect_liquidity_sweep(self.df)
        if config.USE_DISPLACEMENT_FILTER:
            from ..indicators import detect_displacement
            self.df = detect_displacement(self.df)
        if config.USE_EMA_FILTER:
            from ..indicators import calculate_ema
            self.df = calculate_ema(self.df, period=config.EMA_PERIOD)
        return self.df

    def run_backtest(self, pdh_series, pdl_series):
        signals = []
        bias = None
        waiting_for_retest = False
        break_level = None
        for i in range(1, len(self.df)):
            current_idx = self.df.index[i]
            row = self.df.iloc[i]
            prev_row = self.df.iloc[i-1]
            pdh = pdh_series.loc[current_idx]
            pdl = pdl_series.loc[current_idx]
            close = row['close']
            prev_close = prev_row['close']
            if config.USE_KILL_ZONES:
                current_hour = current_idx.hour
                if current_hour not in config.KILL_ZONE_HOURS:
                    pass
            is_uptrend = True
            is_downtrend = True
            if config.USE_EMA_FILTER:
                ema_val = row[f'ema_{config.EMA_PERIOD}']
                is_uptrend = close > ema_val
                is_downtrend = close < ema_val
            if not waiting_for_retest:
                market_structure_bullish = True
                if config.USE_MARKET_STRUCTURE_FILTER and i >= 10:
                    recent_high = self.df.iloc[i-10:i]['high'].max()
                    market_structure_bullish = row['high'] > recent_high
                if prev_close <= pdh and close > pdh and is_uptrend and market_structure_bullish:
                    bias = 'BULLISH'
                    waiting_for_retest = True
                    break_level = pdh
                market_structure_bearish = True
                if config.USE_MARKET_STRUCTURE_FILTER and i >= 10:
                    recent_low = self.df.iloc[i-10:i]['low'].min()
                    market_structure_bearish = row['low'] < recent_low
                elif prev_close >= pdl and close < pdl and is_downtrend and market_structure_bearish:
                    bias = 'BEARISH'
                    waiting_for_retest = True
                    break_level = pdl
            elif waiting_for_retest:
                if bias == 'BULLISH':
                    is_near_level = (row['low'] <= break_level * 1.0005)
                    if is_near_level:
                        in_kill_zone = True
                        if config.USE_KILL_ZONES:
                            in_kill_zone = current_idx.hour in config.KILL_ZONE_HOURS
                        if config.REQUIRE_BOTH_FVG_AND_OB:
                            has_confirmation = row['fvg_bull'] and row['ob_bull']
                        else:
                            has_confirmation = row['fvg_bull'] or row['ob_bull']
                        has_displacement = False
                        if config.USE_DISPLACEMENT_FILTER:
                            lookback_start = max(0, i - 5)
                            recent_displacements = self.df.iloc[lookback_start:i+1]['displacement_bull']
                            has_displacement = recent_displacements.any()
                        else:
                            has_displacement = True
                        if has_confirmation and in_kill_zone and has_displacement:
                            signals.append({
                                'time': current_idx,
                                'type': 'BUY',
                                'price': close,
                                'sl': row['low'],
                                'reason': 'HIGH-PROB: FVG+OB+Displacement+EMA+KillZone'
                            })
                            waiting_for_retest = False
                            bias = None
                elif bias == 'BEARISH':
                    is_near_level = (row['high'] >= break_level * 0.999)
                    if is_near_level:
                        in_kill_zone = True
                        if config.USE_KILL_ZONES:
                            in_kill_zone = current_idx.hour in config.KILL_ZONE_HOURS
                        if config.REQUIRE_BOTH_FVG_AND_OB:
                            has_confirmation = row['fvg_bear'] and row['ob_bear']
                        else:
                            has_confirmation = row['fvg_bear'] or row['ob_bear']
                        has_displacement = False
                        if config.USE_DISPLACEMENT_FILTER:
                            lookback_start = max(0, i - 5)
                            recent_displacements = self.df.iloc[lookback_start:i+1]['displacement_bear']
                            has_displacement = recent_displacements.any()
                        else:
                            has_displacement = True
                        if has_confirmation and in_kill_zone and has_displacement:
                            signals.append({
                                'time': current_idx,
                                'type': 'SELL',
                                'price': close,
                                'sl': row['high'],
                                'reason': 'HIGH-PROB: FVG+OB+Displacement+EMA+KillZone'
                            })
                            waiting_for_retest = False
                            bias = None
        return pd.DataFrame(signals)
