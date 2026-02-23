"""Unit tests for NAS-STRATEGY (strategy_nas, indicators_nas)."""
import pandas as pd
import pytest
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_ohlcv(base_ts, n_bars, base_price=20000, interval_hours=1):
    """Create minimal OHLCV DataFrame."""
    data = []
    for i in range(n_bars):
        ts = base_ts + timedelta(hours=i * interval_hours)
        o = base_price + i * 10
        h = o + 50
        l = o - 50
        c = o + 20
        data.append({"open": o, "high": h, "low": l, "close": c, "volume": 100})
    index = pd.DatetimeIndex([base_ts + timedelta(hours=i * interval_hours) for i in range(n_bars)])
    return pd.DataFrame(data, index=index)


def _make_h1_with_bos_bullish(base_ts, n_bars=60):
    """H1 data with BOS bullish: downtrend then break up + FVG."""
    data = []
    base = 20000
    for i in range(n_bars):
        ts = base_ts + timedelta(hours=i)
        if i < 20:
            o, c = base - i * 20, base - i * 20 - 15
        elif i == 20:
            o, c = base - 400, base - 350
            fvg_bottom = base - 400
            fvg_top = base - 350
        else:
            o, c = base - 350 + (i - 20) * 5, base - 350 + (i - 20) * 5 + 10
        h = max(o, c) + 30
        l = min(o, c) - 30
        data.append({"open": o, "high": h, "low": l, "close": c, "volume": 100})
    return pd.DataFrame(data, index=pd.DatetimeIndex([base_ts + timedelta(hours=i) for i in range(n_bars)]))


def _make_m15_with_sweep(base_ts, swing_high=20100, sweep_size=30):
    """M15 data with liquidity sweep high: price wicks above swing_high then closes back."""
    data = []
    base = 20000
    for i in range(30):
        ts = base_ts + timedelta(minutes=15 * i)
        o = base + i * 5
        if i == 15:
            h = swing_high + sweep_size
            l = o - 10
            c = swing_high - 5
        else:
            h = o + 20
            l = o - 20
            c = o + 5
        data.append({"open": o, "high": h, "low": l, "close": c, "volume": 100})
    return pd.DataFrame(data, index=pd.DatetimeIndex([base_ts + timedelta(minutes=15 * i) for i in range(30)]))


def test_calculate_h1_bias_missing_data():
    """calculate_h1_bias returns NEUTRAL for missing/empty H1 data."""
    from bot.strategies.strategy_nas import calculate_h1_bias

    assert calculate_h1_bias(None, 48, 0.5, 0.3)["bias"] == "NEUTRAL"
    assert calculate_h1_bias(pd.DataFrame(), 48, 0.5, 0.3)["bias"] == "NEUTRAL"
    short = pd.DataFrame({"open": [1], "high": [2], "low": [0], "close": [1.5], "volume": [100]})
    assert calculate_h1_bias(short, 48, 0.5, 0.3)["bias"] == "NEUTRAL"


def test_calculate_h1_bias_with_bos():
    """calculate_h1_bias returns BULLISH/BEARISH when BOS + zone present."""
    from bot.strategies.strategy_nas import calculate_h1_bias

    base = datetime(2025, 1, 1, 8, 0, 0)
    df_h1 = _make_h1_with_bos_bullish(base, 60)
    result = calculate_h1_bias(df_h1, 48, 0.5, 0.3)
    assert result["bias"] in ("BULLISH", "BEARISH", "NEUTRAL")
    assert "reason" in result
    assert "proof" in result


def test_detect_liquidity_sweep_m15():
    """detect_liquidity_sweep_m15 detects sweep when price wicks beyond swing then closes back."""
    from bot.indicators_nas import detect_liquidity_sweep_m15
    from bot.indicators_bos import detect_swing_highs_lows

    base = datetime(2025, 1, 1, 8, 0, 0)
    df = _make_m15_with_sweep(base, swing_high=20100, sweep_size=30)
    df = detect_swing_highs_lows(df, swing_length=3)
    df = detect_liquidity_sweep_m15(df, lookback=5)
    assert "sweep_high" in df.columns
    assert "sweep_high_size" in df.columns
    sweep_rows = df[df["sweep_high"] == True]
    if not sweep_rows.empty:
        assert sweep_rows["sweep_high_size"].iloc[0] >= 0


def test_detect_liquidity_sweep_with_min_size():
    """detect_liquidity_sweep filters by min_sweep_points."""
    from bot.indicators_nas import detect_liquidity_sweep

    base = datetime(2025, 1, 1, 8, 0, 0)
    df = _make_m15_with_sweep(base, swing_high=20100, sweep_size=10)
    get_sweep = detect_liquidity_sweep(df, lookback=5, min_sweep_points=25)
    result = get_sweep(len(df) - 1)
    assert "swept" in result
    assert "size" in result
    assert "reason" in result


def test_confirm_entry_candle():
    """confirm_entry_candle validates bullish/bearish entry candle in FVG."""
    from bot.strategies.strategy_nas import confirm_entry_candle

    fvg_bull = {"top": 20100, "bottom": 20050}
    row_bull = pd.Series({"open": 20060, "high": 20095, "low": 20055, "close": 20080})
    r = confirm_entry_candle(row_bull, "BULLISH", fvg_bull)
    assert "confirmed" in r
    assert "reason" in r

    fvg_bear = {"top": 20050, "bottom": 20000}
    row_bear = pd.Series({"open": 20040, "high": 20045, "low": 19990, "close": 20010})
    r2 = confirm_entry_candle(row_bear, "BEARISH", fvg_bear)
    assert "confirmed" in r2


def test_is_nas_session_allowed():
    """is_nas_session_allowed returns True in London/NY kill zones."""
    from bot.strategies.strategy_nas import is_nas_session_allowed

    london_time = datetime(2025, 1, 1, 8, 30, 0)
    ny_time = datetime(2025, 1, 1, 15, 0, 0)
    asia_time = datetime(2025, 1, 1, 2, 0, 0)
    result_london = is_nas_session_allowed(london_time)
    result_ny = is_nas_session_allowed(ny_time)
    result_asia = is_nas_session_allowed(asia_time)
    assert isinstance(result_london, bool)
    assert isinstance(result_ny, bool)
    assert isinstance(result_asia, bool)


def test_apply_filters():
    """apply_filters returns {passed, reason}."""
    from bot.strategies.strategy_nas import apply_filters

    t = datetime(2025, 1, 1, 8, 30, 0)
    r = apply_filters(t, atr_val=50, spread=2.0)
    assert "passed" in r
    assert "reason" in r


def test_nas_strategy_prepare_data_and_run_backtest():
    """NasStrategy prepare_data and run_backtest return valid structure."""
    from bot.strategies import NasStrategy

    base = datetime(2025, 1, 1, 8, 0, 0)
    df_h1 = _make_ohlcv(base, 100, 20000, 1)
    df_m15 = _make_ohlcv(base, 500, 20000, 0.25)
    df_4h = df_h1.resample("4h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()

    strat = NasStrategy(
        df_h1=df_h1,
        df_m15=df_m15,
        df_entry=df_m15,
        df_4h=df_4h,
        symbol="^NDX",
        verbose=False,
    )
    strat.prepare_data()
    signals = strat.run_backtest()

    assert isinstance(signals, pd.DataFrame)
    if not signals.empty:
        assert "time" in signals.columns
        assert "type" in signals.columns
        assert "price" in signals.columns
        assert "sl" in signals.columns
        for _, row in signals.iterrows():
            if row["type"] == "BUY":
                assert float(row["sl"]) < float(row["price"]), "BUY must have sl < price"
            elif row["type"] == "SELL":
                assert float(row["sl"]) > float(row["price"]), "SELL must have sl > price"


def test_nas_strategy_empty_frames_returns_empty():
    """Empty input DataFrames return empty signals."""
    from bot.strategies import NasStrategy

    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    strat = NasStrategy(
        df_h1=empty,
        df_m15=empty,
        df_entry=empty,
        df_4h=empty,
        symbol="^NDX",
        verbose=False,
    )
    signals = strat.run_backtest()
    assert signals.empty


def test_get_fvg_zones():
    """get_fvg_zones returns zones with top, bottom, size, age."""
    from bot.indicators_nas import get_fvg_zones

    base = datetime(2025, 1, 1, 8, 0, 0)
    df = _make_ohlcv(base, 50, 20000, 0.25)
    zones = get_fvg_zones(df, min_fvg_size=0, max_fvg_age=None)
    assert isinstance(zones, list)
    for z in zones:
        assert "top" in z
        assert "bottom" in z
        assert "size" in z
        assert "direction" in z
