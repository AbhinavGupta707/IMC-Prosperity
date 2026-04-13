# Optimization Pass 1 — Product-Level Shortlists

## EMERALDS

Under the current local replay / fill model and the tested sweep range,
all 68 EMERALDS configurations produced zero fills and zero PnL.  No
candidates to shortlist beyond baseline.

This does not prove there is no EMERALDS edge on the official site or
under different fill behavior assumptions.

**Decision:** Retain baseline config.  EMERALDS contributes zero delta
to combined finalists.  Do not spend further local sweep budget.

---

## TOMATOES

### Baseline (current production config)

| Metric | Value |
|--------|-------|
| Estimator | weighted_mid |
| PnL | 276.00 |
| Trade count | 16 |
| Entry edge | +0.683 |
| Markout-1 | +1.111 |
| Markout-5 | +1.250 |
| Markout-20 | +0.941 |
| maker_edge | 1.0 |
| taker_edge | 1.0 |
| history_length | 48 |
| Final position | 6 |
| Steps near limit | 0 |

### Candidate 1 — wall_mid (taker=0.5)

| Metric | Value | vs Baseline |
|--------|-------|-------------|
| Estimator | wall_mid | changed |
| PnL | 1499.00 | +1223.00 |
| Trade count | 404 | +388 |
| Entry edge | +0.952 | +0.269 |
| maker_edge | 1.0 | same |
| taker_edge | 0.5 | 1.0 -> 0.5 |
| Final position | -1 | improved |
| Steps near limit | 0 | same |
| Maker share | 0.1% | — |

**Rationale:** Lower taker threshold captures substantially more fills
while maintaining strong entry edge (+0.952) and positive markouts at
all horizons.  wall_mid FV tracks the true value better than
weighted_mid (next-mid MAE 0.647 vs 0.815).  Cross-slice check shows
advantage on both days with no clustering.

### Candidate 2 — wall_mid (taker=1.0, current edges)

| Metric | Value | vs Baseline |
|--------|-------|-------------|
| Estimator | wall_mid | changed |
| PnL | 1296.00 | +1020.00 |
| Trade count | 263 | +247 |
| Entry edge | +1.195 | +0.512 |
| maker_edge | 1.0 | same |
| taker_edge | 1.0 | same |
| Final position | -2 | improved |
| Steps near limit | 0 | same |
| Maker share | 0.2% | — |

**Rationale:** Conservative variant — only the FV method changes.
Fewer fills than Candidate 1 but higher per-fill edge (+1.195).
Serves as a lower-risk option if taker=0.5 turns out to be overfit.

### Candidate 3 — rolling_mid (hist=32, taker=1.5, maker=2.0)

| Metric | Value | vs Baseline |
|--------|-------|-------------|
| Estimator | rolling_mid | changed |
| PnL | 1698.00 | +1422.00 |
| Trade count | 290 | +274 |
| Entry edge | +2.101 | +1.418 |
| maker_edge | 2.0 | 1.0 -> 2.0 |
| taker_edge | 1.5 | 1.0 -> 1.5 |
| history_length | 32 | 48 -> 32 |
| Final position | 1 | improved |
| Steps near limit | 0 | same |
| Maker share | 1.0% | — |

**Rationale:** Highest absolute PnL across all 108 configs.  Wider
maker_edge + wider taker threshold + shorter history produces fewer
but more profitable fills per the entry edge metric.

**Risk flag:** Phase 3 cross-slice showed rolling_mid has markout-1
of only +0.338 (vs wall_mid +1.059).  High entry edge with low
markout suggests PnL may come from aggressive inventory turnover
rather than genuinely cleaner fair value.  Phase 6.5/7 must verify
markout quality for this specific config before promotion.

---

## Phase 5 observations

### wall_mid

- **taker_edge is the dominant parameter.** taker=0.5 averages
  PnL=1404, taker=1.0 averages 1310, taker=1.5 averages 434.
- **maker_edge has minimal effect** (range: 995-1072 across values).
- No history dependency — sweep was only 12 configs.

### rolling_mid

- **history_length=32 is clearly best** (avg PnL=1457 vs 48:1143,
  64:1161, 16:1298).
- **taker_edge=1.5 is slightly best** (avg 1326 vs 1.0:1248, 0.5:1220)
  — counter-intuitive; wider threshold trades less but more profitably.
- maker_edge has modest positive effect at higher values.

### weighted_mid

- Best config: PnL=582 (maker=0.5, taker=0.5), still far below
  wall_mid/rolling_mid.
- Dropped from the final shortlist; dominated by both alternatives.

> **Pre-fix note:** These weighted_mid sweep results were generated
> before the estimator was fixed to respect `config.history_length`
> (it previously hardcoded LOOKBACK=4, making history_length sweeps a
> no-op).  Those results remain part of the historical optimization
> record, but they are not directly comparable to post-fix weighted_mid
> behavior.

### filtered_wall_mid

Not swept.  Identical to wall_mid on tutorial data (2-3 level books).
Implementation retained for future rounds.
