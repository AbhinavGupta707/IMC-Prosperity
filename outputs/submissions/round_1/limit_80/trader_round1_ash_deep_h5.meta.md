# H5 — slow-FV test (ewma τ=500 + linear skew c=2)

**Upload label:** H5 (Phase-H hidden-pattern test).
**Factory:** `round1_ash_deep_h5_engine_config`.
**Inlined research:** `ash_shape_override.py` with `skew_coef=2.0`.

## Purpose

Phase-H investigation (`outputs/round_1/ash_deep_dive/phase_h/
PHASE_H_HIDDEN_PATTERN.md`) identified ASH as an OU process with
half-life ~2 ticks around a slowly-drifting fair value near 10 000.
Roll (1984) decomposition shows fundamental vol is ~0; essentially
all observed mid-tick noise is bid-ask bounce.

F3a (shipped winner) uses weighted_mid as FV — this tracks the OU
**state** (mid + book-imbalance correction). H5 replaces it with
ewma τ=500 which tracks the OU **mean** instead. Theory predicts
the slower anchor captures more edge per fill.

## Config

- ASH: strategy=`ash_shape_override`, fv=`ewma_mid` (α≈0.002,
  τ=500), history_length=2000, m=2.5, t=0.5.
- PEPPER: `buy_and_hold`, max_aggressive_size=80.
- ShapeParams: `skew_mode="linear"`, `skew_coef=2.0`,
  `flatten_mode="hard"`, `flatten_threshold=0.7`,
  `size_mode="constant"`.

## Local numbers (Phase-H sweep)

| | local 3-day mean | maker | taker | markout_1 | exp_off |
|---|---:|---:|---:|---:|---:|
| F3a (reference) | +3 446 | 5 | 701 | ~+0.5 | — |
| **H5 (τ=500 c=2)** | **+1 908** | 25 | 884 | +0.60 | **+1 639** |
| H1 (τ=200 c=2) | +2 617 | 15 | 830 | +1.17 | +1 542 |
| H0a (τ=10 c=2) | +3 345 | 3 | 677 | +2.06 | +735 |

**The ambiguity this upload resolves:**
- Local mean says slow-FV loses (−1 538 vs F3a on 3-day).
- Phase-A fill-scaled exp_off says slow-FV wins (+244 vs F3a
  observed +1 395).
- The local sim under-fires maker fills by ~28×; H5's 5× higher
  maker share could dominate in the official fill model.
- Markout_1 is 20% higher than F3a — each fill is more profitable.

## Fingerprint

| | Value |
|---|---|
| Size | 88 331 bytes |
| SHA-256 | `db77893eada405dca2022e2c0486923e67ed0954f2069b0e2dc76250f5a382e7` |
| Validator | 0 errors, 1 warning (size over soft-budget, under hard) |

## Hypothesis / risks

**Hypothesis:** slow-FV anchoring is strictly better than mid-tracking
because the OU half-life is 2 ticks — quotes anchored to a slowly-
drifting mean will disproportionately catch fills on the favourable
side of the reversion trade.

**Risk:** the Phase-F empirical transfer ratio (0.42) was measured on
variants using weighted_mid / wall_mid only. Applying it to slow-FV
gives H5 official ≈ +801 (loses). The fill-scale exp_off trusts the
theoretical fill-scale multiplier; the empirical ratio trusts
real upload evidence. They disagree by ~840 ticks.

**If H5 beats F3a:** slow-FV hypothesis confirmed. Next upload: H0c
(τ=100 c=2, local +2 995) or H4 (τ=500 c=1, local +1 981) to find
the optimum τ.
**If H5 underperforms F3a:** the fill-scale model was misleading
for slow-FV; weighted_mid's faster response is the true winner;
F3a is confirmed optimal and ASH tuning stops.

## Build

```
PYTHONPATH=. .venv/bin/python -m src.scripts.round_1.export_round1_ash_deep_h5
```
