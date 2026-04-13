# Optimization Pass 1 — Finalist Review Notes

## Candidate C1: wall_mid (taker=0.5, maker=1.0)

### What improved vs baseline

- PnL: 276 -> 1499 (+1223)
- Trades: 16 -> 404 (+388)
- Entry edge: +0.683 -> +0.952
- Markout-1: +0.693 -> +0.829
- Final position improved: 6 -> -1

### What got worse

- Markout quality slightly lower than C2 at longer horizons (mk20: +0.731 vs +0.946)
- taker_edge=0.5 sits at grid boundary (lowest tested value) — possible overfit risk

### Edge quality assessment

Gains come from genuine edge — all markouts positive on both days:

| Day | mk1 | mk5 | mk20 |
|-----|-----|-----|------|
| -2 | +0.829 | +0.868 | +0.636 |
| -1 | +0.843 | +0.928 | +0.913 |

No suspicious timestamp clustering (263 trades across 259 distinct 100-step buckets in the wall_mid early review).

### Cross-product interaction

EMERALDS unaffected (zero fills under local replay regardless of TOMATOES config).

---

## Candidate C2: wall_mid (taker=1.0, maker=1.0) — PROMOTED

### What improved vs baseline

- PnL: 276 -> 1296 (+1020)
- Trades: 16 -> 263 (+247)
- Entry edge: +0.683 -> +1.195
- All markouts improved and strongly positive
- Final position improved: 6 -> -2

### What got worse

Nothing.  Lower PnL than C1 and C3, but that is a trade-off for higher per-fill quality, not a regression.

### Edge quality assessment

Best markout quality of all candidates — gains come from genuinely better fair value estimation, not from higher trade volume:

| Day | mk1 | mk5 | mk20 |
|-----|-----|-----|------|
| -2 | +1.065 | +1.133 | +0.891 |
| -1 | +1.040 | +1.124 | +1.072 |

All markouts positive and consistent across days.  No degradation at longer horizons.

### Cross-product interaction

EMERALDS unaffected.

### Why promoted over C1 and C3

- Zero grid boundary warnings (taker=1.0 and maker=1.0 are internal to all tested grids)
- Best markout quality at all horizons
- Simplest change: only fair_value_method changes (weighted_mid -> wall_mid)
- Robust improvement present on both days
- Lower overfit risk: no edge parameters changed from production defaults

---

## Candidate C3: rolling_mid (taker=1.5, maker=2.0, hist=32)

### What improved vs baseline

- PnL: 276 -> 1698 (+1422) — highest absolute PnL
- Trades: 16 -> 290 (+274)
- Entry edge: +0.683 -> +2.101

### What got worse

- Markout quality notably weaker than wall_mid variants:

| Day | mk1 | mk5 | mk20 |
|-----|-----|-----|------|
| -2 | +0.543 | +0.776 | +0.584 |
| -1 | +0.651 | +0.832 | +0.884 |

- Two parameters at grid boundary (taker=1.5 at top, maker=2.0 at top)

### Edge quality assessment

High entry edge (+2.101) with markedly lower markout-1 (+0.627 in
the full continuous replay; per-day values differ slightly because
per-day runs start with fresh state and produce different trade
populations) suggests PnL comes partly from aggressive inventory
turnover rather than genuinely cleaner fair value.  rolling_mid's
94.6% value-change frequency (vs wall_mid's 42.9%) means it generates
many more taker signals, some of which are adverse.

### Why not promoted

- Two grid boundary parameters (overfit risk)
- Markout quality gap vs wall_mid is large and consistent across days
- Economic explanation for improvement is weaker ("more aggressive" vs "better FV")
- Recommended for Phase 2 investigation: expand grid boundaries, analyze inventory path, test whether gains survive at lower aggressiveness
