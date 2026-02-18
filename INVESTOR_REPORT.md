# ICT Trading Bot — Progress & Investor Report

**Document type:** Progress report and system overview  
**Audience:** Investors and stakeholders  
**Date:** February 2026  
**Status:** Operational (backtest, paper, live)

---

## 1. Executive Summary

The **ICT Trading Bot** is a rules-based algorithmic trading system that implements **ICT (Inner Circle Trader)**-style strategies on forex and gold. The system is **fully built and operational**: it backtests on historical data, runs in paper mode with live prices, and executes live trades via MetaTrader 5 (MT5). Risk controls, position and symbol rules, and breakeven logic are implemented and configurable. Progress to date represents a complete pipeline from research (backtest) to execution (live) with guardrails in place.

**Highlights:**

- **Multiple strategies** — PDH/PDL, liquidity sweep, H1–M5 break of structure (BOS), confluence, and a dedicated gold strategy (Kingsley) are implemented and backtestable.
- **Full execution stack** — Paper and live trading through MT5 (e.g. Exness), with dynamic position sizing, margin checks, and broker-safe order handling.
- **Risk and position rules** — No duplicate entries on the same pair unless adding at TP1/TP2; optional breakeven (move SL to entry after X pips in profit); configurable daily trade limits and manual or auto-approval.
- **Backtest framework** — Per-strategy backtests with consistent metrics (trades, wins, losses, win rate, final balance, return %). Results depend on strategy, symbol, and period; run `--strategy all` or per-strategy for current numbers.

---

## 2. Product & System Overview

### 2.1 What It Does

| Mode        | Purpose |
|------------|---------|
| **Backtest** | Run strategies on historical OHLCV (Yahoo Finance or CSV). Bar-by-bar simulation of SL/TP. Output: trade count, win rate, P&L, return %. |
| **Paper**    | Same logic as live, but orders are simulated; positions use live MT5 prices for SL/TP. Validates strategy and risk before going live. |
| **Live**     | Real orders via MT5. Strategy runs on a timer (e.g. every 30s); signals pass safety checks then are sent to the broker. |
| **Replay**   | Replay the live flow on historical data (no MT5). Useful for testing execution logic and filters. |

### 2.2 Technology Stack

- **Language:** Python 3  
- **Data:** pandas, yfinance (backtest); MetaTrader5 (live/paper)  
- **Config:** Single `config.py`; secrets in `.env`  
- **Optional:** OpenAI for signal confidence and trade explanation; text-to-speech for alerts  

The codebase is modular: strategies live in `bot/strategies/`, backtest runners in `bot/backtest/`, and the live/paper engine in `bot/live_trading.py` with a clear separation between signal generation and execution.

---

## 3. Strategies & Backtesting

### 3.1 Available Strategies

| Strategy ID        | Focus | Typical use |
|--------------------|--------|-------------|
| **pdh_pdl**        | Previous day high/low break + retest, FVG/OB, kill zones | Multi-asset, 5m |
| **liquidity_sweep** | 4H liquidity sweep → 1H confirm → 15m FVG/OB entry | Swing, multi-timeframe |
| **h1_m5_bos**       | H1 break of structure + order block → M5 tap + entry | Gold / forex |
| **confluence**      | 4H BOS + 15m OB, kill zone, fixed 50 pip SL | Structured entries |
| **kingsely_gold**   | H1 trend + 15m BOS/ChoCH + zone → liquidity + OB test | Gold (XAUUSD) only |
| **test**            | Minimal trend + fixed SL/TP | Smoke tests, demos |

Each strategy exposes the same interface: `prepare_data()` then `run_backtest()` (or equivalent for live), returning signals with entry, SL, and optional TP/reason.

### 3.2 Backtest Framework

- **Data:** Yahoo Finance (e.g. GC=F for gold, GBPUSD=X) or CSV. Configurable period (e.g. 12d, 60d).  
- **Risk:** Configurable risk per trade (e.g. 10% of balance), 1:3 risk:reward by default.  
- **Metrics:** Trades, wins, losses, win rate, total profit/loss, final balance, return %.  
- **Comparison:** `--strategy gold_compare` runs Kingsley vs BOS on gold and prints a comparison table.

Backtest results are **strategy-, symbol-, and period-dependent**. Investors should request or run the latest backtests (e.g. `python main.py --mode backtest --strategy all --period 60d`) for current performance figures rather than relying on this document for specific numbers.

---

## 4. Risk Management & Safety (Live)

### 4.1 Pre-Trade

- **SL validation** — Every signal is checked so that SL is on the correct side of entry (e.g. below for BUY). Invalid signals are skipped.  
- **Margin check** — Optional pre-trade check that free margin is sufficient for the order.  
- **Daily cap** — Configurable max trades per day (in-memory; resets at midnight local time).  
- **Manual or auto-approval** — Trades can require explicit y/n or run headless with auto-approve.

### 4.2 Position & Symbol Rules

- **Same symbol** — If there is already an open position on a symbol, the bot **does not** open another trade on that symbol **unless** the new entry is at or near an existing position’s TP1 or TP2 (add-on logic). This avoids duplicate entries and respects the “add only at TP1/TP2” rule.  
- **Breakeven** — When a position is in profit by a configurable number of pips (e.g. 3–10), the bot can move the stop loss to the entry price (breakeven). This is a global engine feature (all strategies, all symbols) and can be turned on/off and adjusted in config.

### 4.3 Execution & Broker

- **Order comment** — Sanitized for broker limits (length, characters). Optional fixed or empty comment to satisfy strict brokers (e.g. Exness).  
- **Position sizing** — Dynamic lot size from risk % of balance (aligned with backtest), with fallback to a max position size.  
- **MT5** — Connection, retries, and logging are configurable; errors (e.g. invalid comment, trade disabled) are surfaced with clear messages.

---

## 5. Live Trading Capabilities

- **Broker:** MetaTrader 5 (e.g. Exness). Credentials and server from `.env`.  
- **Symbols:** Configurable (e.g. XAUUSDm, GBPUSDm). Kingsley strategy is built for gold.  
- **Loop:** Strategy runs every `LIVE_CHECK_INTERVAL` seconds (e.g. 30s). On each run: fetch bars and live price, run strategy, apply safety and same-symbol/TP rules, run breakeven check, then execute or reject.  
- **Logging:** Signal details (entry, SL, distance, risk in dollars), execution result, and status (balance, equity, open positions) are printed. Optional voice and AI explanation for executed trades.

---

## 6. Progress & Milestones

| Area | Status | Notes |
|------|--------|--------|
| Strategy design | Done | Multiple ICT-style strategies implemented and backtestable. |
| Backtest engine | Done | Bar-by-bar SL/TP simulation; comparable metrics across strategies. |
| Paper trading | Done | Same logic as live with simulated orders; MT5 prices for SL/TP. |
| Live execution | Done | Real orders via MT5; FOK/IOC/return handling; comment and margin handling. |
| Same-symbol / TP rule | Done | No second entry on same pair unless at TP1/TP2. |
| Breakeven (SL to entry) | Done | Configurable pips trigger; applies to all strategies/symbols. |
| Risk & safety | Done | SL validation, margin check, daily limit, optional manual approval. |
| Configurability | Done | Single config file; breakeven, TP rule, risk, and execution options are tunable. |
| Documentation | Done | ONBOARDING.md, LIVE_TRADING_GUIDE.md, and this report. |

---

## 7. What Success Looks Like (From Our Side)

- **Backtest:** Strategies produce consistent, interpretable metrics (win rate, return %) over chosen periods; parameters (risk, R:R, filters) are documented and configurable.  
- **Paper:** Engine runs without errors; behaviour matches backtest logic; same-symbol and breakeven rules behave as intended.  
- **Live:** Orders are accepted by the broker; SL/TP and breakeven modifications execute as configured; risk and position rules prevent unintended duplication or over-trading.

Actual **financial** success (e.g. positive expectancy, drawdown limits) depends on strategy choice, parameters, symbol, and market regime. Investors should review backtest and, where available, paper/live results for the strategies and symbols they care about.

---

## 8. Next Steps & Disclaimer

**Suggested next steps:**

- Run and archive backtests (e.g. `--strategy all`, 12d and 60d) for each strategy/symbol of interest and attach summary tables to this report or a separate performance document.  
- Optionally add a simple dashboard or export (e.g. CSV) of backtest and paper results for investor reporting.  
- Keep live risk parameters (daily limit, risk %, breakeven pips) under periodic review as the bot runs in production.

**Disclaimer:** This document describes the system’s design, capabilities, and progress. It is not financial advice. Trading involves risk of loss. Past backtest or paper results do not guarantee future live performance. Investors should rely on their own due diligence and, where applicable, professional advice.

---

*Report generated from the ICT Trading Bot codebase and documentation. For technical details, see ONBOARDING.md and LIVE_TRADING_GUIDE.md.*
