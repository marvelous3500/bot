# ICT Trading Bot — Commands to Run Strategies

Use these commands from the project folder (e.g. `C:\Users\...\Desktop\bot` or `~/Desktop/bot`).

---

## Backtest (historical data, no MT5)

```bash
# Default: vester strategy
python main.py --mode backtest

# One strategy, one symbol
python main.py --mode backtest --strategy vester --symbol "GC=F"
python main.py --mode backtest --strategy vee --symbol "GC=F"
python main.py --mode backtest --strategy trend_vester --symbol "GC=F"

# Print per-trade log (entry, SL, TP, outcome, bar hit)
python main.py --mode backtest --strategy vester --symbol "GC=F" --trade-details

# Run all strategies (vester + vee + trend_vester)
python main.py --mode backtest --strategy all

# Backtest period when using --strategy all (12d, 60d, or both)
python main.py --mode backtest --strategy all --period 12d
python main.py --mode backtest --strategy all --period 60d
```

**Strategies:** `vester` | `vee` | `trend_vester` | `test-sl` | `all`

---

## Paper trading (MT5 required, no real orders)

```bash
# Default strategy: vester
python main.py --mode paper

# Auto-approve (no manual prompt) — for server/headless runs
python main.py --mode paper --auto-approve

# Specific strategy
python main.py --mode paper --strategy vester
python main.py --mode paper --strategy vee
python main.py --mode paper --strategy trend_vester   # H1 trend + vester 1M entry (more signals)
```

---

## Live trading (MT5 required, real orders)

```bash
# Default strategy: vester
python main.py --mode live

# Auto-approve (no manual prompt) — for server/headless runs
python main.py --mode live --auto-approve

# Specific strategy
python main.py --mode live --strategy vester
python main.py --mode live --strategy vee
python main.py --mode live --strategy trend_vester   # More signals when vester hasn't fired in days
python main.py --mode live --strategy test-sl         # Lot-size test only (gold)
```

---

## Replay (live-style flow on history, no MT5)

```bash
python main.py --mode replay --strategy marvellous --symbol "GC=F"
python main.py --mode replay --strategy test --symbol "GC=F"
```

---

## Setup (first time)

```bash
pip install -r requirements.txt
# On Windows for paper/live:
pip install -r requirements-windows.txt
```

Copy `.env.example` to `.env` and set `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`. For Exness MT5, set `MT5_PATH` (e.g. `C:/Program Files/MetaTrader 5 EXNESS/terminal64.exe`) if the bot should start the terminal. Log in once manually in the MT5 app, then you can run the bot and it will connect using `.env` credentials.

### Test Telegram notifier

```bash
# Send a sample setup message to verify bot token and chat ID
python scripts/test_telegram.py
python scripts/test_telegram.py marvellous
```

### Symbol-specific config (BTC-USD / BTCUSDm)

When Marvellous runs on BTC-USD or BTCUSDm, the bot uses `SYMBOL_CONFIGS["BTCUSDm"]` in `config.py` for:

- `BACKTEST_SPREAD_PIPS`, `PIP_SIZE`, `MARVELLOUS_MIN_ATR_THRESHOLD`
- `MARVELLOUS_SL_BUFFER`, `MARVELLOUS_SL_FALLBACK_DISTANCE`, `MARVELLOUS_MAX_SPREAD_POINTS`

Edit `config.py` → `SYMBOL_CONFIGS` to tune BTC parameters.

python3 main.py --mode live --strategy marvellous --symbol "BTC-USD"
