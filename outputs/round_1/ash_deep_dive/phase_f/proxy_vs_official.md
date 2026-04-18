# Phase F — proxy-vs-official calibration table

10-point calibration from the Phase-F upload cohort. All variants use
buy_hold_80 PEPPER (observed PEPPER PnL = +7 286.00 on every single
run — perfect pin). All ASH PnL is apples-to-apples.

## Headline calibration

| Variant | Predicted ASH (day_0_real) | Observed ASH | Ratio (obs/pred) | Δ (obs − pred) |
|---|---:|---:|---:|---:|
| baseline (shipped) | 2 541 | 959.78 | 0.378 | −1 581 |
| F2c weighted_mid | 3 387 | 1 035.53 | 0.306 | −2 351 |
| **F3a D5 stack** | 3 346 | **1 394.56** | 0.417 | −1 951 |
| F3b weighted+AS | 3 336 | 953.66 | 0.286 | −2 382 |
| F2b m25+AS-cont | 3 136 | 1 250.00 | 0.399 | −1 886 |
| F2a AS γ=2e-6 | 2 943 | 1 059.94 | 0.360 | −1 883 |
| F2d m=2.5 | 2 546 | 1 222.38 | **0.480** | −1 324 |
| F3d AS γ=5e-7 | 2 943 | 1 268.00 | 0.431 | −1 675 |
| F3c Cartea β=0.1 | 2 673 | 1 230.34 | 0.460 | −1 443 |
| F3e Cartea β=0.3 | 2 294 | 1 096.62 | 0.478 | −1 197 |

Mean ratio: **0.399**. Median: **0.408**. Stdev: **0.068**.

**One-line takeaway:** the Phase-E day_0_real predictions
systematically over-stated ASH PnL by a factor of ~2.5×. Ranking is
mostly preserved for the wall_mid family but inverted for some
weighted_mid variants.

## Mechanism-class transfer ratios

Sorted by transfer ratio (higher = more trustworthy local proxy):

| Transfer ratio | Mechanism class | Variants |
|---:|---|---|
| 0.480 | wall_mid + wider edges | F2d |
| 0.478 | wall_mid + Cartea | F3e |
| 0.460 | wall_mid + Cartea | F3c |
| 0.431 | wall_mid + AS (small γ) | F3d |
| 0.417 | weighted_mid + shape override | F3a |
| 0.399 | wall_mid + AS-continuous flatten | F2b |
| 0.378 | shipped C_h1_alt | baseline |
| 0.360 | wall_mid + AS (larger γ) | F2a |
| 0.306 | weighted_mid (plain MM) | F2c |
| 0.286 | weighted_mid + AS | F3b |

**Clean grouping:** wall_mid variants cluster at 0.40–0.48. Weighted_mid
variants with a symmetric MM bisect (F2c / F3b) plunge to 0.28–0.31.
F3a (weighted_mid but with m=2.5 + skew c=2) lifts back to 0.42 —
suggesting the edge/skew tuning counteracts weighted_mid's over-
trading bias.

## Interpretation

### Local simulator bias by FV class

Local sim over-rewards weighted_mid by ~35% more than wall_mid. Why:

1. **Weighted_mid equals `mean(recent_mids)` on the local tape**; on
   the constant-cadence local data this tracks the mid very tightly.
   The local fill model then converts those near-touch quotes into
   many taker fills that score local PnL.
2. **On the official environment**, either the fill model is
   stricter (fewer crosses honored), or the tape has enough noise
   that weighted_mid's near-touch quotes miss by one tick and end
   up out-of-the-money.

This is a **previously unmeasured bias** that Phase A's
fill-reality check (run on C_h1_alt with wall_mid) couldn't detect.

### Why F3a wins despite its unfavorable transfer ratio

F3a's weighted_mid baseline transfer (per F2c) would be ~0.30. F3a's
actual ratio is 0.42 — a +0.12 improvement attributable to
**m=2.5 + linear skew c=2**. Decomposing:

- F2c (weighted_mid alone): 0.306
- F3a (weighted_mid + m=2.5 + skew c=2): 0.417
- Gain from edge/skew tuning: **+0.111 to ratio, or +359 absolute ASH PnL**

The edge/skew tuning is doing most of the work on weighted_mid-family
variants. Without it, weighted_mid variants are worse than shipped.

### AS family: larger γ is worse on official

| Variant | γ | Phase-C rank | Official rank |
|---|---:|---:|---:|
| F3d | 5e-7 | 2nd (+1 974 expected) | **2nd** (+1 268) |
| F2a | 2e-6 | 1st (+2 244 expected) | **7th** (+1 060) |

Phase-C's "overall winner" (γ=2e-6) is **4th** in the AS family on
official. Phase-C rescale predicted γ=2e-6 > γ=5e-7. Reality is the
reverse: γ=5e-7 beats γ=2e-6 by +208 on official.

**Read:** larger γ → bigger inventory-aversion shift → AS quotes
move further from mid on non-zero inventory → real market walks past
them → fewer fills or worse fills. The local simulator over-credited
the aggressive-γ AS variant.

### Cartea family: surprisingly solid on official

Phase-C labeled Cartea as "degrading" past β=0.3. On official:

| Variant | β | Official ASH | Δ vs baseline |
|---|---:|---:|---:|
| F3c (m=2.5) | 0.1 | +1 230.34 | +271 |
| F3e (m=2.0) | 0.3 | +1 096.62 | +137 |

Both positive deltas. F3c even beat F2d (m=2.5 plain) by +8, so mild
Cartea skew did add net edge on the real day. The Phase-C β=0.6/1.0/1.5
degradation pattern is real — β=0.1 is inside the "helpful" regime.

### AS-continuous flatten (F2b)

F2b = wall_mid + m=2.5 + AS-continuous replaces the hard flatten
threshold at +0.7·limit. Official: +1 250 (+290 over baseline) — third-
best. Key comparison:

- F2d (m=2.5 + hard flatten): +1 222
- F2b (m=2.5 + AS-continuous): +1 250

The AS-continuous flatten added **+28** absolute PnL over pure
m=2.5 on official. Small but clean. Mechanism works but delta is
modest on a calm day where flatten threshold rarely binds.

### The F3b anomaly (weighted_mid + AS lost to baseline)

F3b was predicted +3 336 on day_0_real (within +10 of F3a's
prediction), but scored −6 vs baseline. What's happening:

- AS half-spread at γ=2e-6: **δ ≈ 2.5 ticks** (dominated by 1/k term)
- weighted_mid sits ~1 tick closer to mid than wall_mid on average
- Effective maker quote = (fair − δ) = a position MUCH closer to
  inside-touch than wall_mid baseline
- Real market then walks PAST the quotes and fills us at adverse
  prices, or misses us entirely

Wall_mid's "offset" into the book was **PROTECTING** C_h1_alt from
this fate. weighted_mid + AS removed that protection.

**Implication:** AS formulas assume a statistically-defined fair;
weighted_mid's tight-to-mid property conflicts with AS's implicit
"fair ≠ mid" assumption. Don't combine these naively.

## Refitted rescale for future rounds

The Phase-A rescale (`0.036× maker + 10.24× taker`) produced
day_0_real predictions that were 2.5× too optimistic across the
board. A simple global rescale of **0.40 × local day_0_real** would
give much better predictions:

| Variant | Observed | 0.40 × predicted | Error |
|---|---:|---:|---:|
| baseline | 959.78 | 1 016.40 | +56.62 |
| F2c | 1 035.53 | 1 354.80 | +319.27 |
| F3a | 1 394.56 | 1 338.40 | −56.16 |
| F3b | 953.66 | 1 334.40 | +380.74 |
| F2b | 1 250.00 | 1 254.40 | +4.40 |
| F2a | 1 059.94 | 1 177.20 | +117.26 |
| F2d | 1 222.38 | 1 018.40 | −203.98 |
| F3d | 1 268.00 | 1 177.20 | −90.80 |
| F3c | 1 230.34 | 1 069.20 | −161.14 |
| F3e | 1 096.62 | 917.60 | −179.02 |

MAE = 157 PnL, MAPE = 14%. Much better than Phase-A's 2.5×
over-prediction. But still noisy because the FV family matters
(weighted_mid under-transfers).

**Recommended for future rounds:**
- Wall_mid variants: use multiplier ≈ 0.46
- Weighted_mid variants: use multiplier ≈ 0.30 (or 0.42 if m≥2.5 + skew)
- Drop the Phase-A per-fill-type rescale — a global scale is
  simpler and more accurate at this sample size.

## Open questions after Phase F

1. **Why does local over-predict ASH by 2.5×?** Phase-A said local
   over-fires takers 10× and under-fires makers 28×. If the real
   ratio were simpler than that, we'd expect a cleaner transfer.
   The 2.5× factor is consistent with *fewer* local fills than we
   predicted being real — many of the taker crosses in local just
   don't happen in the official environment.
2. **Is F3a's +434 edge over baseline robust or one-day?** Phase-F
   gave us one official day. Multi-day CV on the new rescale would
   tell us whether F3a is structurally better or just lucky on this
   tape.
3. **Would an F3a-like variant with wall_mid instead of weighted_mid
   stack better?** i.e. `wall_mid + m=2.5 + skew c=2`. Wall_mid has
   transfer 0.46 vs weighted_mid's 0.42 (in the tuned form) — could
   gain another ~+50 ASH PnL. Not built in this pass.
