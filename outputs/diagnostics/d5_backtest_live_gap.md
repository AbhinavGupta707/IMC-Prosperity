# D5 — Backtest vs Live Gap + Plateau Analysis

## Local backtest vs official test-upload scores

Local backtest (wide_w113 sweep winner) claimed +20% over L1 baseline.
Official test uploads (4 runs each, 1 day × 1k snapshots) reveal the opposite.

| Variant | Local backtest (3-day ASH) | Official mean (total) | Official σ | Official runs |
|---|---|---|---|---|
| Promoted | — | 7,654 | 366 | 4 |
| Ash L1 | ASH 9,847 (3d) → ~3,282/d | 7,952 | 248 | 4 |
| Killswitch | — | 7,812 | 166 | 4 |
| v5 | — | 7,972 | 442 | 4 |

## Live ranking vs backtest ranking

1. **v5** — live mean 7,972
2. **Ash L1** — live mean 7,952
3. **Killswitch** — live mean 7,812
4. **Promoted** — live mean 7,654

## Key findings

- **Promoted (wide_w113) live mean = 7,654**. L1 baseline live mean = **7,952**.
- **The 'winner' we shipped actually UNDERPERFORMED the baseline on live tests by ~4%.**
- All four configs cluster in 7,654–7,972 range — within noise σ ≈ 300.
- Expected per-test value was ~9,000 (from scaled R1 anchor). Actual mean ~7,850.
  That's a **~13% absolute shortfall** vs the backtest-scaled expectation.

## Implications for F7 (fill-model mismatch)

**F7 is confirmed as the DOMINANT failure mode.** The backtest fill model
(passive_allocation=0.3) over-predicted P&L by 13%+ AND reversed the sweep ranking.
This means:

1. The sweep winner we shipped is not actually the live optimum.
2. Every other R2 tuning decision (kill-switch ablation, residual gate,
   MAF bid calibration) was made on biased numbers and is suspect.
3. For R3-5: before ANY tuning, we must recalibrate `passive_allocation`
   to match observed live fills. Every historical sweep result is
   provisional until this is done.

## Implications for F8 (plateau selection)

This reframes F8: the plateau vs peak gap is not the issue — the entire
sweep landscape is shifted. Even picking the 'stable neighborhood' winner
doesn't help when the neighborhood itself is measured in a biased fill regime.

## What D5 did NOT resolve

- Top-team claimed 11-12k on 'the same sample data set' — unclear whether
  they measured on their own backtest (biased, like ours) or in live tests.
  If backtest: gap is 20-25% in backtest numbers. If live: gap is larger.
- We need to run at least ONE top-team P3 repo through our fill model at
  various passive_allocation values and see which value reproduces their
  published live number. That tells us the TRUE fill allocation.
