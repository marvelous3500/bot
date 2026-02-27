#!/usr/bin/env python3
"""
Test the Telegram notifier. Sends a sample setup message to verify bot token and chat ID.
Run from project root: python scripts/test_telegram.py
"""
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

# Force Telegram enabled for this test (ignores .env TELEGRAM_ENABLED)
os.environ['TELEGRAM_ENABLED'] = 'true'

from bot.telegram_notifier import test_telegram

if __name__ == "__main__":
    strategy = sys.argv[1] if len(sys.argv) > 1 else "vester"
    ok = test_telegram(strategy_name=strategy)
    sys.exit(0 if ok else 1)
