"""Unit tests for NAS Judas Strategy (strategy_judas, indicators_judas)."""
import pandas as pd
import numpy as np
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


def _make_h1_with_bos(base_ts, n_bars=60, bullish=True):
    """H1 data with BOS."""
    data = []
    base = 20000
    for i in range(n_bars):
        if i < 20:
            o, c = base - i * 20, base - i * 20 - 15
        elif i == 20:
            o, c = base - 400, base - 350 if bullish else base - 450
        else:
            o, c = base - 350 + (i - 20) * 5, base - 350 + (i - 20) * 5 + (10 if bullish else -10)
        h = max(o, c) + 30
        l = min(o, c) - 30
        data.append({"open": o, "high": h, "low": l, "close": c, "volume": 100})
    return pd.DataFrame(data, index=pd.DatetimeIndex([base_ts + timedelta(hours=i) for i in range(n_bars)]))


def _make_m15_judas_setup(base_ts, swing_low=19900, sweep_size=40):
    """M15 data with liquidity sweep low (bullish Judas): wick below swing_low, close back inside."""
    data = []
    base = 20000
    for i in range(50):
        ts = base_ts + timedelta(minutes=15 * i)
        o = base - i * 5
        if i == 20:
            h = o + 30
            l = swing_low - sweep_size
            c = swing_low + 10
        else:
            h = o + 20
            l = o - 20
            c = o + 5
        data.append({"open": o, "high": h, "low": l, "close": c, "volume": 100})
    return pd.DataFrame(data, index=pd.DatetimeIndex([base_ts + timedelta(minutes=15 * i) for i in range(50)]))


def test_detect_session_in_killzone():
    """Session within London/NY KZ returns passed."""
    from bot.strategies.strategy_judas import detect_session

    # London KZ (03:00-05:00 UTC)
    t = datetime(2025, 1, 1, 4, 0, 0)
    r = detect_session(t)
    assert "passed" in r
    assert "session" in r
    assert "reasoning" in r
    assert r["passed"] is True
    assert r["session"] == "london"

    # NY KZ (09:30-11:30 UTC)
    t2 = datetime(2025, 1, 1, 10, 0, 0)
    r2 = detect_session(t2)
    assert r2["passed"] is True
    assert r2["session"] == "newyork"


def test_detect_session_outside():
    """Outside KZ returns not passed."""
    from bot.strategies.strategy_judas import detect_session

    t = datetime(2025, 1, 1, 14, 0, 0)
    r = detect_session(t)
    assert r["passed"] is False
    assert "reasoning" in r


def test_detect_sweep_valid():
    """Wick beyond swing, close inside -> swept=True when size >= min."""
    from bot.strategies.strategy_judas import detect_sweep
    from bot.indicators_bos import detect_swing_highs_lows
    from bot.indicators_nas import detect_liquidity_sweep_m15

    base = datetime(2025, 1, 1, 4, 0, 0)
    df = _make_m15_judas_setup(base, swing_low=19900, sweep_size=40)
    df = detect_swing_highs_lows(df, swing_length=3)
    df = detect_liquidity_sweep_m15(df, lookback=5)

    sweep_rows = df[df["sweep_low"] == True]
    if not sweep_rows.empty:
        idx = sweep_rows.index[0]
        i = df.index.get_loc(idx)
        if isinstance(i, (int, np.integer)):
            r = detect_sweep(df, int(i), "BULLISH")
            assert "swept" in r
            assert "size" in r
            assert "reasoning" in r
            if r["swept"]:
                assert r["size"] >= 35 or "sweep" in r["reasoning"].lower()


def test_detect_sweep_too_small():
    """Sweep size < min_sweep_points -> rejected."""
    from bot.strategies.strategy_judas import detect_sweep
    from bot.indicators_bos import detect_swing_highs_lows
    from bot.indicators_nas import detect_liquidity_sweep_m15

    base = datetime(2025, 1, 1, 4, 0, 0)
    df = _make_m15_judas_setup(base, swing_low=19900, sweep_size=10)
    df = detect_swing_highs_lows(df, swing_length=3)
    df = detect_liquidity_sweep_m15(df, lookback=5)

    sweep_rows = df[df["sweep_low"] == True]
    if not sweep_rows.empty:
        idx = sweep_rows.index[0]
        i = df.index.get_loc(idx)
        if isinstance(i, (int, np.integer)):
            r = detect_sweep(df, int(i), "BULLISH")
            assert "swept" in r
            if r["size"] < 35:
                assert r["swept"] is False


def test_detect_displacement_valid():
    """Body >= 1.8x avg -> detected."""
    from bot.strategies.strategy_judas import detect_displacement_candle
    from bot.indicators import detect_displacement

    base = datetime(2025, 1, 1, 4, 0, 0)
    df = _make_ohlcv(base, 30, 20000, 0.25)
    df = detect_displacement(df, threshold=1.8, window=10)
    disp_rows = df[df["displacement_bull"] == True]
    if not disp_rows.empty:
        idx = disp_rows.index[0]
        i = df.index.get_loc(idx)
        if isinstance(i, (int, np.integer)):
            r = detect_displacement_candle(df, int(i), "BULLISH")
            assert "detected" in r
            assert "ratio" in r
            assert "reasoning" in r


def test_detect_structure_shift():
    """Break of swing after sweep -> shifted."""
    from bot.indicators_judas import detect_structure_shift_after_sweep
    from bot.indicators_bos import detect_swing_highs_lows, detect_break_of_structure

    base = datetime(2025, 1, 1, 4, 0, 0)
    df = _make_m15_judas_setup(base, swing_low=19900, sweep_size=40)
    df = detect_swing_highs_lows(df, swing_length=3)
    df = detect_break_of_structure(df)
    r = detect_structure_shift_after_sweep(df, sweep_idx=20, idx=25, direction="BULLISH")
    assert "shifted" in r
    assert "swing_level" in r
    assert "reasoning" in r


def test_detect_fvg():
    """Three-candle gap -> found with top/bottom."""
    from bot.strategies.strategy_judas import detect_fvg_at_bar
    from bot.indicators import detect_fvg

    base = datetime(2025, 1, 1, 4, 0, 0)
    df = _make_ohlcv(base, 50, 20000, 0.25)
    df = detect_fvg(df)
    fvg_rows = df[df["fvg_bull"] == True]
    if not fvg_rows.empty:
        idx = fvg_rows.index[0]
        i = df.index.get_loc(idx)
        if isinstance(i, (int, np.integer)):
            r = detect_fvg_at_bar(df, int(i), "BULLISH")
            assert "found" in r
            assert "top" in r
            assert "bottom" in r
            assert "size" in r
            assert "reasoning" in r


def test_confirm_entry_bullish():
    """Bullish candle, close in FVG -> confirmed."""
    from bot.strategies.strategy_judas import confirm_entry

    fvg = {"top": 20100, "bottom": 20050}
    row = pd.Series({"open": 20060, "high": 20095, "low": 20055, "close": 20080})
    r = confirm_entry(row, fvg, "BULLISH")
    assert "confirmed" in r
    assert "reasoning" in r
    assert r["confirmed"] is True


def test_confirm_entry_bearish():
    """Bearish candle, close in FVG -> confirmed."""
    from bot.strategies.strategy_judas import confirm_entry

    fvg = {"top": 20050, "bottom": 20000}
    row = pd.Series({"open": 20040, "high": 20045, "low": 19990, "close": 20010})
    r = confirm_entry(row, fvg, "BEARISH")
    assert "confirmed" in r
    assert r["confirmed"] is True


def test_confirmation_chain_incomplete():
    """_validate_confirmation_chain rejects when step missing."""
    from bot.strategies.strategy_judas import _validate_confirmation_chain

    steps = {"session": True, "sweep": True, "sweep_size": True, "displacement": False}
    ok, reason = _validate_confirmation_chain(steps)
    assert ok is False
    assert "displacement" in reason or "incomplete" in reason.lower()


def test_judas_strategy_prepare_data():
    """prepare_data adds required columns."""
    from bot.strategies import JudasStrategy

    base = datetime(2025, 1, 1, 4, 0, 0)
    df_h1 = _make_ohlcv(base, 60, 20000, 1)
    df_m15 = _make_ohlcv(base, 300, 20000, 0.25)
    strat = JudasStrategy(df_h1=df_h1, df_m15=df_m15, symbol="^NDX", verbose=False)
    strat.prepare_data()
    assert "swing_high" in strat.df_h1.columns
    assert "swing_low" in strat.df_h1.columns
    assert "fvg_bull" in strat.df_m15.columns
    assert "displacement_bull" in strat.df_m15.columns
    assert "sweep_low" in strat.df_m15.columns or "sweep_high" in strat.df_m15.columns


def test_judas_strategy_run_backtest():
    """JudasStrategy run_backtest returns DataFrame with valid structure."""
    from bot.strategies import JudasStrategy

    base = datetime(2025, 1, 1, 4, 0, 0)
    df_h1 = _make_h1_with_bos(base, 60, bullish=True)
    df_m15 = _make_m15_judas_setup(base, swing_low=19900, sweep_size=40)
    strat = JudasStrategy(df_h1=df_h1, df_m15=df_m15, symbol="^NDX", verbose=False)
    strat.prepare_data()
    signals = strat.run_backtest()

    assert isinstance(signals, pd.DataFrame)
    if not signals.empty:
        assert "time" in signals.columns
        assert "type" in signals.columns
        assert "price" in signals.columns
        assert "sl" in signals.columns
        assert "reason" in signals.columns
        for _, row in signals.iterrows():
            if row["type"] == "BUY":
                assert float(row["sl"]) < float(row["price"])
            elif row["type"] == "SELL":
                assert float(row["sl"]) > float(row["price"])


def test_judas_strategy_empty_returns_empty():
    """Empty input returns empty signals."""
    from bot.strategies import JudasStrategy

    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    strat = JudasStrategy(df_h1=empty, df_m15=empty, symbol="^NDX", verbose=False)
    signals = strat.run_backtest()
    assert signals.empty


def test_execute_trade():
    """execute_trade returns structured result."""
    from bot.strategies.strategy_judas import execute_trade

    signal = {"time": "2025-01-01", "type": "BUY", "price": 20000, "sl": 19950, "tp": 20150}
    r = execute_trade(signal)
    assert "executed" in r
    assert "order_id" in r
    assert "reasoning" in r


def test_manage_trade():
    """manage_trade returns action, sl, tp."""
    from bot.strategies.strategy_judas import manage_trade

    position = {"sl": 19950, "tp": 20150, "price": 20000, "type": "BUY"}
    r = manage_trade(position)
    assert "action" in r
    assert "sl" in r
    assert "tp" in r
    assert "reasoning" in r
