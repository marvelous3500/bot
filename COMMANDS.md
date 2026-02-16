# ICT Trading Bot — Commands to Run Strategies

Use these commands from the project folder (e.g. `C:\Users\...\Desktop\bot` or `~/Desktop/bot`).

---

## Backtest (historical data, no MT5)

```bash
# Default: h1_m5_bos strategy, 12d + 60d
python main.py --mode backtest

# One strategy, one symbol
python main.py --mode backtest --strategy pdh_pdl --symbol "GBPUSD=X"
python main.py --mode backtest --strategy liquidity_sweep --symbol "GC=F"
python main.py --mode backtest --strategy h1_m5_bos --symbol "GBPUSD=X"
python main.py --mode backtest --strategy confluence --symbol "GBPUSD=X"
python main.py --mode backtest --strategy kingsely_gold --symbol "GC=F"
# Compare kingsely_gold vs h1_m5_bos on gold (same result table)
python main.py --mode backtest --strategy gold_compare --period 60d

# Run all strategies (summary table)
python main.py --mode backtest --strategy all

# Backtest period when using --strategy all (12d, 60d, or both)
python main.py --mode backtest --strategy all --period 12d
python main.py --mode backtest --strategy all --period 60d
```

**Strategies:** `pdh_pdl` | `liquidity_sweep` | `h1_m5_bos` | `confluence` | `kingsely_gold` | `gold_compare` | `all`

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
```

---

## Replay (live-style flow on history, no MT5)

```bash
python main.py --mode replay --strategy liquidity_sweep --symbol "GBPUSD=X"
python main.py --mode replay --strategy h1_m5_bos --symbol "GC=F"
python main.py --mode replay --strategy kingsely_gold --symbol "GC=F"
```

---

## Setup (first time)

```bash
pip install -r requirements.txt
# On Windows for paper/live:
pip install -r requirements-windows.txt
```

Copy `.env.example` to `.env` and set `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`. For Exness MT5, set `MT5_PATH` (e.g. `C:/Program Files/MetaTrader 5 EXNESS/terminal64.exe`) if the bot should start the terminal. Log in once manually in the MT5 app, then you can run the bot and it will connect using `.env` credentials.
