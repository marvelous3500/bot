#!/usr/bin/env python3
"""Print active Marvellous config (from config.py via marvellous_config).
Run this to verify your config.py changes are being loaded."""
import sys
sys.path.insert(0, ".")
from bot import marvellous_config as mc
import config

print("Marvellous Strategy — Active Config (from config.py)")
print("=" * 50)
print("Symbols (MARVELLOUS_SYMBOL=None → gold):")
print(f"  MARVELLOUS_BACKTEST_SYMBOL:   {mc.MARVELLOUS_BACKTEST_SYMBOL}")
print(f"  MARVELLOUS_LIVE_SYMBOL:       {mc.MARVELLOUS_LIVE_SYMBOL}")
print(f"  (config MARVELLOUS_SYMBOL:    {getattr(config, 'MARVELLOUS_SYMBOL', 'N/A')})")
print("=" * 50)
print("Bias (only enabled timeframes are checked):")
print(f"  REQUIRE_H1_BIAS:              {mc.REQUIRE_H1_BIAS}")
print(f"  REQUIRE_4H_BIAS:               {mc.REQUIRE_4H_BIAS}")
print(f"  REQUIRE_DAILY_BIAS:            {mc.REQUIRE_DAILY_BIAS}")
print("Zone confirmation (only used when that bias is required):")
print(f"  REQUIRE_H1_ZONE_CONFIRMATION:  {mc.REQUIRE_H1_ZONE_CONFIRMATION}")
print(f"  REQUIRE_4H_ZONE_CONFIRMATION:  {mc.REQUIRE_4H_ZONE_CONFIRMATION}")
print(f"  REQUIRE_DAILY_ZONE_CONFIRMATION: {mc.REQUIRE_DAILY_ZONE_CONFIRMATION}")
print("Filters that affect signal count:")
print(f"  USE_LIQUIDITY_MAP:             {mc.USE_LIQUIDITY_MAP}")
print(f"  AVOID_NEWS:                    {mc.AVOID_NEWS}")
print(f"  ENTRY_WINDOW_HOURS:            {mc.MARVELLOUS_ENTRY_WINDOW_HOURS}")
print(f"  ENTRY_WINDOW_MINUTES:         {getattr(mc, 'MARVELLOUS_ENTRY_WINDOW_MINUTES', 15)}")
print(f"  SWING_LENGTH:                  {mc.MARVELLOUS_SWING_LENGTH}")
print(f"  OB_LOOKBACK:                    {mc.MARVELLOUS_OB_LOOKBACK}")
print("=" * 50)
print("Tip: To get more trades, try REQUIRE_H1_ZONE_CONFIRMATION=False,")
print("     USE_LIQUIDITY_MAP=False, AVOID_NEWS=False, or ENTRY_WINDOW_MINUTES=30-60")
