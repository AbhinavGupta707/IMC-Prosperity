# IMC Prosperity Trading Bot

## Project Structure

- `src/core/` — engine modules (signals, risk, fair_value, config, execution)
- `src/backtest/` — replay, simulator, metrics, sweeps, comparison
- `src/scripts/` — runners for review, sweeps, comparisons
- `tests/` — pytest suite (unit + integration)
- `data/raw/tutorial_round_1/` — replay data
- `outputs/` — review packs, sweep results, comparison reports

## Running

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/ -v
PYTHONPATH=. .venv/bin/python -m src.scripts.run_review --label baseline
```

## Evaluation Rules

### Evidence calibration

- Do not make categorical claims from local replay when fill behavior
  or simulator behavior may differ from the official environment.
- Phrase conclusions proportionally to the evidence:
  - "under the current local replay / tested range"
  - not "inherent" or "cannot be fixed" unless truly proven.

### Large-jump sanity checks

- When a new estimator or config shows a large aggregate improvement,
  run a quick cross-slice sanity check and a lightweight visual /
  timestamp review before spending more tuning budget around it.
- Do not assume a large aggregate gain is automatically robust.

### Redundant estimator handling

- If two estimators behave identically on the current dataset, keep
  both implementations if strategically useful, but treat one as
  redundant for the current sweep budget.
- Do not waste sweep capacity on estimator duplicates.

### Evaluation priority

In trading strategy evaluation, prioritize:

1. realized PnL
2. entry edge / markouts
3. inventory behavior
4. cross-slice robustness

Do not over-weight pure forecast-style metrics like MAE when trading
outcomes disagree.
