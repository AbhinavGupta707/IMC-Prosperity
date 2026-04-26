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

## Algorithmic research memory from Round 3

Full postmortem:
`docs/round_3/ROUND_3_ALGO_POSTMORTEM_AND_PLAYBOOK.md`.

### Asset geometry first

Before tuning any new product, classify its payoff geometry: delta-one,
option/convexity, basket/spread, conversion/settlement, auction/rank,
hidden bot/liquidity, or inventory liquidation. Build state variables,
oracles, and PnL attribution around that geometry before optimizing
parameters.

### Options need Greek-aware attribution

For option products, evaluate spot, strike, TTE, IV, realized volatility,
delta, gamma, vega, theta, hedge cost, smile residuals, and settlement
mark behavior. Raw voucher price thresholds are not enough. Do not
reject volatility/gamma alpha from a naive rolling-IV or smile prototype
unless the prototype implements proper delta hedging and Greek PnL
decomposition.

### Hardcode structure, not path

Hardcoding inferred bot behavior, IV curve parameters, hedge ratios, and
regime thresholds from public data is valid research. Do not hardcode
future prices, exact timestamp position maps, external/non-public data,
or platform-bug behavior.

### Official uploads are calibration experiments

Use official simulator uploads to isolate mechanisms: long-gamma,
short-gamma, delta-neutral smile residuals, synthetic hedge behavior,
stale quote capture, and terminal-settlement exposure. Do not treat
every upload only as a leaderboard-maximization attempt.
