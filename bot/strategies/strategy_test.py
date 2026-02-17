"""Test strategy: simple H1 trend follow on gold. For verifying live execution."""
import pandas as pd
import config


class TestStrategy:
    """Minimal: H1 trend (last 3 closes) + BUY/SELL with fixed SL/TP. Gold only."""

    def __init__(self, df_h1, verbose=False):
        self.df_h1 = df_h1.copy()
        self.verbose = verbose

    def prepare_data(self):
        return self.df_h1, None

    def run_backtest(self):
        if self.df_h1.empty or len(self.df_h1) < 4:
            return pd.DataFrame()
        sl_dist = getattr(config, 'TEST_SL_DISTANCE', 5.0)
        tp_dist = getattr(config, 'TEST_TP_DISTANCE', 15.0)
        use_kill_zone = getattr(config, 'TEST_USE_KILL_ZONES', False)  # False = always emit
        signals = []
        for i in range(3, len(self.df_h1)):
            row = self.df_h1.iloc[i]
            if use_kill_zone and row.name.hour not in config.KILL_ZONE_HOURS:
                continue
            closes = [self.df_h1.iloc[i - j]['close'] for j in range(4)]
            up = sum(1 for j in range(1, 4) if closes[j] > closes[j - 1])
            if up >= 2:  # bullish
                entry = row['close']
                signals.append({
                    'time': row.name,
                    'type': 'BUY',
                    'price': entry,
                    'sl': entry - sl_dist,
                    'tp': entry + tp_dist,
                    'reason': 'Test: H1 trend follow',
                })
            else:  # bearish
                entry = row['close']
                signals.append({
                    'time': row.name,
                    'type': 'SELL',
                    'price': entry,
                    'sl': entry + sl_dist,
                    'tp': entry - tp_dist,
                    'reason': 'Test: H1 trend follow',
                })
        return pd.DataFrame(signals)
