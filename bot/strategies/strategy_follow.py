"""
FollowStrategy: simple trend-following test strategy.
Follows market direction (EMA crossover) for testing lot size, risk, and execution.
Use with: --strategy follow
"""
import pandas as pd
import numpy as np
from typing import Optional

import config
from .base import BaseStrategy


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


class FollowStrategy(BaseStrategy):
    """
    Simple trend-following: BUY when close crosses above EMA, SELL when below.
    For testing lot size calculation and execution flow.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        symbol: Optional[str] = None,
        ema_period: int = 20,
        sl_atr_mult: float = 2.0,
        verbose: bool = False,
    ):
        self.df = df.copy() if df is not None and not df.empty else df
        self.symbol = symbol
        self.ema_period = ema_period
        self.sl_atr_mult = sl_atr_mult
        self.verbose = verbose

    def prepare_data(self) -> pd.DataFrame:
        """Add EMA and ATR."""
        if self.df is None or self.df.empty:
            return self.df
        self.df["ema"] = self.df["close"].ewm(span=self.ema_period, adjust=False).mean()
        self.df["atr"] = _atr(self.df, 14)
        return self.df

    def run_backtest(self) -> pd.DataFrame:
        """
        Emit BUY when close crosses above EMA, SELL when below.
        SL = ATR-based. TP = RR from config.
        """
        if self.df is None or self.df.empty or len(self.df) < self.ema_period + 5:
            return pd.DataFrame()

        df = self.df
        rr = getattr(config, "RISK_REWARD_RATIO", 5.0)
        signals = []

        prev_above = float(df.iloc[self.ema_period]["close"]) > float(df.iloc[self.ema_period]["ema"])
        for i in range(self.ema_period + 1, len(df)):
            row = df.iloc[i]
            close = float(row["close"])
            ema = float(row["ema"])
            atr_val = float(row["atr"]) if not pd.isna(row["atr"]) and row["atr"] > 0 else (row["high"] - row["low"]) * 2
            sl_dist = atr_val * self.sl_atr_mult

            above = close > ema

            if above and prev_above is False:
                # Bullish crossover
                entry = close
                sl = entry - sl_dist
                tp = entry + sl_dist * rr
                sig = {
                    "time": df.index[i],
                    "type": "BUY",
                    "price": entry,
                    "sl": sl,
                    "tp": tp,
                    "reason": f"Follow: close crossed above EMA{self.ema_period}",
                }
                sig["setup_5m"] = df.index[i]
                signals.append(sig)
            elif not above and prev_above is True:
                # Bearish crossover
                entry = close
                sl = entry + sl_dist
                tp = entry - sl_dist * rr
                sig = {
                    "time": df.index[i],
                    "type": "SELL",
                    "price": entry,
                    "sl": sl,
                    "tp": tp,
                    "reason": f"Follow: close crossed below EMA{self.ema_period}",
                }
                sig["setup_5m"] = df.index[i]
                signals.append(sig)
            prev_above = above  # for next iteration

        return pd.DataFrame(signals)
