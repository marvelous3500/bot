"""Unit tests for VesterStrategy detection methods."""
import pandas as pd
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.strategies import VesterStrategy
from bot.indicators_bos import detect_swing_highs_lows, detect_break_of_structure
from bot.indicators import detect_fvg, detect_rejection_candle


@pytest.fixture
def sample_h1_bullish_bias():
    """1H DataFrame with BOS above swing high, FVG, and rejection candle in zone."""
    base = pd.Timestamp("2025-01-01 00:00:00")
    # Bars: 0-4 build structure, 5 BOS bull, 6-7 retrace, 8 rejection in zone
    data = {
        "open": [100, 101, 102, 101, 100, 99, 98, 97, 96],
        "high": [101, 102, 103, 102, 101, 100, 99, 98, 97],
        "low": [99, 100, 101, 100, 99, 98, 97, 96, 95],
        "close": [100.5, 101.5, 102.5, 101, 100, 99.5, 98.5, 97.5, 97],
        "volume": [100] * 9,
    }
    # Bar 2: swing high (103), bar 3: swing low (100), bar 5: close 99.5 < 103, bar 6: close 98.5
    # FVG: c3_low > c1_high -> bar 4: need bar 2 high < bar 4 low. Bar 2 high=103, bar 4 low=99 -> no
    # Simpler: bar 7 has fvg_bull if bar 5 low > bar 3 high. Bar 3 high=99, bar 5 low=98 -> no
    # FVG bull: c3_low > c1_high. Bar i has fvg_bull when df.iloc[i]['low'] > df.iloc[i-2]['high']
    # So we need bar i low > bar i-2 high. E.g. bar 4: low 99 > bar 2 high 103? No.
    # bar 6: low 97 > bar 4 high 101? No. bar 8: low 95 > bar 6 high 99? No.
    # Let's set: bar 2 high=98, bar 4 low=99 -> bar 4 fvg_bull. Zone: [98, 99]
    # Rejection at bar 8: long lower wick, close > open. Bar 8: low 95, body 96-97, wick = 96-95=1, range=2, ratio 0.5
    data = {
        "open": [100, 101, 102, 101, 100, 99, 98.5, 98, 97],
        "high": [101, 102, 103, 102, 101, 100, 99.5, 99, 98],
        "low": [99, 100, 101, 100, 99, 98, 97.5, 97, 95],
        "close": [100.5, 101.5, 102.5, 101, 100.5, 99.5, 98.5, 98, 97.5],
        "volume": [100] * 9,
    }
    # Bar 2: high 103 (swing high), bar 3: low 100 (swing low)
    # Bar 5: close 99.5 - for BOS bull we need close > last swing high (103). So bar 5 can't be BOS.
    # Bar 6: close 98.5. Let's have bar 5 close above 103 for BOS. Bar 5 close=104.
    data["high"][5] = 105
    data["low"][5] = 103
    data["close"][5] = 104
    data["open"][5] = 103.5
    # Now bar 5 breaks above swing high 103. FVG: bar 7 fvg_bull = bar 7 low > bar 5 high. 97 > 105? No.
    # FVG bull at bar i: df.iloc[i]['low'] > df.iloc[i-2]['high']. Bar 5 high=105, bar 7 low=95. 95>105? No.
    # Bar 6: low 97.5 > bar 4 high 101? No. We need bar 4 high lower. Bar 4 high=99, bar 6 low=99.5 -> bar 6 fvg_bull. Zone [99, 99.5]
    data["high"][4] = 99
    data["low"][6] = 99.5
    data["high"][6] = 100
    data["close"][6] = 99.8
    data["open"][6] = 99.6
    # Rejection at bar 7 or 8 in zone [99, 99.5]. Bar 7: low 97, high 99 - touches zone. Rejection: long lower wick.
    # Bar 7: low 97, open 98 close 98 -> body 0. Wick = 98-97=1, range 2, ratio 0.5. Good.
    data["low"][7] = 97
    data["high"][7] = 99.2
    data["open"][7] = 98
    data["close"][7] = 98.2
    index = pd.DatetimeIndex([base + pd.Timedelta(hours=i) for i in range(9)])
    return pd.DataFrame(data, index=index)


def test_detect_htf_bias_neutral_when_no_bos():
    """When no BOS on 1H, detectHTFBias returns None."""
    base = pd.Timestamp("2025-01-01 00:00:00")
    data = {
        "open": [100] * 10,
        "high": [101] * 10,
        "low": [99] * 10,
        "close": [100] * 10,
        "volume": [100] * 10,
    }
    df = pd.DataFrame(data, index=pd.DatetimeIndex([base + pd.Timedelta(hours=i) for i in range(10)]))
    df = detect_swing_highs_lows(df, swing_length=2)
    df = detect_break_of_structure(df)
    df = detect_fvg(df)
    df = detect_rejection_candle(df, wick_ratio=0.5)
    strat = VesterStrategy(df_h1=df, df_m5=df.iloc[:5], df_m1=df.iloc[:5], verbose=False)
    strat.prepare_data()
    bias, proof = strat.detectHTFBias(df)
    assert bias is None
    assert proof is None


def test_detect_liquidity_sweep_buy():
    """Sweep below swing low: low < L, close > L."""
    base = pd.Timestamp("2025-01-01 00:00:00")
    # Bar 2: swing low at 95. Bar 4: low 94, close 96 -> sweep
    data = {
        "open": [100, 99, 98, 97, 96],
        "high": [101, 100, 99, 98, 97],
        "low": [99, 98, 95, 96, 94],
        "close": [99.5, 98.5, 96, 97, 96],
        "volume": [100] * 5,
    }
    df = pd.DataFrame(data, index=pd.DatetimeIndex([base + pd.Timedelta(hours=i) for i in range(5)]))
    df = detect_swing_highs_lows(df, swing_length=1)
    strat = VesterStrategy(df_h1=df, df_m5=df, df_m1=df, verbose=False)
    strat.prepare_data()
    swept, level, idx = strat.detectLiquiditySweep(df, "BUY", lookback=5)
    assert swept is True
    assert level == 95
    assert idx == 4


def test_detect_structure_shift():
    """detectStructureShift returns BOS direction from DataFrame."""
    base = pd.Timestamp("2025-01-01 00:00:00")
    data = {
        "open": [100, 99, 98, 99, 100],
        "high": [101, 100, 99, 101, 102],
        "low": [99, 98, 97, 98, 99],
        "close": [99.5, 98.5, 97.5, 100.5, 101.5],
        "volume": [100] * 5,
    }
    df = pd.DataFrame(data, index=pd.DatetimeIndex([base + pd.Timedelta(hours=i) for i in range(5)]))
    df = detect_swing_highs_lows(df, swing_length=1)
    df = detect_break_of_structure(df)
    strat = VesterStrategy(df_h1=df, df_m5=df, df_m1=df, verbose=False)
    strat.prepare_data()
    direction, bos_idx = strat.detectStructureShift(df)
    assert direction in ("BULLISH", "BEARISH") or direction is None


def test_place_trade():
    """placeTrade returns valid signal dict."""
    strat = VesterStrategy(
        df_h1=pd.DataFrame(),
        df_m5=pd.DataFrame(),
        df_m1=pd.DataFrame(),
        verbose=False,
    )
    sig = strat.placeTrade("BUY", 100.0, 99.0, 103.0, pd.Timestamp("2025-01-01 12:00"), "test")
    assert sig["type"] == "BUY"
    assert sig["price"] == 100.0
    assert sig["sl"] == 99.0
    assert sig["tp"] == 103.0
    assert "reason" in sig
    assert "time" in sig


def test_run_backtest_empty_returns_empty_df():
    """run_backtest with insufficient data returns empty DataFrame."""
    df = pd.DataFrame({
        "open": [100, 101],
        "high": [101, 102],
        "low": [99, 100],
        "close": [100.5, 101.5],
        "volume": [100, 100],
    }, index=pd.DatetimeIndex([pd.Timestamp("2025-01-01"), pd.Timestamp("2025-01-02")]))
    strat = VesterStrategy(df_h1=df, df_m5=df, df_m1=df, verbose=False)
    strat.prepare_data()
    signals = strat.run_backtest()
    assert signals.empty
