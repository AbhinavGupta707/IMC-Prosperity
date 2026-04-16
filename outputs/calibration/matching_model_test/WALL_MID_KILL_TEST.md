# Matching-model bias test — does the wall_mid kill survive scrutiny?

**Question** (from adversarial review): the wall_mid family (F2d, F3c,
F3d, F2b) won officially in Phase F at +263 to +308 over baseline.
MC says they all lose money in expectation. Is MC biased against
wall_mid because of the bot-priority matching assumption, or is
"wall_mid was officially lucky" a fair characterization?

**Method**: re-run all 6 cohort variants under TWO matching modes:
1. `priority_mode=bot` (default): bot inventory has time priority at
   every price level; player passive only fills the leftover.
2. `priority_mode=player`: player passive fills FIRST, before bot
   inventory at the same price. If MC's wall_mid kill is driven by
   the bot-priority assumption, this should change the verdict.

100 sessions per (variant, mode) on round-1 ASH calibration.

## Results

| Variant | bot-priority median | player-priority median | Δ | Verdict |
|---|---:|---:|---:|---|
| **F3a** | **+421** | **+421** | 0 | Identical |
| F2c | +374 | +374 | 0 | Identical |
| F2d | -95 | -95 | 0 | Identical |
| F3c | -112 | -101 | +11 | Within noise |
| F3d | -209 | -209 | 0 | Identical |
| F2b | -271 | -259 | +12 | Within noise |

Differences are at most +12 PnL on a per-session std of ~270.
Statistically: zero.

## Verdict

**The wall_mid kill is NOT a bot-priority artifact.** Switching to
the most player-favorable matching model leaves the verdict
unchanged. F2d/F3c/F3d/F2b have negative MC median PnL **under
both matching assumptions**.

This eliminates one of the two competing explanations from the
review. We're left with two possibilities, in order of likelihood:

1. **MC is missing some OTHER microstructure feature wall_mid
   exploits** that we haven't tested for. Possible candidates:
   - Multi-tick price-impact dynamics (synthetic trades all print
     at one tick; real trades may push prices over multiple ticks)
   - Cross-product effects (we MC ASH-only; wall_mid might exploit
     ASH-PEPPER correlation)
   - Bot-quote refreshes within a single tick (synthetic books
     are static between ticks; real bots may re-quote intra-tick)

2. **The 4 wall_mid variants caught the same lucky tail-realization
   on day 0**. Their official PnLs ARE correlated (they share the
   same FV-estimator family), so this is essentially "they all got
   lucky once" — low base-rate prior, but not impossible.

## Probability assessment (subjective)

After this test:
- P(wall_mid family is officially lucky on day 0): now ~55%
  (was ~50% before this test)
- P(MC is missing a microstructure feature wall_mid exploits): ~40%
  (was ~50%)
- P(other unmodeled mechanism): ~5%

The matching-model variant test moved the needle slightly toward
"officially lucky" but the outcome is still ambiguous — the test
ruled out ONE possible MC bias, not all of them.

## Recommendation for round 2

Given this remains ambiguous:

- **Do not ship a wall_mid variant as the headline ASH strategy** —
  MC says it loses in expectation under multiple matching
  assumptions, AND F3a's MC verdict is positive under multiple
  matching assumptions.
- **Carry one wall_mid variant as a hedge candidate** if submission
  slots permit. The cost of the hedge is one slot; the upside is
  protection if round-2 day-0 microstructure happens to favor
  wall_mid the way round-1 day-0 apparently did.
- **Don't spend further build budget** on additional matching-model
  variants for round 1. The remaining ambiguity (~40-55%) reflects
  genuine uncertainty about microstructure, not a fixable model
  bug. Round-2 day-1 hold-1 calibration will provide the next data
  point that meaningfully shifts the prior.

## Files

- `bot/<variant>/{report.md, per_session.csv, raw_results.json}` —
  cohort results under bot-priority matching (default).
- `player/<variant>/{report.md, per_session.csv, raw_results.json}` —
  cohort results under player-priority matching (test variant).
- `WALL_MID_KILL_TEST.md` — this file.
