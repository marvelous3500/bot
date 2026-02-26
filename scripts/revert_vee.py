#!/usr/bin/env python3
"""
Restore vee strategy to the saved snapshot state.
Run from repo root: python scripts/revert_vee.py
Or: python main.py --revert-vee (if wired in CLI).
Snapshot: 1H bias -> 15m CHOCH -> OB+FVG -> entry on OB zone (candle); SL beyond OB; TP 3R.
"""

import os
import shutil

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT = os.path.join(REPO_ROOT, "scripts", "vee_revert", "strategy_vee_snapshot.py")
TARGET = os.path.join(REPO_ROOT, "bot", "strategies", "strategy_vee.py")


def main():
    if not os.path.isfile(SNAPSHOT):
        print(f"Snapshot not found: {SNAPSHOT}")
        return 1
    shutil.copy2(SNAPSHOT, TARGET)
    print(f"Reverted vee strategy to snapshot: {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
