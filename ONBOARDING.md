# ICT Trading Bot — Onboarding & Architecture

This document describes the **treading-bot** project: purpose, architecture, patterns, and how to run or extend it.

> [!TIP]
> **Developers**: For detailed implementation guides on adding indicators or strategies, see [DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md).

---

## 1. Project Overview

**What it is:** A Python trading bot for **ICT (Inner Circle Trader)** strategies.
- **Modes**: Backtesting, Paper Trading, Live Trading.
- **Broker**: MetaTrader 5 (optimized for Exness).
- **Symbol Support**: Yahoo Finance (backtest) and MT5 (live).

### Strategies
| Strategy | Description | Key Patterns |
|----------|-------------|--------------|
| `marvellous` | D/4H/H1 Bias + M15 BOS + OB tap | Multi-TF BOS/OB |
| `vester` | 1H Bias → 5M Setup → 1M Entry | Sweep + BOS + Zone |

---

## 2. Architecture & Patterns

### 2.1 Component Flow
- **CLI (`main.py`)**: The entry point.
- **Backtest**: Strategy generates signals $\rightarrow$ Runner simulates SL/TP.
- **Live (`LiveTradingEngine`)**: Periodically runs strategy $\rightarrow$ Validates Safety $\rightarrow$ Executes.

### 2.2 Core Patterns
- **Indicator Pattern**: Functional and stateless (`bot/indicators.py`).
- **Strategy Pattern**: Class-based with `prepare_data` and `run_backtest`.
- **Config Pattern**: Centralized `config.py` with `.env` for secrets.

---

## 3. Component Map

| Folder/File | Purpose |
|-------------|---------|
| `config.py` | Central configuration and environment loading. |
| `ai/` | Signal confidence (OpenAI) and voice alerts. |
| `bot/strategies/` | The core trading logic. |
| `bot/indicators.py` | ICT-specific indicator functions (FVG, OB, Sweep). |
| `bot/live_trading.py` | The main engine for live and paper modes. |
| `bot/mt5_connector.py` | Low-level MT5 integration. |

---

## 4. How to Run

### Backtest
```bash
python main.py --mode backtest --strategy vester --symbol "GC=F"
```

### Paper Trading
1. Set `LIVE_MODE = False` in `config.py`.
2. Ensure MT5 is running.
```bash
python main.py --mode paper --strategy vester
```

---

## 5. Development 
Refer to [DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) for:
- Adding indicators.
- Creating new strategy classes.
- Live trading lifecycle details.
