#!/usr/bin/env python3
"""
Run Marvellous strategy backtest for 12d and 60d, print results side by side.
Note: Yahoo limits 15m data to 60 days, so 90d uses 60d of data.
"""
import sys
import os
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from bot.backtest import run_marvellous_backtest


def main():
    symbol = getattr(config, "MARVELLOUS_BACKTEST_SYMBOL", "GC=F")
    print("Marvellous Strategy — 12d vs 60d Backtest Comparison")
    print("=" * 80)
    print(f"Asset: {symbol} | Risk: {config.RISK_PER_TRADE*100:.0f}% | R:R 1:{config.RISK_REWARD_RATIO}")
    print()

    periods = [("12 days", "12d"), ("60 days", "60d")]
    results = []

    old_stdout = sys.stdout
    for label, period in periods:
        print(f"Running {label}...", end=" ", flush=True)
        sys.stdout = io.StringIO()
        try:
            stats = run_marvellous_backtest(symbol=symbol, period=period, return_stats=True)
        finally:
            sys.stdout = old_stdout
        stats["period_label"] = label
        results.append(stats)
        print("done.")

    print()
    print("| Period    | Trades | Wins | Losses | Win rate  | Final balance | Return      |")
    print("| :-------- | :----- | :--- | :----- | :-------- | :------------ | :---------- |")
    for s in results:
        wr = f"{s['win_rate']:.2f}%" if s["trades"] else "—"
        ret_str = f"{'+' if s['return_pct'] >= 0 else ''}{s['return_pct']:,.2f}%" if s["trades"] else "—"
        bal = f"${s['final_balance']:,.2f}" if s["trades"] else "$100.00"
        print(f"| {s['period_label']:<9} | {s['trades']:>6} | {s['wins']:>4} | {s['losses']:>6} | {wr:>9} | {bal:>13} | {ret_str:>10} |")
    print("=" * 80)


if __name__ == "__main__":
    main()
