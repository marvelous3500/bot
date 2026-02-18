"""Unit tests for Kingsley Gold strategy."""
import pandas as pd
import pytest
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_ohlcv(base_ts, n_bars, base_price=2650):
    """Create minimal OHLCV DataFrame."""
    data = []
    for i in range(n_bars):
        ts = base_ts + timedelta(hours=i)
        o = base_price + i * 0.5
        h = o + 2
        l = o - 2
        c = o + 1
        data.append({'open': o, 'high': h, 'low': l, 'close': c, 'volume': 100})
    index = pd.DatetimeIndex([base_ts + timedelta(hours=i) for i in range(n_bars)])
    return pd.DataFrame(data, index=index)


@pytest.fixture
def minimal_kingsley_dfs():
    """Minimal 4H, H1, 15m DataFrames for Kingsley strategy."""
    base = datetime(2025, 1, 1, 7, 0, 0)  # London kill zone
    df_4h = _make_ohlcv(base, 50, 2640)
    df_h1 = _make_ohlcv(base, 200, 2645)
    df_15m = _make_ohlcv(base, 800, 2650)
    df_daily = _make_ohlcv(base, 60, 2630)
    return df_4h, df_h1, df_15m, df_daily


def test_kingsley_prepare_data_and_run_backtest(minimal_kingsley_dfs):
    """KingsleyGoldStrategy prepare_data and run_backtest return valid structure."""
    from bot.strategies import KingsleyGoldStrategy

    df_4h, df_h1, df_15m, df_daily = minimal_kingsley_dfs
    strat = KingsleyGoldStrategy(df_4h, df_h1, df_15m, df_daily=df_daily, verbose=False)
    df_4h_p, df_h1_p, df_15m_p = strat.prepare_data()
    assert df_4h_p is not None and not df_4h_p.empty
    assert df_h1_p is not None and not df_h1_p.empty
    assert df_15m_p is not None and not df_15m_p.empty
    assert 'swing_high' in df_h1_p.columns
    assert 'bos_bull' in df_h1_p.columns

    signals = strat.run_backtest()
    assert isinstance(signals, pd.DataFrame)
    if not signals.empty:
        assert 'time' in signals.columns
        assert 'type' in signals.columns
        assert 'price' in signals.columns
        assert 'sl' in signals.columns
        for _, row in signals.iterrows():
            if row['type'] == 'BUY':
                assert float(row['sl']) < float(row['price']), "BUY must have sl < price"
            elif row['type'] == 'SELL':
                assert float(row['sl']) > float(row['price']), "SELL must have sl > price"


def test_kingsley_empty_frames_returns_empty():
    """Empty input DataFrames return empty signals."""
    from bot.strategies import KingsleyGoldStrategy

    empty = pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
    strat = KingsleyGoldStrategy(empty, empty, empty, df_daily=None, verbose=False)
    signals = strat.run_backtest()
    assert signals.empty
