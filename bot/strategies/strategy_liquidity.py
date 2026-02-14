import pandas as pd
import config
from ..indicators import detect_fvg, detect_order_block, detect_liquidity_sweep, detect_rejection_candle

class LiquiditySweepStrategy:
    """Multi-timeframe: 4H sweep → 1H confirmation → 15m entry."""

    def __init__(self, df_4h, df_1h, df_15m):
        self.df_4h = df_4h.copy()
        self.df_1h = df_1h.copy()
        self.df_15m = df_15m.copy()

    def prepare_data(self):
        self.df_4h = detect_liquidity_sweep(self.df_4h, lookback=10)
        self.df_1h = detect_liquidity_sweep(self.df_1h, lookback=5)
        self.df_1h = detect_rejection_candle(self.df_1h)
        self.df_15m = detect_fvg(self.df_15m)
        self.df_15m = detect_order_block(self.df_15m)
        self.df_15m = detect_rejection_candle(self.df_15m)
        use_ema = getattr(config, 'LIQUIDITY_USE_EMA_FILTER', config.USE_EMA_FILTER)
        if use_ema:
            from ..indicators import calculate_ema
            self.df_4h = calculate_ema(self.df_4h, period=50)
            self.df_1h = calculate_ema(self.df_1h, period=50)
            self.df_15m = calculate_ema(self.df_15m, period=50)
        return self.df_4h, self.df_1h, self.df_15m

    def run_backtest(self):
        signals = []
        sweep_direction = None
        sweep_time = None
        sweep_candle_high = None
        sweep_candle_low = None
        waiting_for_entry = False
        confirm_bars = getattr(config, 'LIQUIDITY_1H_CONFIRM_BARS', 6)
        entry_bars = getattr(config, 'LIQUIDITY_15M_ENTRY_BARS', 8)

        for i_4h in range(1, len(self.df_4h)):
            current_4h_idx = self.df_4h.index[i_4h]
            row_4h = self.df_4h.iloc[i_4h]
            if row_4h['sweep_low'] and not waiting_for_entry:
                sweep_direction = 'BULLISH'
                sweep_time = current_4h_idx
                sweep_candle_high = row_4h['high']
                sweep_candle_low = row_4h['low']
                waiting_for_entry = True
            elif row_4h['sweep_high'] and not waiting_for_entry:
                sweep_direction = 'BEARISH'
                sweep_time = current_4h_idx
                sweep_candle_high = row_4h['high']
                sweep_candle_low = row_4h['low']
                waiting_for_entry = True

            if waiting_for_entry:
                future_1h = self.df_1h[self.df_1h.index > sweep_time]
                h1_window = future_1h.head(confirm_bars)
                confirm_time = None
                strict_1h = getattr(config, 'LIQUIDITY_STRICT_1H_CONFIRM', False)
                for idx_1h, row_1h in h1_window.iterrows():
                    if sweep_direction == 'BULLISH':
                        h1_confirm = (row_1h.get('sweep_low', False) or row_1h.get('rejection_bull', False))
                        if not strict_1h:
                            h1_confirm = h1_confirm or (row_1h['close'] > row_1h['open'])
                        if h1_confirm:
                            confirm_time = idx_1h
                            break
                    elif sweep_direction == 'BEARISH':
                        h1_confirm = (row_1h.get('sweep_high', False) or row_1h.get('rejection_bear', False))
                        if not strict_1h:
                            h1_confirm = h1_confirm or (row_1h['close'] < row_1h['open'])
                        if h1_confirm:
                            confirm_time = idx_1h
                            break

                if confirm_time is None:
                    if len(h1_window) >= confirm_bars:
                        waiting_for_entry = False
                        sweep_direction = None
                    continue

                future_15m = self.df_15m[self.df_15m.index > confirm_time]
                search_window = future_15m.head(entry_bars)
                use_kill_zone = getattr(config, 'LIQUIDITY_USE_KILL_ZONES', config.USE_KILL_ZONES)
                use_ema = getattr(config, 'LIQUIDITY_USE_EMA_FILTER', config.USE_EMA_FILTER)
                for idx_15m, row_15m in search_window.iterrows():
                    in_kill_zone = True
                    if use_kill_zone:
                        in_kill_zone = idx_15m.hour in config.KILL_ZONE_HOURS
                    if not in_kill_zone:
                        continue
                    is_uptrend = True
                    is_downtrend = True
                    if use_ema:
                        ema_val = row_15m.get(f'ema_{config.EMA_PERIOD}')
                        if pd.isna(ema_val):
                            continue
                        close_15m = row_15m['close']
                        is_uptrend = close_15m > ema_val
                        is_downtrend = close_15m < ema_val
                    if sweep_direction == 'BULLISH' and is_uptrend:
                        require_15m = getattr(config, 'LIQUIDITY_REQUIRE_15M_CONFIRM', True)
                        has_confirmation = (row_15m.get('fvg_bull', False) or row_15m.get('ob_bull', False) or row_15m.get('rejection_bull', False)) if require_15m else True
                        if has_confirmation:
                            sl = sweep_candle_low if sweep_candle_low is not None else row_15m['low']
                            signals.append({
                                'time': idx_15m,
                                'type': 'BUY',
                                'price': row_15m['close'],
                                'sl': sl,
                                'reason': '4H Sweep Low + 1H Confirm + 15m FVG/OB'
                            })
                            waiting_for_entry = False
                            sweep_direction = None
                            break
                    elif sweep_direction == 'BEARISH' and is_downtrend:
                        require_15m = getattr(config, 'LIQUIDITY_REQUIRE_15M_CONFIRM', True)
                        has_confirmation = (row_15m.get('fvg_bear', False) or row_15m.get('ob_bear', False) or row_15m.get('rejection_bear', False)) if require_15m else True
                        if has_confirmation:
                            sl = sweep_candle_high if sweep_candle_high is not None else row_15m['high']
                            signals.append({
                                'time': idx_15m,
                                'type': 'SELL',
                                'price': row_15m['close'],
                                'sl': sl,
                                'reason': '4H Sweep High + 1H Confirm + 15m FVG/OB'
                            })
                            waiting_for_entry = False
                            sweep_direction = None
                            break
                if waiting_for_entry and len(search_window) >= entry_bars:
                    waiting_for_entry = False
                    sweep_direction = None
        return pd.DataFrame(signals)
