# Real Money Checklist

Complete before running live trading with real funds.

## Pre-Live

- [ ] Paper traded 2+ weeks with target strategy
- [ ] Backtest with spread/commission shows acceptable performance
- [ ] Walk-forward or holdout validation passed (see STRATEGY_VALIDATION.md)
- [ ] `MANUAL_APPROVAL = True` for first live runs
- [ ] `MAX_TRADES_PER_DAY = 2` or 3; `MAX_TRADES_PER_SESSION = 1` (divides limit across London/NY)
- [ ] `.env` has correct MT5 server for real account (not Trial)
- [ ] Position size = 0.01 (or minimum) for first 10–20 trades
- [ ] `LIVE_CONFIRM_ON_START = True` so you explicitly confirm before the loop starts

## Phased Rollout

| Phase | Duration | Config | Goal |
|-------|----------|--------|------|
| Paper | 2 weeks | `LIVE_MODE=False` | Validate signals, safety, TP1/breakeven |
| Live micro | 2–4 weeks | `MANUAL_APPROVAL=True`, 0.01 lot, 2 trades/day | Real fills, slippage, broker behavior |
| Live scaled | After validation | Increase lot, consider `MANUAL_APPROVAL=False` | Scale if profitable |

## Risk Warnings

- Real money at risk. Only use capital you can afford to lose.
- Start small. Use paper mode first, then minimum position sizes.
- Do not disable stop loss. All trades must have a valid SL.
