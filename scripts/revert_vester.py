#!/usr/bin/env python3
"""
Restore vester strategy to the saved snapshot state (before H1 liquidity sweep confirmation).
Run from repo root: python scripts/revert_vester.py
Or: python main.py --revert-vester
"""

import os
import shutil

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT = os.path.join(REPO_ROOT, "scripts", "vester_revert", "strategy_vester_snapshot.py")
TARGET = os.path.join(REPO_ROOT, "bot", "strategies", "strategy_vester.py")


def main():
    if not os.path.isfile(SNAPSHOT):
        print(f"Snapshot not found: {SNAPSHOT}")
        return 1
    shutil.copy2(SNAPSHOT, TARGET)
    print(f"Reverted vester strategy to snapshot: {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
