# Live Trading Guide — ICT Trading Bot

This guide describes how to configure and run the bot in **paper** and **live** mode with MetaTrader 5 (Exness), what is enforced in code, and how the implementation is structured.

---

## 1. Entry Point and How to Run

**Paper trading (recommended first):**
```bash
python main.py --mode paper --strategy pdh_pdl
```

**Live trading (real money):**
```bash
python main.py --mode live --strategy pdh_pdl
```

**Options:**
- `--mode`: `backtest` | `paper` | `live`
- `--strategy`: `pdh_pdl` | `liquidity_sweep` | `h1_m5_bos` | `confluence`
- `--symbol`: used for backtest only; live/paper use the first symbol from `config.LIVE_SYMBOLS`

**Requirements:** MT5 terminal must be running and logged in (or credentials in `.env`). The bot connects to MT5, runs the selected strategy every `LIVE_CHECK_INTERVAL` seconds, and executes or simulates trades when signals pass all safety checks.

**Installation:** On **Mac**, `pip install -r requirements.txt` installs core deps only (MetaTrader5 is Windows-only on PyPI). Backtest works on Mac; for paper/live use **Windows** and run `pip install -r requirements-windows.txt` after the main requirements.

### Running on Mac (MetaApi)

You can run **paper** and **live** on Mac without a Windows VM by using the **MetaApi** cloud connector (same REST API as MT5, no local terminal).

1. Get a token at [https://app.metaapi.cloud/token](https://app.metaapi.cloud/token).
2. Add your MT5 account at [https://app.metaapi.cloud/accounts](https://app.metaapi.cloud/accounts) (login, password, server). Copy the **account ID** (UUID).
3. In `.env` set:
   - `USE_METAAPI=true`
   - `METAAPI_TOKEN=<your token>`
   - `METAAPI_ACCOUNT_ID=<account UUID>`
4. Run as usual: `python main.py --mode paper` or `--mode live`. The bot will use MetaApi instead of the local MT5 package.

---

## 2. Configuration and Environment

### 2.1 Config ([config.py](config.py))

| Setting | Description | Default |
|--------|-------------|---------|
| `LIVE_MODE` | `False` = paper, `True` = real money | `False` |
| `MANUAL_APPROVAL` | Require y/n confirmation before each trade | `True` |
| `MAX_TRADES_PER_DAY` | Daily trade limit (in-memory; resets at midnight **local time**) | `5` |
| `MAX_POSITION_SIZE` | Lot size (e.g. 0.01 = micro lot) | `0.01` |
| `PAPER_TRADING_LOG` | JSON file for paper session persistence | `paper_trades.json` |
| `LIVE_CHECK_INTERVAL` | Seconds between strategy runs | `60` |
| `USE_MARGIN_CHECK` | Pre-trade margin check in live mode | `True` |
| `MT5_LOGIN` / `MT5_PASSWORD` / `MT5_SERVER` | From `.env`; server default is **Exness-MT5Trial** | — |
| `USE_METAAPI` | Use MetaApi cloud connector (Mac/Linux or optional on Windows) | `false` |
| `METAAPI_TOKEN` / `METAAPI_ACCOUNT_ID` | From `.env` when `USE_METAAPI=true`; get token at app.metaapi.cloud | — |
| `LIVE_SYMBOLS` | MT5 symbols (e.g. XAUUSD, GBPUSD) | `{'XAUUSD': 'XAUUSD', 'GBPUSD': 'GBPUSD'}` |

#### AI (optional)

| Setting | Description | Default |
|--------|-------------|---------|
| `AI_ENABLED` | Use OpenAI to score signal confidence (1–5); skip trade if below threshold | `False` |
| `AI_CONFIDENCE_THRESHOLD` | Minimum score (1–5) to allow a trade | `2.0` |
| `AI_EXPLAIN_TRADES` | After execution/close, get a short AI explanation of the trade | `False` |

The OpenAI API key is read from `.env` as `OPENAI_API_KEY`. If the key is missing or AI is disabled, the bot runs as before (no API calls).

#### Voice alerts (optional)

| Setting | Description | Default |
|--------|-------------|---------|
| `VOICE_ALERTS` | Enable text-to-speech for trade found / taken / rejected | `False` |
| `VOICE_ALERT_ON_SIGNAL` | Speak when a trade is found and when it is executed | `True` |
| `VOICE_ALERT_ON_REJECT` | Speak when a trade is rejected and why | `True` |

When voice is on, the bot speaks: **trade found** (direction, symbol, reason, “Checking approval”); **trade rejected** (concrete reason: no stop loss, stop loss invalid, insufficient margin, below confidence threshold, daily limit reached, not approved by user); **trade executed** (direction, symbol, price).

### 2.2 Environment (.env)

Create `.env` from [.env.example](.env.example) (never commit `.env`):

```
MT5_LOGIN=your_account_number
MT5_PASSWORD=your_password
MT5_SERVER=Exness-MT5Trial

# Optional: for AI (when AI_ENABLED=True)
OPENAI_API_KEY=...
```

For a real Exness account you may use a server like `Exness-MT5`; override `MT5_SERVER` in `.env` as needed.

---

## 3. Safety Features — What Is Enforced

| Feature | Enforced in code | Where |
|--------|-------------------|-------|
| **Stop loss required** | Yes | [bot/live_trading.py](bot/live_trading.py): `_validate_signal_sl()` rejects signals with missing/invalid SL or SL on wrong side of entry. No order is sent without a valid SL. |
| **Daily trade limit** | Yes | [bot/live_trading.py](bot/live_trading.py): `check_safety_limits()` blocks new trades when trades executed today (by local date) ≥ `MAX_TRADES_PER_DAY`. |
| **Position size** | Yes | Volume is set from `config.MAX_POSITION_SIZE` for every signal. |
| **Manual approval** | Yes (when enabled) | [bot/trade_approver.py](bot/trade_approver.py): prompt with trade details; optional **timeout** (default 60s) — if no response, trade is rejected. |
| **Pre-trade margin check** | Yes (live, when `USE_MARGIN_CHECK=True`) | [bot/live_trading.py](bot/live_trading.py): before placing a live order, compares `calc_required_margin(...)` to `free_margin`; rejects if insufficient. |
| **SL/TP sent to MT5** | Yes | [bot/mt5_connector.py](bot/mt5_connector.py): `place_order` includes `sl` and `tp` when provided. |

**Daily limit note:** “Today” is determined by `datetime.now().date()` (local/server time), not UTC. So the limit resets at **midnight local time** (or the machine’s idea of “today”).

---

## 4. Current Behavior (Important Details)

- **Single symbol:** Only the **first** symbol in `config.LIVE_SYMBOLS` is used for the whole run (e.g. XAUUSD). To trade another symbol, change the order in config or add a `--symbol` option for live mode (not implemented yet).
- **MT5 server default:** If `MT5_SERVER` is not set in `.env`, the code uses **Exness-MT5Trial**. Override in `.env` for real accounts.
- **pdh_pdl in live/paper:** The engine uses the 5m DataFrame only for `ICTStrategy`, computes PDH/PDL from daily data (same logic as backtest), and calls `run_backtest(pdh_series, pdl_series)` so the strategy behaves correctly.

---

## 5. Implementation Status

| Component | File(s) | Status |
|-----------|--------|--------|
| MT5 connection, bars, orders, positions, margin calc | [bot/mt5_connector.py](bot/mt5_connector.py) | Implemented |
| Paper trading (virtual positions, P&L, session log) | [bot/paper_trading.py](bot/paper_trading.py) | Implemented |
| Live engine (loop, strategy, safety, approval, execute) | [bot/live_trading.py](bot/live_trading.py) | Implemented |
| Trade approval with timeout | [bot/trade_approver.py](bot/trade_approver.py) | Implemented |
| Live config and .env | [config.py](config.py), [.env.example](.env.example) | Implemented |
| CLI modes backtest / paper / live | [main.py](main.py) | Implemented |

---

## 6. Testing Plan

- **Phase 1 — Paper (1–2 weeks):** Run all strategies in paper mode (`--mode paper`). Verify signals, safety (daily limit, SL rejection, approval timeout), and simulated P&L. Review `paper_trades.json`.
- **Phase 2 — Live micro lots:** Use 0.01 lots, keep `MANUAL_APPROVAL=True`, limit to 2–3 trades per day. Monitor slippage and spreads.
- **Phase 3 — Scale (if profitable):** Consider gradual position size increase and whether to keep or relax manual approval.

---

## 7. File Structure (Relevant to Live Trading)

```
treading-bot/
├── .env                    # MT5 credentials (gitignored; create from .env.example)
├── .env.example
├── config.py               # Live trading and MT5 settings
├── main.py                 # CLI: --mode backtest | paper | live
├── ai/                     # AI and voice
│   ├── helper.py           # get_signal_confidence, explain_trade (OpenAI)
│   └── voice.py            # speak (pyttsx3)
├── bot/
│   ├── live_trading.py     # LiveTradingEngine, safety checks, SL validation, margin check
│   ├── mt5_connector.py    # MT5 API: connect, bars, orders, margin calc
│   ├── paper_trading.py    # Paper trading simulator
│   ├── trade_approver.py   # Manual approval with timeout
│   ├── replay_engine.py    # Replay live flow on historical data
│   ├── data_loader.py      # Yahoo Finance / CSV
│   ├── indicators.py       # FVG, OB, liquidity sweep, EMA
│   ├── indicators_bos.py   # Swing, BOS, order block
│   ├── strategies/         # Strategy modules (pdh_pdl, liquidity_sweep, h1_m5_bos, confluence)
│   └── backtest/           # Backtest runners per strategy
└── ...
```

See [ONBOARDING.md](ONBOARDING.md) for full architecture and file map.

---

## 8. Risk Warnings

- **Real money at risk:** Live trading involves real financial risk. Only use capital you can afford to lose.
- **Start small:** Use paper mode first, then minimum position sizes (e.g. 0.01 lots).
- **Do not disable stop loss:** All trades must have a stop loss; the bot rejects signals without a valid SL.
