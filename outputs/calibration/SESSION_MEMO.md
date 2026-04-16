# Calibration & Monte-Carlo session memo — 2026-04-16

**Branch**: `calibration-tooling`
**Goal**: build full calibration → audit → Monte Carlo pipeline; deliver
F3a verdict; produce reusable infra for round 2.

## CRITICAL CAVEAT (added after adversarial review)

The pipeline is solid engineering. The verdicts in this memo were
initially overstated relative to what n=1 day of calibration data can
support. Read MC_VERDICT.md (v2) for the calibrated language. Top
issues uncovered in review:

- The "100 MC sessions" are 100 re-orderings of one day's
  microstructure. They measure within-day path noise, not across-day
  variance. Win-rate 93% is conditional on day-0's regime.
- Gate 3 was called PASS on an 8x divergence (replay +58 vs MC +465);
  this is too lenient. The fill model in strategy_replay is
  miscalibrated and biases toward favorable selection.
- The "wall_mid family was officially LUCKY" claim is unsafe. 4
  variants won officially +263 to +308; MC says all 4 lose money.
  Could be MC bias against wall_mid. Test required (player-priority-
  at-touch matching variant) before any kill recommendation.
- F2c's m=2.5+skew tuning is INVENTORY PROTECTION on bad-tail days,
  not extra edge on average. Don't extrapolate to "edge tuning works
  in general."
- **The single biggest thing that strengthens the pipeline is one more
  day of hold-1 data. Round-2 day 1 will provide this automatically.**

## Pipeline overview (what now exists)

```
Day 1 of round N — submit hold-1 trader, download log
         |
         v
src/scripts/calibration/run_calibration.py
         |
         +--> outputs/round_N_hold1/{fits.json, report.md, plots/}
         |
         v
Day 2 — for each candidate strategy:
         |
         |   strategy_replay      (single-day, deterministic)
         +-> run_strategy_audit -> outputs/audit_<strategy>/{quote_scores.csv, summary.md}
         |
         |   monte_carlo          (N synthetic days, distribution stats)
         +-> run_monte_carlo    -> outputs/mc_<strategy>/{report.md, per_session.csv}
         |
         v
Day 3 — promote based on combined audit + MC verdict
         |
         v
Day 4-5 — submit, monitor, record (local_replay, MC_median, official_PnL) triple
```

## What shipped this session (6 commits)

| Commit | What |
|---|---|
| `337c329` (early) | Round-1 hold-1 calibration polished + AR(1) fix + bimodal split |
| `9ea0d43` | Cross-validation against chrispyroberts published values |
| `fde1d6a` | strategy_replay + F3a single-day verdict |
| `bb8570c` | Round-N runbook + initial session memo |
| `4c5b108` (Session A) | MC simulator core (5 modules + 52 tests) + Gates 1-2 |
| `<latest>` (Session B) | MC runner + stability metrics + cohort MC verdict |

## Top-level findings

### 1. F3a has a real edge under day-0 microstructure (cross-day untested)

Three signals point the same way:
- **strategy_replay**: single-day +58 PnL, mean edge per quote +1.56,
  all 4 markout horizons positive on both sides — a lucky-direction
  artifact would not produce uniform sign across horizons + sides.
- **MC median +465** across 100 *within-day permutations* of round-1
  day-0's microstructure (matches official lift +434 within rounding,
  with the major caveat that PnL absolutes are not meant to match —
  that's a coincidence of the within-day calibration).
- **Win rate 93%** within-day permutations.

Confidence: ~70% (was previously claimed as ~95%) that F3a's edge
reflects a real market-making property rather than day-0 noise.
The remaining 30% is the cross-day persistence question that one
more day of hold-1 calibration would settle.

### 2. The wall_mid family verdict is UNRESOLVED (was previously claimed "officially lucky")

Phase F's official ranking placed F3d (#2), F2b (#3), F3c (#4), F2d (#5)
with positive lifts +263 to +308. MC across 100 seeds shows all four
with negative median PnL and 43-48% win rate.

Two competing explanations:
- 4 correlated strategies caught the same lucky tail draw on day 0
- MC is missing a microstructure feature wall_mid exploits

**The distinguishing test is required before any kill recommendation**:
re-run MC with a player-priority-at-touch matching model variant. If
wall_mid family medians turn positive under that variant, MC is biased
and the kill is wrong. Until that test runs, **carry one wall_mid
variant as a hedge candidate for round 2**.

### 3. PEPPER is NOT a Gaussian random walk

Real PEPPER FV: 998 of 999 increments are essentially +0.1 ticks; one
is -5.9. The "sigma=0.19" we measured is entirely from the one outlier;
the underlying process is **deterministic +0.1 ticks per tick**.

This rewrites the Phase F PEPPER narrative: `buy_hold_80`'s consistent
+7286 was capturing a structural deterministic drift, not lucky
volatility. For round 2: any product with similar deterministic-drift
profile should be addressed with buy-and-hold, NOT MM strategies.

### 4. m=2.5 + skew tuning is INVENTORY PROTECTION on bad-tail days, not edge generation

F2c (plain weighted_mid, m=1.5) MC median: +408
F3a (weighted_mid + m=2.5 + linear skew c=2) MC median: +465

The +57 marginal in MC is borderline-significant in within-day noise
(~0.2σ of per-session std=293). What's NOT borderline: F2c's worst MC
seeds are the same as F3a's worst seeds (417, 499, 474, 498, 511), and
F2c's official under-performance vs F3a (+75 vs +434) likely reflects
a single tail-realization that F3a's m=2.5+skew protected against.

For round 2: re-tune m and skew_c around the new sigma; don't ship
F3a's literal numbers. The recipe (weighted_mid + m≈N·sigma + small
linear skew) likely transfers; the specific numbers do not.

## Reusable engine infra (product-agnostic)

| Module | Purpose | Location |
|---|---|---|
| `extract_fv.py` | Recover server FV from PnL stream (hold-1 OR general-mode) | `src/analysis/calibration/` |
| `fair_value_fit.py` | Gaussian RW fit (sigma, drift, AR(1), variance ratio, quantization) | same |
| `bot_classifier.py` | Rank-based depth band detection with bimodality split | same |
| `rule_search.py` | Brute-force quote-rule recovery with canonicalization | same |
| `trade_fit.py` | Bernoulli arrivals + categorical sizes + locations | same |
| `validate.py` | 10 standard diagnostic plots per product | same |
| `serialize.py` | fits.json + calibration_report.md emitters | same |
| `strategy_replay.py` | Replay any Trader against true FV; per-quote markouts | same |
| `fv_evolver.py` | Synthesize FV paths from FairValueFit | same |
| `bot_sampler.py` | Empirical historical-book reanchoring | same |
| `trade_sampler.py` | Renewal-process arrivals + joint (offset, size) draws | same |
| `player_matcher.py` | Phase 1 aggressive + phase 2 bot-taker w/ time priority | same |
| `generative_simulator.py` | Tick-loop orchestrator + SessionResult | same |
| `stability_metrics.py` | Distribution aggregation across N MC sessions | same |

## CLI entry points

| Script | Purpose |
|---|---|
| `run_calibration.py` | End-to-end: hold-1 log + trades CSV → fits + plots |
| `validate_against_tutorial.py` | Score recovered params vs chrispyroberts published truth |
| `compare_against_truth.py` | Per-parameter delta table |
| `run_strategy_audit.py` | Single-day strategy_replay against true FV |
| `run_simulator_validation.py` | Gates 1+2 (round-trip + marginal match) |
| `run_monte_carlo.py` | N-session distribution stats per strategy |

## Test coverage

77 calibration-specific tests, all green:

| File | Tests |
|---|---:|
| `test_calibration_pipeline.py` | 10 |
| `test_calibration_general_mode.py` | 4 |
| `test_calibration_runner_integration.py` | 1 |
| `test_strategy_replay.py` | 2 |
| `test_fv_evolver.py` | 11 |
| `test_bot_sampler.py` | 12 |
| `test_trade_sampler.py` | 10 |
| `test_player_matcher.py` | 12 |
| `test_generative_simulator.py` | 7 |
| `test_stability_metrics.py` | 9 |
| `test_monte_carlo_runner.py` | 3 |

## What's NOT done (deferred or open)

1. **Bivariate FV process** — measured cross-product correlation
   +0.64 (whole-day) but rolling-median 0.03. For single-product F3a
   audit this doesn't bite; for cross-product strategies it would.
   v2 of fv_evolver should accept a covariance matrix.

2. **Jump model for PEPPER-like products** — current sigma+drift Gaussian
   RW doesn't handle the rare big-jump component. With n=1 jump
   observation, can't fit a jump distribution. Need more data or accept
   the limitation that MC under-estimates PEPPER tail risk.

3. **Joint side+location trade classifier** — current heuristic
   (`price > FV → buy`) is biased on asymmetric quote distributions
   (we saw it on TOMATOES: 0.685 vs truth 0.472). Not blocking F3a
   verdict; would matter for products with strong asymmetric quotes.

4. **Per-mechanism transfer-ratio tracker** — needs ~5 rounds of
   (local_replay, MC_median, official_PnL) triples to be useful.
   Defer until round 3 or so.

5. **Inner-wall multi-bot refinement** — round-1 inner-wall match
   rates are 80-84% (vs outer 95-97%). Likely a third bot
   occasionally displacing the wall. Bimodality split helped but
   didn't fully resolve. Not a blocker.

6. **Round-2 hold-1 calibration** — must happen day 1 of round 2.
   Pipeline is ready; just needs new data.

## Branch hygiene

- `calibration-tooling`: 6 commits ahead of main; clean working tree.
- 3 stashes parked from this and previous sessions:
  - `stash@{0}`: session-b-pre-start codex wip in core/config.py
  - `stash@{1}`: pre-step1 wip — unexpected modified files on calibration-tooling
  - `stash@{2}`: round1-research wip — may contain recovered Phase G config

To inspect: `git stash list`. To recover: `git stash apply stash@{N}`.

## Recommendations for next steps

1. **Submit `pepper_buy_hold_80_fastload`** if any round-1 slots remain:
   change `max_aggressive_size=80` (currently 5). Trivial config change,
   expected +60-100 PEPPER PnL, no risk. Probably still ships
   F3a's ASH config alongside.

2. **Round 2 day 1**: submit `outputs/submissions/calibration/trader_hold_one.py`.
   Pipeline ready to recalibrate when log lands. **Crucially, this
   gives us n=2 calibration days — the single biggest pipeline
   strengthener available.**

3. **Round 2 day 2**: pre-MC sanity check — compute per-FV-estimator
   MAE vs recovered server FV. Whichever FV estimator is closest is
   the strategy's foundation. ~5 min check that should gate which
   candidates even get sent to MC. Then run cohort MC with F3a-mechanism
   *retuned* to the new sigma (NOT the literal m=2.5/skew=2 numbers).

4. **Carry one wall_mid variant as a round-2 hedge** until the
   distinguishing test (player-priority-at-touch matching variant) is
   run and confirms whether MC is biased against wall_mid.

5. **For deterministic-drift products** (PEPPER analogs in round 2):
   skip MC entirely. Submit hold-1 day 1, observe drift sign, ship
   buy-and-hold-N. **Carries jump-tail risk that MC cannot quantify
   (n=1 jump observed) — accept the risk consciously.**

6. **Build the player-priority-at-touch matching variant** (~1 day) to
   resolve the wall_mid kill question. Should happen before round 2
   opens.

7. **Build a `--fast` MC mode** (20 sessions × 4 candidates) as a
   day-2 sanity check. Wall-clock-test the full calibrate→audit→MC
   path on round-1 data first to confirm the day-2 timeline is feasible.

End of session.
