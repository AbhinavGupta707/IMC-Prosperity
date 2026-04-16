# Monte Carlo cohort verdict (revised after adversarial review)

**Date**: 2026-04-16 Session B.  Revised same-day after multi-perspective review surfaced overclaims.
**Method**: 100 synthetic round-1 day-0-style sessions per candidate,
ASH-only (PEPPER excluded — its FV process is deterministic, not
stochastic, so MC can't say anything meaningful about PEPPER strategies).
**Calibration**: round-1 ASH FV process (sigma=0.41, drift=-0.008,
quantization=1/1024) recovered from hold-1 submission 206432.

## CRITICAL CAVEAT — read first

**This MC is calibrated on n=1 day of data.** All 100 "synthetic
sessions" sample from the same single day's empirical bot books, trade
gaps, and FV-process parameters. They are 100 *re-orderings of one
day's microstructure*, not 100 different days. The variance estimate
in this report measures **within-day path noise only**; it captures
**zero across-day variation**.

What this report can claim: "F3a outperforms baseline within the
microstructure regime observed on round-1 day-0."

What this report cannot claim: "F3a will outperform baseline on a
different day or a different regime."

The honest confidence on F3a's edge being a real market-making
property (not a single-day artifact): roughly 70%, not 95%.

Three other limitations propagate through the verdict:

1. **Gate 3 did not really pass.** strategy_replay says F3a PnL +58
   on the realized day; MC median says +465; official says +1395
   (lift +434 over baseline). 8x and 24x divergences. The "pass"
   was issued because the signs match. The fill model in
   strategy_replay (30% passive at exact-price match) is known
   miscalibrated, which biases toward favorable selection.

2. **The wall_mid family kill — partial resolution.** Phase F
   officially ranked F3d/F2b/F3c/F2d at positions 2-5 with positive
   lifts +263 to +308. MC says all four lose money in expectation.
   The matching-model bias hypothesis (MC's bot-priority assumption
   under-credits wall_mid) was tested in
   `matching_model_test/WALL_MID_KILL_TEST.md` by re-running the
   cohort under player-priority matching. **Result: wall_mid family
   does NOT rebound** — medians change by < 12 PnL on per-session
   std ~270 (statistically zero). One bias hypothesis ruled out,
   but ambiguity remains: probability that wall_mid is "officially
   lucky on day 0" now ~55%; probability MC is missing some OTHER
   microstructure feature ~40%. Action: don't ship wall_mid as
   headline; carry one as round-2 hedge.

3. **The F2c paradox.** Official Phase F: F2c was 8th place at +75.
   MC: F2c is 2nd at +408. The verdict text earlier framed this
   as "F2c structural, official under-delivered" — that's
   selection bias on which source counts. The honest framing:
   F2c's worst MC seeds are the same as F3a's worst seeds; both
   strategies are 93% win rate; F2c likely had a tail-realization
   on day 0 that F3a's m=2.5 + skew protected against. So F3a's
   tuning is **inventory protection on bad days**, not extra
   edge on average.

## Headline ranking (with calibrated language)

| Rank | Strategy | MC median | Win rate | R^2 mean | Official Δ vs baseline | Honest verdict |
|---:|---|---:|---:|---:|---:|---|
| 1 | **F3a** | **+465** | **93%** | **0.76** | **+434** | Real edge under day-0 microstructure; cross-day untested. m=2.5 + skew=2 functions as INVENTORY PROTECTION, not edge generator. |
| 2 | F2c | +408 | 93% | 0.79 | +75 | Same edge as F3a in expectation; bigger tail risk because no inventory protection. Official under-performance likely a tail draw. |
| 3 | F2d | -37 | 48% | 0.54 | +263 | Could be officially lucky. Could be MC bias against wall_mid. UNRESOLVED — needs matching-model test before any kill. |
| 4 | F3c | -31 | 46% | 0.54 | +270 | Same status as F2d. |
| 5 | F3d | -158 | 45% | 0.55 | +308 | Same status as F2d. |
| 6 | F2b | -188 | 43% | 0.54 | +290 | Same status as F2d. |

## Three structural takeaways (recalibrated)

### 1. F3a's edge is REAL within day-0 microstructure; cross-day persistence is UNTESTED

Three signals point the same way:
- strategy_replay: positive markouts at all 4 horizons on both sides
- MC: median +465, win rate 93%, R^2 mean 0.76 (*within-day*
  resamples)
- Official: +434 lift over baseline

Read together, F3a probably has a real market-making edge.
"Probably" — not "certainly". The calibration is from one day.

The right test for cross-day persistence: round-2 day 1 hold-1,
recalibrate, re-run cohort MC. If F3a's MC median is similarly
positive on round-2 calibration, that's n=2 — weak but progress.
Until then, treat F3a as a recipe to RECALIBRATE not a
configuration to ship verbatim.

### 2. The m=2.5 + skew=2 tuning is INVENTORY PROTECTION, not edge generation

F2c (plain weighted_mid, m=1.5, no skew) MC median: +408
F3a (weighted_mid + m=2.5 + linear skew c=2) MC median: +465

The +57 marginal is borderline-significant in MC noise (within ~0.2σ
of the per-session std=293). What's NOT borderline: F3a's q05 is
-37 vs F2c's worst-seed PnLs being similar to F3a's worst-seed PnLs
(same seeds, similar magnitudes per per-session inspection).

The m=2.5 + skew=2 doesn't generate more edge in expectation; it
protects against the tail realizations that hurt F2c on the
official day. **For round 2: re-tune m and skew_c around the new
sigma, don't ship the literal F3a numbers.**

### 3. The wall_mid family verdict is UNRESOLVED, not "lucky"

The previous version of this doc said "do not carry these to
round 2." That was overconfident.

The 4 wall_mid variants share a worst-seed cluster (498, 434, ...)
distinct from F3a/F2c's worst seeds (417, 499, ...). So MC sees
the wall_mid family as having fatter left tails — that's a real
mechanism difference, not noise.

But the wall_mid family also won OFFICIALLY across all 4 variants.
Either:
- 4 correlated strategies caught the same lucky tail draw on day 0
  (low prior given they share FV-estimator family — their PnLs ARE
  correlated, so this is essentially "they all got lucky once")
- MC is missing a microstructure feature wall_mid exploits

The distinguishing test: re-run MC with player-priority-at-touch
matching. If wall_mid family medians turn positive, MC has model
bias. If they stay negative, "officially lucky" is fair.

**Until that test runs, don't kill wall_mid for round 2. Carry one
wall_mid variant as a hedge candidate.**

## Decision matrix for round 2 (revised)

| If round 2 has... | Then... |
|---|---|
| Same products as round 1 | Re-validate F3a + F2d + F2c via day-1 hold-1 + cohort MC. Ship the cohort winner. Don't ship F3a verbatim without revalidation. |
| New product with similar bot microstructure | Submit hold-1 day 1. Recalibrate. Re-tune m and skew_c around the new sigma. The RECIPE (weighted_mid + m≈N·sigma + small linear skew) likely transfers; the specific numbers do not. |
| New product with deterministic-drift dynamics (PEPPER-like) | Skip MC. Submit hold-1, observe drift sign and rate, ship buy-and-hold to position limit. **Carries jump-tail risk that MC cannot quantify** — accept it consciously. |
| New product with novel structure (baskets, options, etc.) | Recalibrate from scratch. May need new sampler models. |

## Files in this directory

- `f3a/`, `f2c/`, ..., `f2b/` — per-strategy MC outputs (report.md, per_session.csv, raw_results.json)
- `MC_VERDICT.md` — this file (v2 revised)
