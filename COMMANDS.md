# ICT Trading Bot — Commands to Run Strategies

Use these commands from the project folder (e.g. `C:\Users\...\Desktop\bot` or `~/Desktop/bot`).

---

## Backtest (historical data, no MT5)

```bash
# Default: h1_m5_bos strategy, 12d + 60d
python main.py --mode backtest

# One strategy, one symbol
python main.py --mode backtest --strategy h1_m5_bos --symbol "GBPUSD=X"
python main.py --mode backtest --strategy kingsely_gold --symbol "GC=F"
python main.py --mode backtest --strategy test --symbol "GC=F"
# Compare kingsely_gold vs h1_m5_bos on gold (same result table)
python main.py --mode backtest --strategy gold_compare --period 60d

# Compare Marvellous vs Kingsley on gold (side by side)
python main.py --mode backtest --strategy marvellous_kingsley_compare --period 60d

# Verify Marvellous config is loaded (after editing config.py)
python scripts/print_marvellous_config.py

# Marvellous: compare 12d vs 60d backtest (side by side)
python scripts/compare_marvellous_periods.py

# Run all strategies (summary table)
python main.py --mode backtest --strategy all

# Backtest period when using --strategy all (12d, 60d, or both)
python main.py --mode backtest --strategy all --period 12d
python main.py --mode backtest --strategy all --period 60d
```

**Strategies:** `h1_m5_bos` | `kingsely_gold` | `marvellous` | `test` | `gold_compare` | `marvellous_kingsley_compare` | `all`

### Parameter sweep (Kingsley fine-tuning)

```bash
# Run sweep with different config values, print results side by side
python scripts/sweep_kingsley.py
```

### Kingsley vs LuxAlgo ICT comparison

```bash
# Compare Kingsley (fractal) vs LuxAlgo (pivot) backtest results side by side
python scripts/compare_kingsley_luxalgo.py
python scripts/compare_kingsley_luxalgo.py --period 12d
python scripts/compare_kingsley_luxalgo.py --csv path/to/data.csv
```

---

## Paper trading (MT5 required, no real orders)

```bash
# Default strategy: h1_m5_bos
python main.py --mode paper

# Auto-approve (no manual prompt) — for server/headless runs
python main.py --mode paper --auto-approve

# Specific strategy
python main.py --mode paper --strategy h1_m5_bos
python main.py --mode paper --strategy kingsely_gold   # Gold (XAUUSD) only
python main.py --mode paper --strategy test            # Gold, smoke test
```

---

## Live trading (MT5 required, real orders)

```bash
# Default strategy: h1_m5_bos
python main.py --mode live

# Auto-approve (no manual prompt) — for server/headless runs
python main.py --mode live --auto-approve

# Specific strategy
python main.py --mode live --strategy h1_m5_bos
python main.py --mode live --strategy kingsely_gold    # Gold (XAUUSD) only
python main.py --mode live --strategy test             # Gold, smoke test
```

---

## Replay (live-style flow on history, no MT5)

```bash
python main.py --mode replay --strategy h1_m5_bos --symbol "GC=F"
python main.py --mode replay --strategy kingsely_gold --symbol "GC=F"
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
