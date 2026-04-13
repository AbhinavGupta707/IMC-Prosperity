# Optimization Pass 1 — Run Manifest

## Branch

`optimisation` (from `codex-phase1-6-cleanup`)

## Dataset

```
data/raw/tutorial_round_1/prices_round_0_day_-2.csv
data/raw/tutorial_round_1/prices_round_0_day_-1.csv
data/raw/tutorial_round_1/trades_round_0_day_-2.csv
data/raw/tutorial_round_1/trades_round_0_day_-1.csv
```

Products: EMERALDS, TOMATOES.  Two days: day -2, day -1.

## Phase 1 — Legality + Inventory Behavior Tests

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_signals.py tests/test_risk.py -v
```

Added 36 tests for limit=80 (EMERALDS skew=8.0/flatten=0.75, TOMATOES skew=12.0/flatten=0.70).
Long + short positions, symmetry, risk clipping boundaries.

## Phase 1.5 — Synthetic High-Inventory Stress Tests

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_signals.py -k "stress or monotonicity or dead_zone or recovery_unwind" -v
```

22 tests: full pipeline legality across 13 positions, skew monotonicity, no dead zone, recovery aggressiveness.

## Phase 2 — New Fair-Value Estimators

Added `wall_mid`, `filtered_wall_mid`, `hybrid_wall_micro` to `src/core/fair_value.py`.
Registered in `ESTIMATORS` and `KNOWN_ESTIMATOR_NAMES`.
11 new tests in `tests/test_fair_value.py`.

## Phase 3 — TOMATOES Fair-Value Comparison

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.run_fair_value_compare --label optim_tomatoes_fv
```

9 estimators compared.  Output: `outputs/fair_value_comparison/20260413T174430Z_optim_tomatoes_fv/`

**Shortlist rationale:**
- wall_mid: Best PnL (1296), best MAE, positive markouts on both days
- filtered_wall_mid: Identical to wall_mid on tutorial data (thin books) — excluded from sweeps
- rolling_mid: Second-best PnL (1188) but poor markout quality — included with risk flag

## Phase 4 — EMERALDS Staged Sweep

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.run_emeralds_sweep --label optim_emeralds
```

68 configs (20 Stage A + 48 Stage B).  All produced zero fills under local replay.
Output: `outputs/sweeps/20260413T1745*_optim_emeralds_*/`

## Phase 5 — TOMATOES Estimator-Aware Sweep

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.run_tomatoes_fv_sweep --label optim_tomatoes_fv_sweep
```

108 configs (12 wall_mid + 48 rolling_mid + 48 weighted_mid).
Output: `outputs/sweeps/20260413T*_optim_tomatoes_fv_sweep_*/`

**Key finding:** wall_mid taker_edge is the dominant parameter.  rolling_mid history_length=32 is optimal.  weighted_mid history_length has zero effect (hardcoded LOOKBACK=4).

## Phase 6 — Product-Level Shortlists

Written to `outputs/optim_pass_1_shortlists.md`.

**EMERALDS:** Baseline only.
**TOMATOES:**
- C1: wall_mid (taker=0.5, maker=1.0) — PnL=1499
- C2: wall_mid (taker=1.0, maker=1.0) — PnL=1296
- C3: rolling_mid (hist=32, taker=1.5, maker=2.0) — PnL=1698

## Phase 6.5 — Combined Finalist Pairings

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.run_combined_finalists
```

3 pairings tested (EMERALDS baseline x 3 TOMATOES candidates).

## Phase 7 — Review Packs

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.run_candidate_review --no-charts
```

Review packs generated in `outputs/review_packs/`.
Interpretation notes: `outputs/optim_pass_1_review_notes.md`.

## Phase 8 — Promotion Gate

**Promoted:** C2 (wall_mid, taker=1.0, maker=1.0)

All 6 criteria passed with zero warnings.  See `outputs/optim_pass_1_promotion.md` for full gate results.

**Config diff:**
```python
# TOMATOES only change:
fair_value_method: "weighted_mid" -> "wall_mid"
# All other parameters unchanged.
```

## Phase 9 — Commit Hygiene

401 tests passing after promotion.

## Follow-Up Pass

### weighted_mid / history_length fix

`WeightedMidEstimator` previously hardcoded `LOOKBACK = 4`, ignoring
`config.history_length`.  Fixed to read from config so parameter sweeps
are meaningful.  Regression test added.

> **Historical cutoff:** All weighted_mid sweep results in Phases 3-6
> were generated under the old implementation and are historically
> informative but not directly comparable to post-fix behavior.

### Post-fix weighted_mid sanity check

After fixing the estimator, a narrow sanity check compared wall_mid
(promoted) against fixed weighted_mid at several history_length values:

| Config | PnL | Trades | Edge | mk1 | mk5 | mk20 | Pos |
|--------|-----|--------|------|-----|-----|------|-----|
| wall_mid (promoted) | 1296 | 263 | +1.195 | +1.059 | +1.120 | +0.946 | -2 |
| weighted_mid h=4 | 276 | 16 | +0.683 | +0.693 | +0.710 | +0.216 | 6 |
| weighted_mid h=16 | 904 | 208 | +1.250 | +0.838 | +1.022 | +0.775 | 0 |
| weighted_mid h=32 | 1583 | 313 | +1.488 | +0.661 | +0.854 | +0.784 | 5 |
| weighted_mid h=48 | 1322 | 348 | +1.734 | +0.594 | +0.735 | +0.654 | -2 |
| weighted_mid h=64 | 1297 | 361 | +1.939 | +0.474 | +0.650 | +0.642 | -7 |

**Findings:**

- h=4 reproduces the old behavior exactly (PnL=276), confirming the fix.
- **Surprise:** fixed weighted_mid at h=32 reaches PnL=1583, exceeding
  wall_mid (1296).  The earlier conclusion that "weighted_mid is clearly
  behind wall_mid" no longer holds for the fixed version.
- However, wall_mid retains substantially better markout quality
  (mk1=+1.059 vs +0.661).  The weighted_mid PnL advantage comes from
  more aggressive trading (313 vs 263 fills) with lower per-fill quality.
- h=32 is optimal for weighted_mid, matching the rolling_mid finding.

**Decision:** C2 (wall_mid) remains the promoted default because its
markout quality advantage is large and consistent.  Fixed weighted_mid
at h=32 is flagged as a **new alternate candidate** for investigation
in a future pass, alongside C3.  No auto-promotion.

### C3 alternate preserved

C3 (rolling_mid, hist=32, taker=1.5, maker=2.0) documented as a live
alternate candidate in promotion notes and official validation guide.

### Regression guard

Integration test added: `test_trader_tomatoes_wall_mid_default_produces_orders`
verifies the promoted default config runs end-to-end.

### Official validation

Guide written: `outputs/optim_pass_1_official_validation.md` with exact
config diffs, submission order, and metrics to compare for C2 and C3.
