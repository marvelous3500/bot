#!/usr/bin/env python3
"""
Parameter sweep for H1-M5 BOS strategy.
Runs backtests with different config values and prints results side by side.
Fetches data once and reuses for all runs.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from bot.data_loader import fetch_data_yfinance
from bot.backtest.backtest_bos import run_bos_backtest


def fetch_data(symbol=None, period=None):
    """Fetch data once for reuse."""
    symbol = symbol or config.SYMBOLS[0]
    period = period or getattr(config, 'BACKTEST_PERIOD', '60d')
    print(f"Fetching data for {symbol} ({period})...")
    df_h1 = fetch_data_yfinance(symbol, period=period, interval='1h')
    df_m5 = fetch_data_yfinance(symbol, period=period, interval='5m')
    if df_h1.index.tz is not None:
        df_h1.index = df_h1.index.tz_convert(None)
    if df_m5.index.tz is not None:
        df_m5.index = df_m5.index.tz_convert(None)
    return df_h1, df_m5


def run_with_overrides(overrides, df_h1, df_m5):
    """Apply config overrides, run backtest, restore config. Returns stats dict."""
    saved = {}
    for key, val in overrides.items():
        if hasattr(config, key):
            saved[key] = getattr(config, key)
        setattr(config, key, val)
    try:
        stats = run_bos_backtest(
            return_stats=True,
            df_h1=df_h1,
            df_m5=df_m5,
        )
        return stats
    finally:
        for key in saved:
            setattr(config, key, saved[key])


def main():
    symbol = config.SYMBOLS[0]
    period = getattr(config, 'BACKTEST_PERIOD', '60d')
    df_h1, df_m5 = fetch_data(symbol, period)
    print("Data loaded. Running parameter sweep...\n")

    # Param sets: (label, overrides)
    param_sets = [
        ("Base (config)", {}),
        ("No EMA filter", {"BOS_USE_EMA_FILTER": False}),
        ("No kill zones", {"BOS_USE_KILL_ZONES": False}),
        ("disp=0.5", {"BOS_DISPLACEMENT_RATIO": 0.5}),
        ("disp=0.6", {"BOS_DISPLACEMENT_RATIO": 0.6}),
        ("disp=0.8", {"BOS_DISPLACEMENT_RATIO": 0.8}),
        ("window=4h", {"BOS_M5_WINDOW_HOURS": 4}),
        ("window=6h", {"BOS_M5_WINDOW_HOURS": 6}),
        ("4H filter", {"USE_4H_BIAS_FILTER": True}),
        ("EMA + strict disp", {"BOS_USE_EMA_FILTER": True, "BOS_DISPLACEMENT_RATIO": 0.8}),
        ("No EMA + disp=0.5", {"BOS_USE_EMA_FILTER": False, "BOS_DISPLACEMENT_RATIO": 0.5}),
        ("No kill + disp=0.6", {"BOS_USE_KILL_ZONES": False, "BOS_DISPLACEMENT_RATIO": 0.6}),
    ]

    results = []
    for label, overrides in param_sets:
        stats = run_with_overrides(overrides, df_h1, df_m5)
        results.append((label, stats))

    # Sort by win rate (desc), then by return (desc)
    results.sort(key=lambda x: (x[1]['win_rate'] if x[1]['trades'] else 0, x[1]['return_pct']), reverse=True)

    # Print side-by-side table
    print("=" * 120)
    print("H1-M5 BOS Parameter Sweep — Results (sorted by win rate, then return)")
    print("=" * 120)
    header = f"{'Config':<22} | {'Trades':>6} | {'Wins':>4} | {'Loss':>4} | {'Win%':>6} | {'Final $':>14} | {'Return':>12}"
    print(header)
    print("-" * 120)
    for label, s in results:
        wr = f"{s['win_rate']:.1f}%" if s['trades'] else "—"
        ret = f"{s['return_pct']:+,.1f}%" if s['trades'] else "—"
        print(f"{label:<22} | {s['trades']:>6} | {s['wins']:>4} | {s['losses']:>4} | {wr:>6} | ${s['final_balance']:>12,.2f} | {ret:>12}")
    print("=" * 120)
    print(f"\nAsset: {symbol} | Period: {period} | Risk: {config.RISK_PER_TRADE*100:.0f}% | R:R 1:{config.RISK_REWARD_RATIO}")
    print("\nBest config for win rate is at top. Apply winning overrides to config.py to use.")


if __name__ == "__main__":
    main()
