#!/usr/bin/env python3
"""
Walk-forward analysis for strategy validation.
Splits data into train/test windows and runs backtest on each.
"""
import argparse
import sys
import os
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from bot.data_loader import fetch_data_yfinance
from bot.backtest.backtest_kingsley import run_kingsley_backtest
from bot.backtest.backtest_bos import run_bos_backtest

AGG = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}


def fetch_full_data(symbol, period='60d'):
    """Fetch data for walk-forward."""
    use_60d = period in ('6mo', '180d') or (isinstance(period, str) and ('mo' in period.lower() or 'y' in period.lower()))
    fetch_period = '60d' if use_60d else period
    if 'GC=' in str(symbol).upper() or 'XAU' in str(symbol).upper():
        df_h1 = fetch_data_yfinance(symbol, period=fetch_period, interval='1h')
        df_15m = fetch_data_yfinance(symbol, period=fetch_period, interval='15m')
        df_4h = df_h1.resample('4h').agg(AGG).dropna()
        df_daily = df_h1.resample('1D').agg(AGG).dropna()
        for df in (df_4h, df_h1, df_15m, df_daily):
            if df.index.tz is not None:
                df.index = df.index.tz_convert(None)
        return df_4h, df_h1, df_15m, df_daily, None
    else:
        df_h1 = fetch_data_yfinance(symbol, period=fetch_period, interval='1h')
        df_m5 = fetch_data_yfinance(symbol, period=fetch_period, interval='5m')
        for df in (df_h1, df_m5):
            if df.index.tz is not None:
                df.index = df.index.tz_convert(None)
        return None, df_h1, df_m5, None, 'bos'


def slice_by_days(df, start_dt, end_dt):
    """Slice DataFrame to date range (inclusive)."""
    if df is None or df.empty:
        return df
    mask = (df.index >= start_dt) & (df.index <= end_dt)
    return df.loc[mask].copy()


def run_walk_forward(strategy, symbol, train_days, test_days, step_days, holdout_pct=None):
    """Run walk-forward analysis."""
    period = f"{train_days + test_days + (train_days if step_days else 0)}d"
    print(f"Fetching data for {symbol}...")
    if strategy == 'kingsely_gold':
        df_4h, df_h1, df_15m, df_daily, _ = fetch_full_data(symbol, '60d')
        if df_h1.empty or df_15m.empty:
            print("No data.")
            return
        all_dates = df_h1.index
    else:
        _, df_h1, df_m5, _, _ = fetch_full_data(symbol, '60d')
        if df_h1.empty or df_m5.empty:
            print("No data.")
            return
        all_dates = df_h1.index

    start = all_dates.min()
    end = all_dates.max()
    total_days = (end - start).days
    print(f"Data range: {start.date()} to {end.date()} ({total_days} days)\n")

    if holdout_pct:
        holdout_days = int(total_days * holdout_pct / 100)
        train_end = end - timedelta(days=holdout_days)
        if strategy == 'kingsely_gold':
            df_4h_t = slice_by_days(df_4h, start, train_end)
            df_h1_t = slice_by_days(df_h1, start, train_end)
            df_15m_t = slice_by_days(df_15m, start, train_end)
            df_daily_t = slice_by_days(df_daily, start, train_end)
            df_4h_h = slice_by_days(df_4h, train_end, end)
            df_h1_h = slice_by_days(df_h1, train_end, end)
            df_15m_h = slice_by_days(df_15m, train_end, end)
            df_daily_h = slice_by_days(df_daily, train_end, end)
            s_train = run_kingsley_backtest(return_stats=True, df_4h=df_4h_t, df_h1=df_h1_t, df_15m=df_15m_t, df_daily=df_daily_t, symbol=symbol)
            s_holdout = run_kingsley_backtest(return_stats=True, df_4h=df_4h_h, df_h1=df_h1_h, df_15m=df_15m_h, df_daily=df_daily_h, symbol=symbol)
        else:
            df_h1_t = slice_by_days(df_h1, start, train_end)
            df_m5_t = slice_by_days(df_m5, start, train_end)
            df_h1_h = slice_by_days(df_h1, train_end, end)
            df_m5_h = slice_by_days(df_m5, train_end, end)
            s_train = run_bos_backtest(return_stats=True, symbol=symbol, df_h1=df_h1_t, df_m5=df_m5_t)
            s_holdout = run_bos_backtest(return_stats=True, symbol=symbol, df_h1=df_h1_h, df_m5=df_m5_h)
        print("Holdout Analysis")
        print("-" * 70)
        print(f"{'Window':<12} | {'Trades':>6} | {'Win%':>6} | {'Return':>10}")
        print("-" * 70)
        print(f"{'Train':<12} | {s_train['trades']:>6} | {s_train['win_rate']:>5.1f}% | {s_train['return_pct']:>+9.1f}%")
        print(f"{'Holdout':<12} | {s_holdout['trades']:>6} | {s_holdout['win_rate']:>5.1f}% | {s_holdout['return_pct']:>+9.1f}%")
        return

    results = []
    fold = 0
    train_start = start
    while True:
        train_end = train_start + timedelta(days=train_days)
        test_start = train_end
        test_end = test_start + timedelta(days=test_days)
        if test_end > end:
            break
        fold += 1
        if strategy == 'kingsely_gold':
            df_4h_t = slice_by_days(df_4h, train_start, train_end)
            df_h1_t = slice_by_days(df_h1, train_start, train_end)
            df_15m_t = slice_by_days(df_15m, train_start, train_end)
            df_daily_t = slice_by_days(df_daily, train_start, train_end)
            df_4h_v = slice_by_days(df_4h, test_start, test_end)
            df_h1_v = slice_by_days(df_h1, test_start, test_end)
            df_15m_v = slice_by_days(df_15m, test_start, test_end)
            df_daily_v = slice_by_days(df_daily, test_start, test_end)
            s_train = run_kingsley_backtest(return_stats=True, df_4h=df_4h_t, df_h1=df_h1_t, df_15m=df_15m_t, df_daily=df_daily_t, symbol=symbol)
            s_test = run_kingsley_backtest(return_stats=True, df_4h=df_4h_v, df_h1=df_h1_v, df_15m=df_15m_v, df_daily=df_daily_v, symbol=symbol)
        else:
            df_h1_t = slice_by_days(df_h1, train_start, train_end)
            df_m5_t = slice_by_days(df_m5, train_start, train_end)
            df_h1_v = slice_by_days(df_h1, test_start, test_end)
            df_m5_v = slice_by_days(df_m5, test_start, test_end)
            s_train = run_bos_backtest(return_stats=True, symbol=symbol, df_h1=df_h1_t, df_m5=df_m5_t)
            s_test = run_bos_backtest(return_stats=True, symbol=symbol, df_h1=df_h1_v, df_m5=df_m5_v)
        results.append((fold, s_train, s_test))
        train_start = train_start + timedelta(days=step_days)

    print("Walk-Forward Analysis")
    print("-" * 90)
    print(f"{'Fold':<6} | {'Train Trades':>11} | {'Train Ret%':>10} | {'Test Trades':>11} | {'Test Ret%':>10}")
    print("-" * 90)
    for fold, s_train, s_test in results:
        print(f"{fold:<6} | {s_train['trades']:>11} | {s_train['return_pct']:>+9.1f}% | {s_test['trades']:>11} | {s_test['return_pct']:>+9.1f}%")


def main():
    parser = argparse.ArgumentParser(description="Walk-forward analysis for strategy validation")
    parser.add_argument("--strategy", default="kingsely_gold", choices=["kingsely_gold", "h1_m5_bos"])
    parser.add_argument("--symbol", default="GC=F")
    parser.add_argument("--train-days", type=int, default=30)
    parser.add_argument("--test-days", type=int, default=14)
    parser.add_argument("--step-days", type=int, default=14)
    parser.add_argument("--holdout", type=float, default=None, help="Holdout pct (e.g. 20) for train/holdout split")
    args = parser.parse_args()
    if args.strategy == "kingsely_gold" and "GC=" not in args.symbol and "XAU" not in args.symbol.upper():
        args.symbol = "GC=F"
    run_walk_forward(args.strategy, args.symbol, args.train_days, args.test_days, args.step_days, args.holdout)


if __name__ == "__main__":
    main()
