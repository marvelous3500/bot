#!/usr/bin/env python3
"""
Run Marvellous strategy backtest with 1m vs 5m entry timeframe, side by side.
Uses 7d period (Yahoo 1m limit) so both runs use the same data for fair comparison.
"""
import sys
import os
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from bot import marvellous_config as mc
from bot.backtest import run_marvellous_backtest


def main():
    symbol = getattr(config, "MARVELLOUS_BACKTEST_SYMBOL", "GC=F")
    period = "7d"  # Same period for both (Yahoo 1m limit)
    print("Marvellous Strategy — 1m vs 5m Entry Timeframe Comparison")
    print("=" * 80)
    print(f"Asset: {symbol} | Period: {period} | Risk: {config.RISK_PER_TRADE*100:.0f}% | R:R 1:{config.RISK_REWARD_RATIO}")
    print()

    results = []
    old_stdout = sys.stdout

    for entry_tf in ["5m", "1m"]:
        print(f"Running with {entry_tf} entry...", end=" ", flush=True)
        # Override entry timeframe for this run
        config.MARVELLOUS_ENTRY_TIMEFRAME = entry_tf
        # Force marvellous_config to pick up the override (it caches at import)
        mc.ENTRY_TIMEFRAME = entry_tf
        sys.stdout = io.StringIO()
        try:
            stats = run_marvellous_backtest(symbol=symbol, period=period, return_stats=True)
        finally:
            sys.stdout = old_stdout
        stats["entry_tf"] = entry_tf
        results.append(stats)
        print("done.")

    print()
    print("| Entry TF | Trades | Wins | Losses | Win rate  | Total Profit | Total Loss  | Final balance | Return      |")
    print("| :------- | :----- | :--- | :----- | :-------- | :----------- | :---------- | :------------ | :---------- |")
    for s in results:
        wr = f"{s['win_rate']:.2f}%" if s["trades"] else "—"
        ret_str = f"{'+' if s['return_pct'] >= 0 else ''}{s['return_pct']:,.2f}%" if s["trades"] else "—"
        bal = f"${s['final_balance']:,.2f}" if s["trades"] else "$100.00"
        profit = f"${s['total_profit']:,.2f}" if s["trades"] else "$0"
        loss = f"${s['total_loss']:,.2f}" if s["trades"] else "$0"
        print(f"| {s['entry_tf']:<8} | {s['trades']:>6} | {s['wins']:>4} | {s['losses']:>6} | {wr:>9} | {profit:>12} | {loss:>12} | {bal:>12} | {ret_str:>10} |")
    print("=" * 80)


if __name__ == "__main__":
    main()
