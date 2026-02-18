#!/usr/bin/env python3
"""
Parameter sweep for Kingsley Gold strategy.
Runs backtests with different config values and prints results side by side.
Fetches data once and reuses for all runs.
"""
import sys
import os

# Add project root for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from bot.data_loader import fetch_data_yfinance
from bot.backtest.backtest_kingsley import run_kingsley_backtest

AGG = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}


def fetch_data(symbol=None, period=None):
    """Fetch data once for reuse."""
    symbol = symbol or getattr(config, 'KINGSLEY_BACKTEST_SYMBOL', 'GC=F')
    period = period or getattr(config, 'BACKTEST_PERIOD', '60d')
    use_60d = period in ('6mo', '180d') or (isinstance(period, str) and ('mo' in period.lower() or 'y' in period.lower()))
    fetch_period = '60d' if use_60d else period
    df_h1 = fetch_data_yfinance(symbol, period=fetch_period, interval='1h')
    df_4h = df_h1.resample('4h').agg(AGG).dropna()
    df_15m = fetch_data_yfinance(symbol, period=fetch_period, interval='15m')
    df_daily = df_h1.resample('1D').agg(AGG).dropna()
    # Strip timezone for consistency
    for df in (df_4h, df_h1, df_15m, df_daily):
        if df.index.tz is not None:
            df.index = df.index.tz_convert(None)
    return df_4h, df_h1, df_15m, df_daily


def run_with_overrides(overrides, df_4h, df_h1, df_15m, df_daily):
    """Apply config overrides, run backtest, restore config. Returns stats dict."""
    saved = {}
    for key, val in overrides.items():
        if hasattr(config, key):
            saved[key] = getattr(config, key)
        setattr(config, key, val)
    try:
        stats = run_kingsley_backtest(
            return_stats=True,
            df_4h=df_4h, df_h1=df_h1, df_15m=df_15m, df_daily=df_daily,
        )
        return stats
    finally:
        for key in saved:
            setattr(config, key, saved[key])


def main():
    symbol = getattr(config, 'KINGSLEY_BACKTEST_SYMBOL', 'GC=F')
    period = getattr(config, 'BACKTEST_PERIOD', '60d')
    print(f"Fetching data for {symbol} ({period})...")
    df_4h, df_h1, df_15m, df_daily = fetch_data(symbol, period)
    print("Data loaded. Running parameter sweep...\n")

    # Param sets: (label, overrides)
    param_sets = [
        ("Base (config)", {}),
        ("Aggressive (swing2+disp0.5)", {"KINGSLEY_AGGRESSIVE": True}),
        ("disp=0.5", {"KINGSLEY_DISPLACEMENT_RATIO": 0.5}),
        ("disp=0.7", {"KINGSLEY_DISPLACEMENT_RATIO": 0.7}),
        ("no Asian", {"KINGSLEY_USE_ASIAN_SESSION": False}),
        ("4H filter", {"USE_4H_BIAS_FILTER": True}),
        ("swing=5", {"KINGSLEY_SWING_LENGTH": 5}),
        ("swing=2", {"KINGSLEY_SWING_LENGTH": 2}),
        ("liq=3", {"KINGSLEY_LIQ_SWEEP_LOOKBACK": 3}),
        ("liq=7", {"KINGSLEY_LIQ_SWEEP_LOOKBACK": 7}),
        ("tp=1", {"KINGSLEY_TP_SWING_LOOKAHEAD": 1}),
        ("tp=5", {"KINGSLEY_TP_SWING_LOOKAHEAD": 5}),
        ("window=4h", {"KINGSLEY_15M_WINDOW_HOURS": 4}),
        ("window=12h", {"KINGSLEY_15M_WINDOW_HOURS": 12}),
    ]

    results = []
    for label, overrides in param_sets:
        stats = run_with_overrides(overrides, df_4h, df_h1, df_15m, df_daily)
        results.append((label, stats))

    # Print side-by-side table
    print("=" * 120)
    print("Kingsley Gold Parameter Sweep — Results")
    print("=" * 120)
    header = f"{'Config':<18} | {'Trades':>6} | {'Wins':>4} | {'Loss':>4} | {'Win%':>6} | {'Final $':>14} | {'Return':>12}"
    print(header)
    print("-" * 120)
    for label, s in results:
        wr = f"{s['win_rate']:.1f}%" if s['trades'] else "—"
        ret = f"{s['return_pct']:+,.1f}%" if s['trades'] else "—"
        print(f"{label:<18} | {s['trades']:>6} | {s['wins']:>4} | {s['losses']:>4} | {wr:>6} | ${s['final_balance']:>12,.2f} | {ret:>12}")
    print("=" * 120)
    print(f"\nAsset: {symbol} | Period: {period} | Risk: {config.RISK_PER_TRADE*100:.0f}% | R:R 1:{config.RISK_REWARD_RATIO}")


if __name__ == "__main__":
    main()
