"""
Utility: run a 1‑week backtest for the V1 strategy.

Usage (from project root):

    python -m scripts.run_v1_one_week

You can override the default symbol or CSV via environment variables:
    V1_BT_SYMBOL=GC=F python -m scripts.run_v1_one_week
    V1_BT_CSV=path/to/data.csv python -m scripts.run_v1_one_week
"""

import os

import config
from bot.backtest import run_v1_backtest


def main() -> None:
    # Prefer CSV if provided (avoids Yahoo limits), otherwise use symbol.
    csv_path = os.getenv("V1_BT_CSV") or None
    symbol = os.getenv("V1_BT_SYMBOL") or getattr(config, "V1_BACKTEST_SYMBOL", "GC=F")

    period = "7d"  # exactly one week of data when using Yahoo

    print("\n============================================================")
    print(f"Running 1‑week V1 backtest on {symbol}")
    print("============================================================")
    run_v1_backtest(csv_path=csv_path, symbol=symbol, period=period)


if __name__ == "__main__":
    main()

