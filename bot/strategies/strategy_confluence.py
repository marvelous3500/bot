"""
Confluence strategy: Kill zone + 4H structure (BOS/CHoCH) + 15m OB entry.
SL is set externally (e.g. 50 pips).
"""
import pandas as pd
import config
from ..indicators import detect_order_block, detect_liquidity_sweep
from ..indicators_bos import detect_swing_highs_lows, detect_break_of_structure


class ConfluenceStrategy:
    """Multi-timeframe confluence: 4H BOS + 15m OB, kill zone."""

    def __init__(self, df_4h, df_15m):
        self.df_4h = df_4h.copy()
        self.df_15m = df_15m.copy()

    def prepare_data(self):
        self.df_4h = detect_swing_highs_lows(self.df_4h, swing_length=3)
        self.df_4h = detect_break_of_structure(self.df_4h)
        self.df_4h = detect_liquidity_sweep(self.df_4h, lookback=10)
        self.df_15m = detect_order_block(self.df_15m)
        if config.USE_EMA_FILTER:
            from ..indicators import calculate_ema
            self.df_4h = calculate_ema(self.df_4h, period=config.EMA_PERIOD)
            self.df_15m = calculate_ema(self.df_15m, period=config.EMA_PERIOD)
        return self.df_4h, self.df_15m

    def run_backtest(self):
        signals = []
        bias = None
        bias_time = None
        use_sweep = getattr(config, 'CONFLUENCE_REQUIRE_SWEEP', False)
        for i_4h in range(1, len(self.df_4h)):
            current_4h_idx = self.df_4h.index[i_4h]
            row_4h = self.df_4h.iloc[i_4h]
            if row_4h['bos_bull']:
                if not use_sweep or row_4h.get('sweep_low', False):
                    bias = 'BULLISH'
                    bias_time = current_4h_idx
            elif row_4h['bos_bear']:
                if not use_sweep or row_4h.get('sweep_high', False):
                    bias = 'BEARISH'
                    bias_time = current_4h_idx
            if bias is None or bias_time is None:
                continue
            future_15m = self.df_15m[self.df_15m.index > bias_time]
            search_window = future_15m.head(20)
            for idx_15m, row_15m in search_window.iterrows():
                in_kill_zone = True
                if config.USE_KILL_ZONES:
                    in_kill_zone = idx_15m.hour in config.KILL_ZONE_HOURS
                if not in_kill_zone:
                    continue
                if config.USE_EMA_FILTER:
                    ema_val = row_15m.get(f'ema_{config.EMA_PERIOD}')
                    if pd.isna(ema_val):
                        continue
                    close_15m = row_15m['close']
                    if bias == 'BULLISH' and close_15m <= ema_val:
                        continue
                    if bias == 'BEARISH' and close_15m >= ema_val:
                        continue
                if bias == 'BULLISH' and row_15m['ob_bull']:
                    signals.append({
                        'time': idx_15m,
                        'type': 'BUY',
                        'price': row_15m['close'],
                        'reason': '4H BOS + 15m OB (Kill Zone)'
                    })
                    bias = None
                    bias_time = None
                    break
                elif bias == 'BEARISH' and row_15m['ob_bear']:
                    signals.append({
                        'time': idx_15m,
                        'type': 'SELL',
                        'price': row_15m['close'],
                        'reason': '4H BOS + 15m OB (Kill Zone)'
                    })
                    bias = None
                    bias_time = None
                    break
            if bias is not None and len(search_window) >= 20:
                bias = None
                bias_time = None
        return pd.DataFrame(signals)
