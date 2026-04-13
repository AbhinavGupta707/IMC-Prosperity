# Optimization Pass 1 — Promotion Decision

## Executive Summary

TOMATOES fair value method promoted from `weighted_mid` to `wall_mid`.
This single change improves total PnL from 276 to 1296 (+1020) on the
tutorial replay by using the midpoint of the largest bid/ask levels as
the fair value estimate instead of a recency-weighted mid average.  The
improvement is present on both replay days, driven by genuinely positive
markouts at all horizons, with no inventory pathology or grid boundary
concerns.  EMERALDS config is unchanged (zero fills under the current
local replay / fill model).

## Exact Changes Made

| File | Change |
|------|--------|
| `src/core/config.py` | TOMATOES `fair_value_method`: `"weighted_mid"` -> `"wall_mid"` |
| `tests/test_config.py` | Updated default config test assertion to match |

One line of production config, one line of test.  No edge parameters,
inventory parameters, or strategy logic changed.

## Metrics Table: Before / After

### Combined (both days)

| Metric | Before (weighted_mid) | After (wall_mid) | Delta |
|--------|----------------------|-------------------|-------|
| Total PnL | 276.00 | 1296.00 | +1020.00 |
| TOMATOES PnL | 276.00 | 1296.00 | +1020.00 |
| EMERALDS PnL | 0.00 | 0.00 | 0.00 |
| Trade count | 16 | 263 | +247 |
| Entry edge | +0.683 | +1.195 | +0.512 |
| Markout-1 | +0.693 | +1.059 | +0.366 |
| Markout-5 | +0.710 | +1.120 | +0.410 |
| Markout-20 | +0.216 | +0.946 | +0.730 |
| Final position | 6 | -2 | improved |
| Steps near limit | 0 | 0 | same |

### Per-day TOMATOES

| Day | Before PnL | After PnL | Delta | After mk1 | After mk5 | After mk20 |
|-----|-----------|-----------|-------|-----------|-----------|------------|
| -2 | 225.00 | 952.50 | +727.50 | +1.065 | +1.133 | +0.891 |
| -1 | -56.00 | 454.00 | +510.00 | +1.040 | +1.124 | +1.072 |

## Promotion Methodology Note

Raw PnL ranking was used for search and shortlisting throughout this
pass.  However, the final promotion decision can prefer a lower-PnL
candidate when:

- markout quality is materially better (genuine edge vs aggressive turnover)
- overfit risk is lower (no parameters at grid boundary)
- the change is simpler and more interpretable (fewer parameter diffs)
- cross-slice behavior is cleaner and more consistent

C2 was promoted over C3 (higher PnL) and over post-fix weighted_mid
h=32 (also higher PnL) because C2 had the best markout quality at
all horizons, zero grid boundary warnings, and the simplest possible
change (only the FV method differs from baseline).  This is a
deliberate risk-aware choice, not an oversight of the PnL ranking.

## Promotion Gate Results

| # | Criterion | Result | Notes |
|---|-----------|--------|-------|
| 1 | Improved PnL | PASS | +1020 total |
| 2 | No legality issues | PASS | 401 tests pass including Phase 1/1.5 |
| 3 | No inventory pathology | PASS | Final pos=-2, near_limit=0 |
| 4 | Understandable economic reason | PASS | wall_mid tracks true value better (MAE 0.647 vs 0.815) |
| 5 | Cross-slice robustness | PASS | Improvement on both days, no regression |
| 6 | No obvious overfit | PASS | Zero grid boundary warnings; taker=1.0, maker=1.0 both internal |

## Rejected Alternatives

### C1: wall_mid (taker=0.5)

- PnL=1499 (+1223 vs baseline) — higher than promoted config
- Rejected because taker_edge=0.5 sits at the bottom grid boundary
- Markouts slightly lower than C2 at longer horizons
- Recommended for Phase 2: expand taker_edge grid below 0.5 to test if the boundary is real or overfit

### C3: rolling_mid (hist=32, taker=1.5, maker=2.0) — LIVE ALTERNATE

**Status: Not promoted, but preserved as a serious alternate candidate.**

- PnL=1698 (+1422 vs baseline) — highest absolute PnL of all tested configs
- Not promoted in this pass because:
  - Two parameters at grid boundary (taker=1.5 at top, maker=2.0 at top)
  - Markout quality notably weaker (mk1=+0.627 vs promoted +1.059)
  - PnL improvement appears partly driven by aggressive inventory turnover
- **Why C3 remains interesting:**
  - Highest raw PnL across all 108+ tested configurations
  - Positive markouts on both days (just lower than wall_mid)
  - Cross-slice robust (positive improvement on both day -2 and day -1)
  - If official site fill model rewards aggressiveness more than local
    replay, C3 may outperform C2
- **Next steps for C3:**
  - Test on official site alongside C2 (see `optim_pass_1_official_validation.md`)
  - If official results favor C3, expand grid beyond current boundaries
    and re-evaluate markout quality before promotion

### weighted_mid (current baseline)

- Best tuned config: PnL=582 (maker=0.5, taker=0.5)
- Still dominated by wall_mid at the same edge parameters

> **Pre-fix note:** The weighted_mid sweep results in this pass were
> generated before the estimator was fixed to respect
> `config.history_length` (it previously hardcoded LOOKBACK=4).  Those
> results remain part of the historical optimization record, but they
> are not directly comparable to post-fix weighted_mid behavior.  A
> narrow post-fix sanity check confirmed wall_mid still clearly
> outperforms — see `optim_pass_1_run_manifest.md`.

### filtered_wall_mid

- Identical results to wall_mid on tutorial data (2-3 level books)
- Not separately swept; kept in code for future rounds with deeper books

## Remaining Risks

1. **Local replay fidelity:** The tutorial fill model may differ from the
   official exchange.  wall_mid's advantage is validated under local replay
   only.  This does not guarantee the same improvement on the official site.

2. **Thin book sensitivity:** wall_mid picks the largest-volume level on
   each side.  On 2-3 level books this works well; on deeper books the
   "wall" concept may behave differently.

3. **EMERALDS is untested:** Zero fills under local replay prevents any
   EMERALDS optimization.  Re-evaluate after site-side results.

4. **taker_edge frontier:** C1 (taker=0.5) showed higher PnL.  The
   current promotion conservatively keeps taker=1.0.  Phase 2 should
   investigate whether taker<1.0 is a genuine improvement or overfit.

5. **rolling_mid potential:** C3 showed the highest raw PnL.  If its
   markout quality can be improved through less aggressive edges or
   different history lengths, it could outperform wall_mid.

6. **Fixed weighted_mid at h=32:** A post-fix sanity check revealed
   that weighted_mid with history_length=32 reaches PnL=1583,
   exceeding wall_mid (1296).  However, its markout quality is notably
   lower (mk1=+0.661 vs +1.059).  This makes it a new alternate
   candidate alongside C3, warranting investigation in a future pass.
   The earlier conclusion that "weighted_mid is clearly behind
   wall_mid" applied only to the pre-fix version (hardcoded LOOKBACK=4).

## Recommended Next Move (Pass 2)

1. **Taker-edge frontier:** Sweep taker_edge in [0.3, 0.4, 0.5, 0.6, 0.7]
   for wall_mid to determine if the C1 boundary advantage is real.

2. **rolling_mid deep dive:** Expand the rolling_mid grid beyond current
   boundaries, specifically analyze inventory path and markout quality
   per aggressiveness level.

3. **Site-side validation:** Run the promoted config on the official
   platform and compare PnL / fill behavior against local replay
   expectations.

4. **EMERALDS re-assessment:** If site-side EMERALDS shows any fills,
   revisit the EMERALDS sweep with adjusted expectations.

## Branch and Artifacts

- **Branch:** `optimisation`
- **Promoted config change:** `src/core/config.py` TOMATOES fair_value_method: weighted_mid -> wall_mid
- **Review packs (on disk, not committed):** `outputs/review_packs/`
- **Sweep outputs (on disk, not committed):** `outputs/sweeps/`, `outputs/fair_value_comparison/`
