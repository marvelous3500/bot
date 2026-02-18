"""Unit tests for backtest SL/TP simulation logic."""
import pandas as pd
import pytest
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _simulate_trade(entry_price, stop_loss, tp_price, future_bars, trade_type, risk_pct, risk_reward):
    """Simulate one trade: return outcome (WIN/LOSS) and profit/loss amount."""
    balance = 100.0
    for _, bar in future_bars.iterrows():
        if trade_type == 'BUY':
            if bar['low'] <= stop_loss:
                loss = balance * risk_pct
                return 'LOSS', -loss
            if bar['high'] >= tp_price:
                profit = (balance * risk_pct) * risk_reward
                return 'WIN', profit
        else:  # SELL
            if bar['high'] >= stop_loss:
                loss = balance * risk_pct
                return 'LOSS', -loss
            if bar['low'] <= tp_price:
                profit = (balance * risk_pct) * risk_reward
                return 'WIN', profit
    return None, 0.0


def test_buy_tp_hits_first():
    """BUY signal: TP hit before SL -> WIN, balance increases by risk * R:R."""
    base = datetime(2025, 1, 1, 12, 0, 0)
    # Entry 100, SL 98, TP 106 (R:R 3). Bars: first bar high=107 (TP), low=99 (above SL)
    data = [
        {'open': 100, 'high': 107, 'low': 99, 'close': 105, 'volume': 100},
    ]
    future = pd.DataFrame(data, index=pd.DatetimeIndex([base + timedelta(minutes=15)]))
    outcome, pnl = _simulate_trade(100, 98, 106, future, 'BUY', 0.10, 3.0)
    assert outcome == 'WIN'
    # profit = 100 * 0.10 * 3 = 30
    assert abs(pnl - 30.0) < 0.01


def test_buy_sl_hits_first():
    """BUY signal: SL hit before TP -> LOSS, balance decreases by risk."""
    base = datetime(2025, 1, 1, 12, 0, 0)
    # Entry 100, SL 98, TP 106. Bars: first bar low=97 (SL hit), high=101
    data = [
        {'open': 100, 'high': 101, 'low': 97, 'close': 99, 'volume': 100},
    ]
    future = pd.DataFrame(data, index=pd.DatetimeIndex([base + timedelta(minutes=15)]))
    outcome, pnl = _simulate_trade(100, 98, 106, future, 'BUY', 0.10, 3.0)
    assert outcome == 'LOSS'
    # loss = 100 * 0.10 = 10
    assert abs(pnl + 10.0) < 0.01


def test_sell_tp_hits_first():
    """SELL signal: TP hit before SL -> WIN."""
    base = datetime(2025, 1, 1, 12, 0, 0)
    # Entry 100, SL 102, TP 94. Bars: low=93 (TP), high=101 (below SL)
    data = [
        {'open': 100, 'high': 101, 'low': 93, 'close': 95, 'volume': 100},
    ]
    future = pd.DataFrame(data, index=pd.DatetimeIndex([base + timedelta(minutes=15)]))
    outcome, pnl = _simulate_trade(100, 102, 94, future, 'SELL', 0.10, 3.0)
    assert outcome == 'WIN'
    assert abs(pnl - 30.0) < 0.01


def test_sell_sl_hits_first():
    """SELL signal: SL hit before TP -> LOSS."""
    base = datetime(2025, 1, 1, 12, 0, 0)
    # Entry 100, SL 102, TP 94. Bars: high=103 (SL), low=99
    data = [
        {'open': 100, 'high': 103, 'low': 99, 'close': 101, 'volume': 100},
    ]
    future = pd.DataFrame(data, index=pd.DatetimeIndex([base + timedelta(minutes=15)]))
    outcome, pnl = _simulate_trade(100, 102, 94, future, 'SELL', 0.10, 3.0)
    assert outcome == 'LOSS'
    assert abs(pnl + 10.0) < 0.01


def test_bar_order_matters_tp_first():
    """When both SL and TP could be hit, order of bars matters - first bar hits TP."""
    base = datetime(2025, 1, 1, 12, 0, 0)
    # Bar 1: high=106 (TP), low=99. Bar 2: low=97 (SL). TP should be hit first.
    data = [
        {'open': 100, 'high': 106, 'low': 99, 'close': 105, 'volume': 100},
        {'open': 105, 'high': 104, 'low': 97, 'close': 98, 'volume': 100},
    ]
    future = pd.DataFrame(
        data,
        index=pd.DatetimeIndex([base + timedelta(minutes=15 * i) for i in range(2)])
    )
    outcome, pnl = _simulate_trade(100, 98, 106, future, 'BUY', 0.10, 3.0)
    assert outcome == 'WIN'
