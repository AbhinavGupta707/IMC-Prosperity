# Calibration & Monte-Carlo session memo — 2026-04-16

**Branch**: `calibration-tooling`
**Goal**: build full calibration → audit → Monte Carlo pipeline; deliver
F3a verdict; produce reusable infra for round 2.

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

### 1. F3a's edge IS structural

Three independent confirmations:
- **strategy_replay**: single-day +58 PnL, mean edge per quote +1.56,
  all 4 markout horizons positive on both sides
- **MC median +465** across 100 random seeds (matches official +434
  within rounding)
- **Win rate 93%, R^2 mean 0.76** — high consistency across seeds

Confidence: very high that F3a will outperform on similar-microstructure
days.

### 2. The wall_mid family was officially LUCKY

Phase F's official ranking placed F3d (#2), F2b (#3), F3c (#4), F2d (#5)
as positive lifts. MC across 100 seeds shows all four with **negative
median PnL and 43-48% win rate** — textbook sample-of-one signature.

Their official wins came from one favorable random-walk realization on
day 0. **Do not carry these to round 2.**

### 3. PEPPER is NOT a Gaussian random walk

Real PEPPER FV: 998 of 999 increments are essentially +0.1 ticks; one
is -5.9. The "sigma=0.19" we measured is entirely from the one outlier;
the underlying process is **deterministic +0.1 ticks per tick**.

This rewrites the Phase F PEPPER narrative: `buy_hold_80`'s consistent
+7286 was capturing a structural deterministic drift, not lucky
volatility. For round 2: any product with similar deterministic-drift
profile should be addressed with buy-and-hold, NOT MM strategies.

### 4. The right FV estimator > parameter tuning

For F3a, the `weighted_mid` FV choice contributes most of the edge;
adding `m=2.5` and `linear skew c=2` on top adds only +57 marginal
median PnL. Round-2 strategy: prioritize discovering the right FV
estimator for the new product before tuning edges/skews.

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
   Pipeline ready to recalibrate when log lands.

3. **Round 2 day 2**: re-run cohort MC on round-2 calibration with the
   F3a mechanism (`weighted_mid + m=2.5 + skew=2`). If MC says it
   still wins, ship F3a-port. If MC says it doesn't transfer, audit
   the new FV estimators (the calibration plots will show which mid
   approximation is closest to true FV).

4. **Don't ship wall_mid family in round 2** unless MC says otherwise.
   The single-day evidence is misleading.

5. **For deterministic-drift products** (PEPPER analogs in round 2):
   skip MC entirely. Just submit hold-1 day 1, observe drift sign,
   ship buy-and-hold-N.

End of session.
