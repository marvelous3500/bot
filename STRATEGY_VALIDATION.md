# Strategy Validation Guide

Steps to validate strategies before live trading.

## 1. Backtest with Realism

Enable spread and commission in `config.py`:

```python
BACKTEST_SPREAD_PIPS = 2.0       # e.g. 2 for gold
BACKTEST_COMMISSION_PER_LOT = 7.0  # round-trip per lot
BACKTEST_SLIPPAGE_PIPS = 0.5
```

Run backtest and compare to zero-spread results:

```bash
python main.py --mode backtest --strategy kingsely_gold --symbol "GC=F"
```

## 2. Walk-Forward Analysis

Run walk-forward to check if the strategy holds up on unseen data:

```bash
python scripts/walk_forward.py --strategy kingsely_gold --symbol "GC=F" --train-days 30 --test-days 14 --step-days 14
```

Interpretation: Test return should be within a reasonable range of train return. Large degradation suggests overfitting.

## 3. Holdout Validation

Use last 20% of data as holdout:

```bash
python scripts/walk_forward.py --strategy kingsely_gold --symbol "GC=F" --holdout 20
```

Criteria: Holdout win rate within ~10% of train win rate; holdout return positive or acceptable.

## 4. Parameter Sweep Across Periods

Run sweep with different periods to check robustness:

```bash
# Edit scripts/sweep_kingsley.py to add --period or run with different BACKTEST_PERIOD
# Compare 12d vs 60d: configs that work in both are more robust
```

## 5. Paper Trading

Run paper mode for 2+ weeks with `MANUAL_APPROVAL=True`:

```bash
python main.py --mode paper --strategy kingsely_gold
```

Compare paper win rate and behavior to backtest. Reject trades that fail your eye test.

## 6. Validation Checklist

- [ ] Backtest with spread/commission shows acceptable performance
- [ ] Walk-forward: test return not severely degraded vs train
- [ ] Holdout: win rate within ~10% of train
- [ ] Paper traded 2+ weeks; signals align with manual analysis
- [ ] Ready for live with MANUAL_APPROVAL and small lot size
