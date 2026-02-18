#!/usr/bin/env python3
"""
Run Kingsley backtest with Kingsley (fractal) vs LuxAlgo (pivot) ICT indicators.
Prints results side by side for comparison.

Usage:
  python scripts/compare_kingsley_luxalgo.py
  python scripts/compare_kingsley_luxalgo.py --period 12d
  python scripts/compare_kingsley_luxalgo.py --csv path/to/data.csv
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from bot.backtest.backtest_kingsley import run_kingsley_backtest
from bot.data_loader import fetch_data_yfinance, load_data_csv


def _fetch_data(csv_path=None, period="60d"):
    """Fetch or load data, return (df_4h, df_h1, df_15m, df_daily)."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    if csv_path:
        df = load_data_csv(csv_path)
        df_h1 = df.resample("1h").agg(agg).dropna()
        df_4h = df_h1.resample("4h").agg(agg).dropna()
        df_15m = df.resample("15min").agg(agg).dropna()
        df_daily = df_h1.resample("1D").agg(agg).dropna()
    else:
        symbol = config.KINGSLEY_BACKTEST_SYMBOL
        use_60d = period in ("6mo", "180d") or ("mo" in str(period).lower() or "y" in str(period).lower())
        fetch_period = "60d" if use_60d else period
        df_h1 = fetch_data_yfinance(symbol, period=fetch_period, interval="1h")
        df_4h = df_h1.resample("4h").agg(agg).dropna()
        df_15m = fetch_data_yfinance(symbol, period=fetch_period, interval="15m")
        df_daily = df_h1.resample("1D").agg(agg).dropna()
    for df in (df_4h, df_h1, df_15m, df_daily):
        if df.index.tz is not None:
            df.index = df.index.tz_convert(None)
    return df_4h, df_h1, df_15m, df_daily


def run_with_ict_mode(use_luxalgo, csv_path=None, period=None, df_4h=None, df_h1=None, df_15m=None, df_daily=None):
    """Run backtest with given ICT mode, return stats dict."""
    config.USE_LUXALGO_ICT = use_luxalgo
    return run_kingsley_backtest(
        return_stats=True,
        csv_path=csv_path,
        symbol=config.KINGSLEY_BACKTEST_SYMBOL if not csv_path else None,
        period=period,
        df_4h=df_4h,
        df_h1=df_h1,
        df_15m=df_15m,
        df_daily=df_daily,
    )


def main():
    parser = argparse.ArgumentParser(description="Compare Kingsley vs LuxAlgo backtest")
    parser.add_argument("--period", default=None, help="Backtest period (e.g. 12d, 60d)")
    parser.add_argument("--csv", default=None, help="Path to CSV data (skips Yahoo fetch)")
    args = parser.parse_args()

    period = args.period or getattr(config, "BACKTEST_PERIOD", "60d")
    csv_path = args.csv

    print("Running Kingsley backtest: Kingsley (fractal) vs LuxAlgo (pivot)...")
    if csv_path:
        print(f"  Data: {csv_path}")
    else:
        print(f"  Symbol: {config.KINGSLEY_BACKTEST_SYMBOL}, Period: {period}")
    print()

    df_4h, df_h1, df_15m, df_daily = _fetch_data(csv_path=csv_path, period=period)

    stats_kingsley = run_with_ict_mode(
        False, df_4h=df_4h, df_h1=df_h1, df_15m=df_15m, df_daily=df_daily
    )
    stats_luxalgo = run_with_ict_mode(
        True, df_4h=df_4h, df_h1=df_h1, df_15m=df_15m, df_daily=df_daily
    )

    print()
    print("=" * 80)
    print("BACKTEST COMPARISON: Kingsley (fractal) vs LuxAlgo (pivot)")
    print("=" * 80)
    print()
    print(f"{'Metric':<22} | {'Kingsley (fractal)':>18} | {'LuxAlgo (pivot)':>18}")
    print("-" * 62)
    print(f"{'Trades':<22} | {stats_kingsley['trades']:>18} | {stats_luxalgo['trades']:>18}")
    print(f"{'Wins':<22} | {stats_kingsley['wins']:>18} | {stats_luxalgo['wins']:>18}")
    print(f"{'Losses':<22} | {stats_kingsley['losses']:>18} | {stats_luxalgo['losses']:>18}")
    print(f"{'Win rate':<22} | {stats_kingsley['win_rate']:>17.1f}% | {stats_luxalgo['win_rate']:>17.1f}%")
    print(f"{'Final balance':<22} | ${stats_kingsley['final_balance']:>16,.2f} | ${stats_luxalgo['final_balance']:>16,.2f}")
    ret_k = f"{'+' if stats_kingsley['return_pct'] >= 0 else ''}{stats_kingsley['return_pct']:.1f}%"
    ret_l = f"{'+' if stats_luxalgo['return_pct'] >= 0 else ''}{stats_luxalgo['return_pct']:.1f}%"
    print(f"{'Return':<22} | {ret_k:>18} | {ret_l:>18}")
    print("=" * 80)


if __name__ == "__main__":
    main()
