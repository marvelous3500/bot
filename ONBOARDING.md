# ICT Trading Bot — Onboarding & Architecture

This document describes the **treading-bot** (ICT Trading Bot) project: purpose, architecture, patterns, and how to run or extend it. Use it for onboarding and as a reference when changing code.

---

## 1. Project Overview

**What it is:** A Python trading bot that implements **ICT (Inner Circle Trader)**-style strategies. It supports:

- **Backtesting** on historical data (Yahoo Finance or CSV)
- **Paper trading** (simulated orders with live MT5 data)
- **Live trading** (real orders via MetaTrader 5)

**Stack:** Python 3, pandas, yfinance, MetaTrader5, python-dotenv. Code is organized in **ai/** (AI + voice) and **bot/** (strategies, backtest, live/paper engine).

**Strategies:**

| Strategy ID        | Module (under `bot/strategies/`) | Description |
|--------------------|----------------------------------|-------------|
| `h1_m5_bos`        | `strategy_bos.py`   | H1 Break of Structure + OB → M5 shallow tap + liquidity sweep + entry |
| `kingsely_gold`    | `strategy_kingsley.py` | H1 trend + 15m BOS/ChoCH + zone→LQ + OB test (gold only) |
| `test`             | `strategy_test.py` | Minimal trend follow (gold, smoke test) |

---

## 2. Architecture

### 2.1 High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  main.py (CLI)                                                              │
│  --mode: backtest | paper | live    --strategy: h1_m5_bos | kingsely_gold | test
└─────────────────────────────────────────────────────────────────────────────┘
         │
         ├── backtest ──► bot/backtest/ (per-strategy runners)
         │                      │
         │                      ├── bot/data_loader (yfinance or CSV)
         │                      ├── bot/strategies: prepare_data() → run_backtest()
         │                      └── Simulate P&L (SL/TP bar-by-bar)
         │
         └── paper | live ──► bot/live_trading.LiveTradingEngine
                                    │
                                    ├── bot/mt5_connector (MT5 data + orders)
                                    ├── bot/paper_trading (virtual positions) or real MT5 orders
                                    ├── bot/trade_approver (manual y/n if MANUAL_APPROVAL)
                                    ├── ai/ (confidence + explain_trade + voice, optional)
                                    └── Same strategies, run periodically (run_strategy → execute_signal)
```

### 2.2 Component Roles

| Component | Role |
|-----------|------|
| **config.py** | Single source of config: symbols, timeframes, risk, filters (EMA, kill zones, FVG/OB), live/MT5 settings. Loads `.env` for secrets. |
| **ai/** | AI helper (signal confidence, explain_trade via OpenAI) and voice (speak via pyttsx3). Optional; config flags in config.py. |
| **bot/data_loader.py** | Fetch OHLCV from Yahoo Finance or load from CSV. Normalizes columns to lowercase and datetime index. |
| **bot/mt5_connector.py** | MT5 connection, account/symbol info, bars, live price, place_order, get_positions, close_position. Returns dicts/DataFrames. |
| **bot/indicators.py** | FVG, order block, liquidity sweep, EMA, displacement. Adds boolean/float columns to DataFrame. |
| **bot/indicators_bos.py** | Swing highs/lows, break of structure (BOS), order block identification, shallow tap. Dispatches to Kingsley (fractal) or LuxAlgo-style (pivot) per `USE_LUXALGO_ICT`. |
| **bot/indicators_luxalgo.py** | LuxAlgo-style ICT parity: pivot swings, MSS/BOS, OB with breaker. Used when `USE_LUXALGO_ICT=True`. |
| **bot/strategies/strategy_bos.py** | `H1M5BOSStrategy`: H1 + M5 DataFrames; `prepare_data()` then `run_backtest()` → signals. |
| **bot/strategies/strategy_kingsley.py** | `KingsleyGoldStrategy`: 4H + H1 + 15m; BOS/ChoCH + zone→LQ + OB test (gold). |
| **bot/strategies/strategy_test.py** | `TestStrategy`: H1 trend follow (gold, smoke test). |
| **bot/backtest/** | Per-strategy backtest runners: load data, build strategy, run strategy, simulate trades (SL/TP hit first), print results. |
| **bot/live_trading.py** | `LiveTradingEngine`: MT5 data → run_strategy() → optional TradeApprover → execute_signal (paper or MT5). Loop with LIVE_CHECK_INTERVAL. |
| **bot/paper_trading.py** | Virtual balance/positions, place_order, update_positions (MT5 prices for SL/TP), save/load session JSON. |
| **bot/trade_approver.py** | Console prompt for trade approval; shows signal, R:R, risk amount; returns True/False. |
| **bot/replay_engine.py** | Replay live flow on historical data (no MT5); uses same strategies and safety/AI/voice. |

### 2.3 Data Conventions

- **OHLCV columns:** `open`, `high`, `low`, `close`, `volume` (lowercase).
- **Index:** Datetime (timezone-naive in backtests to avoid alignment issues).
- **Strategy inputs:** Strategies receive DataFrames and may mutate copies (`self.df = dataframe.copy()`). Indicators add columns in place.
- **Signals:** List of dicts or DataFrame with at least: `time`, `type` ('BUY'|'SELL'), `price`, `sl`, and optionally `reason`. Live engine adds `symbol`, `tp`, `volume`.

---

## 3. Patterns in the Codebase

### 3.1 Strategy Pattern

- Each strategy is a **class** holding one or two DataFrames.
- **`prepare_data()`** computes indicators (and optionally returns updated frames). Called once before backtest/live run.
- **`run_backtest()`** iterates over bars (and optionally PDH/PDL series), maintains local state (bias, waiting_for_retest, etc.), and returns a **signals DataFrame** with rows like `time, type, price, sl, reason`.
- Backtest runners use these signals and **forward-looking bars** to determine whether SL or TP is hit first and update balance.

### 3.2 Indicator Pattern

- Indicators are **functions** that take a DataFrame (and optional params like `lookback`, `period`) and **return the same DataFrame** with new columns (e.g. `fvg_bull`, `ob_bear`, `ema_50`, `sweep_high`). They are used like:
  - `df = detect_fvg(df); df = detect_order_block(df); ...`
- Strategy modules (in `bot/strategies/`) import from `bot.indicators` or `bot.indicators_bos` and call them inside `prepare_data()`.

### 3.3 Backtest Pattern

- **Load data** (CSV or yfinance); normalize timezone (strip to naive).
- **Build strategy** with the correct frame(s); call `prepare_data()`.
- **Run strategy** to get signals.
- **Simulate P&L:** for each signal, look at future bars; if SL hit first → loss (RISK_PER_TRADE × balance), if TP hit first → win (same risk × RISK_REWARD_RATIO); append to balance and counts; print totals and win rate.

### 3.4 Live/Paper Execution Pattern

- **LiveTradingEngine** gets one “latest” signal per run (e.g. `signals_df.iloc[-1]`), enriches it with symbol, current price, volume, TP.
- **Safety:** `check_safety_limits()` (e.g. MAX_TRADES_PER_DAY); optional **TradeApprover** before execution.
- **Execution:** Paper path uses `PaperTrading.place_order` and `update_positions(mt5_connector)`; live path uses `MT5Connector.place_order`.

---

## 4. File Map (Quick Reference)

| File / folder | Purpose |
|---------------|--------|
| `main.py` | CLI: --mode, --strategy, --csv, --symbol; dispatches to bot.backtest or bot.live_trading. |
| `config.py` | All config + dotenv; SYMBOLS, TIMEFRAME, risk, filters, MT5_*, LIVE_*, AI_*, VOICE_*, etc. |
| `ai/helper.py` | get_signal_confidence, explain_trade (OpenAI). |
| `ai/voice.py` | speak (pyttsx3). |
| `bot/data_loader.py` | fetch_data_yfinance, fetch_daily_data_yfinance, load_data_csv. |
| `bot/mt5_connector.py` | MT5Connector: connect, get_bars, get_live_price, place_order, get_positions, close_position. |
| `bot/indicators.py` | FVG, OB, liquidity sweep, EMA, displacement. |
| `bot/indicators_bos.py` | Swing high/low, BOS, identify_order_block, detect_shallow_tap. |
| `bot/strategies/strategy_bos.py` | H1M5BOSStrategy (H1 BOS + OB, M5 tap + sweep + entry). |
| `bot/strategies/strategy_kingsley.py` | KingsleyGoldStrategy (H1 + 15m BOS/ChoCH + OB test, gold). |
| `bot/strategies/strategy_test.py` | TestStrategy (minimal trend, smoke test). |
| `bot/backtest/` | Per-strategy backtest runners (bos, kingsley, test). |
| `bot/live_trading.py` | LiveTradingEngine: connect, run_strategy, execute_signal, update_positions, run() loop. |
| `bot/paper_trading.py` | PaperTrading: virtual orders, positions, P&L, session JSON. |
| `bot/trade_approver.py` | TradeApprover: request_approval, show_daily_summary. |
| `bot/replay_engine.py` | run_replay: live flow on historical data (no MT5). |
| `.env.example` | Template for MT5_*, OPENAI_API_KEY. |
| `requirements.txt` | pandas, yfinance, python-dotenv, openai, pyttsx3; MetaTrader5 (Windows) in requirements-windows.txt. |

---

## 5. How to Run

### 5.1 Backtest

```bash
# Default: backtest h1_m5_bos
python main.py --mode backtest

# With strategy and symbol
python main.py --mode backtest --strategy h1_m5_bos --symbol "GC=F"
python main.py --mode backtest --strategy kingsely_gold --symbol "GC=F"

# From CSV (must have time/open/high/low/close/volume)
python main.py --mode backtest --strategy h1_m5_bos --csv path/to/data.csv
```

### 5.2 Paper Trading

- Copy `.env.example` to `.env` and set MT5 credentials (MT5 must be running).
- `config.LIVE_MODE = False` and run:

```bash
python main.py --mode paper --strategy h1_m5_bos
```

### 5.3 Live Trading

- Set `config.LIVE_MODE = True` (or add a CLI override if you add one). Use with caution.
- Optional: `MANUAL_APPROVAL = True` to confirm each trade in the terminal.

```bash
python main.py --mode live --strategy h1_m5_bos
```

---

## 6. Configuration and Environment

- **Trading pairs / symbols:** `config.SYMBOLS` (Yahoo); `config.LIVE_SYMBOLS` (MT5 symbols for live/paper).
- **Risk:** `RISK_PER_TRADE`, `RISK_REWARD_RATIO`, `MAX_POSITION_SIZE`, `MAX_TRADES_PER_DAY`.
- **Filters:** `USE_EMA_FILTER`, `EMA_PERIOD`, `USE_KILL_ZONES`, `KILL_ZONE_HOURS`, `REQUIRE_BOTH_FVG_AND_OB`, `USE_DISPLACEMENT_FILTER`, `USE_MARKET_STRUCTURE_FILTER`.
- **Secrets:** `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER` from `.env` via `config.py`.

---

## 7. Adding a New Strategy

1. **Indicators:** Add any new indicator functions in `bot/indicators.py` or a dedicated module (e.g. `bot/indicators_xyz.py`); same pattern: take DataFrame, return it with new columns.
2. **Strategy class:** New file `strategy_xyz.py` with a class that:
   - Takes the needed DataFrame(s) in `__init__`.
   - Implements `prepare_data()` (call indicators).
   - Implements `run_backtest()` returning a DataFrame of signals (`time`, `type`, `price`, `sl`, `reason`).
3. **Backtest runner:** New file `backtest_xyz.py` that loads data, builds the strategy, runs `prepare_data()` and `run_backtest()`, then simulates P&L (reuse the same SL/TP simulation pattern as other backtests).
4. **main.py:** Add `--strategy xyz` choice and dispatch in the backtest branch to `backtest_xyz.run_xyz_backtest(...)`.
5. **bot/live_trading.py:** In `run_strategy()`, add an `elif self.strategy_name == 'xyz':` branch: load the right timeframes from MT5, build the strategy, call `prepare_data()` and `run_backtest()`, then take the latest signal and return it in the same format (symbol, type, price, sl, tp, volume).

---

## 8. Known Inconsistencies / Gotchas

- **Duplicate dependencies:** `requirements.txt` lists `pandas` and `python-dotenv` twice; consider deduplicating.
- **Paper P&L:** Paper trading uses a simplified P&L (e.g. `price_diff * volume * 100`); for realism this could be replaced with symbol-specific point value and contract size from MT5.
- **Live trading:** See [LIVE_TRADING_GUIDE.md](LIVE_TRADING_GUIDE.md) for configuration, safety features (SL enforcement, margin check, approval timeout), and how to run paper/live.

---

## 9. Cursor Rules

When working in this repo, use the **Cursor rules** in `.cursor/rules/` (e.g. the project-context rule with `alwaysApply: true`) so that the AI has consistent context on architecture, strategy/indicator/backtest patterns, and config. See that rule file for concise reminders and conventions.
