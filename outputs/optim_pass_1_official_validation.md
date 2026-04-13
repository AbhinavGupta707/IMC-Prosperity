# Optimization Pass 1 — Official Validation Guide

## Configs to Validate

### C2 — Promoted Robust Default

**Status:** Currently promoted in `default_engine_config()`.

| Parameter | Baseline | C2 |
|-----------|----------|----|
| fair_value_method | weighted_mid | **wall_mid** |
| fair_value_fallbacks | (mid, microprice) | (mid, microprice) |
| taker_edge | 1.0 | 1.0 |
| maker_edge | 1.0 | 1.0 |
| quote_size | 4 | 4 |
| max_aggressive_size | 8 | 8 |
| inventory_skew | 12.0 | 12.0 |
| flatten_threshold | 0.7 | 0.7 |
| history_length | 48 | 48 |

Only the fair value method changed.  All edge, inventory, and sizing
parameters are identical to baseline.

> **Note:** The baseline uses `weighted_mid`, which was fixed after the
> main optimization pass to respect `config.history_length`.  Earlier
> sweep results for weighted_mid were generated under the old
> implementation (hardcoded LOOKBACK=4) and are not directly comparable
> to post-fix behavior.  Post-fix sanity checks showed a split result:
> fixed `weighted_mid` at h=32 achieved higher raw local PnL (1583 vs
> 1296), while `wall_mid` retained materially stronger markout quality
> (mk1 +1.059 vs +0.661).  `wall_mid` was therefore kept as the
> promoted robust default pending official validation.

### C3 — Higher-Upside Alternate

**Status:** Not promoted.  Preserved as alternate candidate pending
official validation or further neighborhood exploration.

| Parameter | Baseline | C3 |
|-----------|----------|----|
| fair_value_method | weighted_mid | **rolling_mid** |
| fair_value_fallbacks | (mid, microprice) | (mid, microprice) |
| taker_edge | 1.0 | **1.5** |
| maker_edge | 1.0 | **2.0** |
| quote_size | 4 | 4 |
| max_aggressive_size | 8 | 8 |
| inventory_skew | 12.0 | 12.0 |
| flatten_threshold | 0.7 | 0.7 |
| history_length | 48 | **32** |

Four parameters differ from baseline.

## How to Test on the Official Site

### Recommended submission order

1. **Baseline** (weighted_mid) — establishes the reference point
2. **C2** (wall_mid) — promoted config, expected to improve
3. **C3** (rolling_mid) — alternate, may outperform C2 on PnL

To test C3, temporarily modify `default_engine_config()` in
`src/core/config.py`:

```python
"TOMATOES": ProductConfig(
    position_limit=80,
    strategy_name="market_making",
    fair_value_method="rolling_mid",      # C3
    fair_value_fallbacks=("mid", "microprice"),
    taker_edge=1.5,                       # C3
    maker_edge=2.0,                       # C3
    quote_size=4,
    max_aggressive_size=8,
    inventory_skew=12.0,
    flatten_threshold=0.7,
    history_length=32,                    # C3
),
```

Revert after testing.

### Metrics to record when official results come back

For each config submission, record everything observable.  Prioritize
in this order (per the evaluation rules in CLAUDE.md):

| Priority | Metric | Notes |
|----------|--------|-------|
| 1 | Total PnL | Primary ranking signal |
| 2 | Per-product PnL | Check for cross-product interaction |
| 3 | Trade count | Proxy for fill rate / aggressiveness |
| 4 | Final position | Inventory health at end of round |
| 5 | Any signs of instability | Large drawdowns, position spikes, unusual exposure |
| 6 | Repeatability | If multiple official runs are possible, check ranking consistency |

Entry edge and markouts are not directly observable on the official
site, but trade count + PnL together serve as a rough proxy for
fill quality.

### Key comparisons

1. **C2 vs Baseline:** Does wall_mid outperform weighted_mid on the
   official site?  Local replay showed +1020 PnL improvement.  Any
   positive delta confirms the direction.

2. **C3 vs C2:** Does rolling_mid's higher aggressiveness produce
   better PnL on the official site?  Local replay showed C3 at +1698
   vs C2 at +1296, but with lower markout quality.  If C3 outperforms
   on the official site, it may justify promotion in a future pass,
   but re-evaluate markout quality first.

3. **C2 vs Baseline on EMERALDS:** Verify EMERALDS is unaffected.
   The TOMATOES config change should not alter EMERALDS behavior, but
   confirm zero regression.

4. **Relative ranking stability:** If multiple official runs are
   possible, check whether the C2 > baseline ranking holds
   consistently, or whether it flips across runs.  A single-run
   advantage is weaker evidence than a repeatable one.

### Interpretation guidance

- If C2 outperforms baseline: the wall_mid promotion is validated.
- If C2 underperforms baseline: the local replay fill model may differ
  from the official exchange.  Revert the promotion and investigate
  fill model assumptions.
- If C3 outperforms C2: the rolling_mid aggressiveness is rewarded by
  the official fill model.  Consider promoting C3 in a future pass,
  but re-evaluate markout quality first.
- If results are inconsistent across runs: the advantage may be
  noise-level.  Increase sample size before drawing conclusions.
- Do not draw conclusions about EMERALDS from TOMATOES results.
