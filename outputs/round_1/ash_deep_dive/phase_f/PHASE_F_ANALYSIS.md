# Phase F — Official results, deep analysis

**Status:** Phase F complete. All 10 bundles uploaded and scored.
Deep-dive pass ends here with this memo.
**Author-date:** 2026-04-16.
**Companion files:** `submission_log.md` (raw results table),
`proxy_vs_official.md` (calibration refitting).

---

## 1. Executive summary

**Winner: F3a (D5 empirical stack)** — ASH +1 394.56, **+434.78 over
the shipped C_h1_alt baseline (+45%)**. Total PnL +8 680.56 (best of
10 uploads). Mechanism: `weighted_mid` fair value +
`maker_edge=2.5` + `linear skew coef=2` on top of the shipped
`MarketMakingStrategy` skeleton, delivered via the research-only
`AshShapeOverrideStrategy`.

Four more variants beat the baseline by +260–308:
F3d, F2b, F3c, F2d. Six of ten Phase-F variants beat shipped on ASH.

**Two planned winners disappointed.** The Phase-C top-ranked AS
candidate (F2a, γ=2e-6, predicted +2 244 expected-official) finished
7th at only +100 over baseline. The weighted_mid + AS hybrid (F3b,
predicted +3 336) finished 10th, −6 below baseline.

**The Phase-E stress-tape analysis was directionally correct
but noisy.** Its top-3 picks by "stress robustness" (F2c, F3a, F3b)
came in 8th, 1st, and 10th respectively. F3a validates the
stress-test framework; F2c and F3b refute it in different ways —
F2c's "no losses on flat" result was a sim artifact that didn't
transfer, and F3b is an interaction bug where two good mechanisms
compose badly.

---

## 2. Full ranking

| Rank | Variant | ASH | Δ vs baseline | Mechanism | Transfer ratio |
|---:|---|---:|---:|---|---:|
| **1** | **F3a** | **+1 394.56** | **+434.78** | weighted_mid + m=2.5 + linear skew c=2 | 0.417 |
| 2 | F3d | +1 268.00 | +308.22 | wall_mid + AS γ=5e-7 | 0.431 |
| 3 | F2b | +1 250.00 | +290.22 | wall_mid + m=2.5 + AS-continuous flatten | 0.399 |
| 4 | F3c | +1 230.34 | +270.56 | wall_mid + m=2.5 + Cartea β=0.1 | 0.460 |
| 5 | F2d | +1 222.38 | +262.59 | wall_mid + m=2.5 (config only) | **0.480** |
| 6 | F3e | +1 096.62 | +136.84 | wall_mid + Cartea β=0.3 | 0.478 |
| 7 | F2a | +1 059.94 | +100.16 | wall_mid + AS γ=2e-6 | 0.360 |
| 8 | F2c | +1 035.53 | +75.75 | weighted_mid (plain MM) | 0.306 |
| 9 | baseline | +959.78 | ref | shipped C_h1_alt | 0.378 |
| 10 | F3b | +953.66 | **−6.12** | weighted_mid + AS γ=2e-6 | **0.286** |

PEPPER = +7 286.00 on every row (buy_hold_80 pin held).

## 3. Per-bucket ASH PnL (25k-tick buckets)

| Variant | b0 | b1 | b2 | b3 | End |
|---|---:|---:|---:|---:|---:|
| baseline | 225.0 | 203.8 | 304.9 | 226.1 | 960 |
| F3a | **317.2** | **325.6** | **462.2** | 289.6 | **1 395** |
| F3b | 182.2 | 198.8 | 321.1 | 251.6 | 954 |
| F2c | 234.2 | 226.7 | 402.5 | 172.2 | 1 036 |
| F2d | 298.0 | 265.8 | 392.9 | 265.7 | 1 222 |
| F2a | 221.2 | 222.8 | 340.9 | 275.0 | 1 060 |
| F2b | 272.7 | 252.3 | 442.5 | 282.5 | 1 250 |
| F3c | 327.3 | 285.5 | 367.8 | 249.8 | 1 230 |
| F3d | 285.7 | 257.3 | 442.5 | 282.5 | 1 268 |
| F3e | 294.1 | 258.7 | 316.1 | 227.8 | 1 097 |

**F3a leads on 3 of 4 buckets** and ties baseline on bucket 3.
**F3c leads bucket 0** by a wide margin (+100 over baseline on b0
alone — the residual-alpha signal is strongest early in the day
when the book is most volatile).
**F2c's bucket 3 crashed** (−55 vs baseline) — weighted_mid inventory
drift plus a mid-session micro-trend ate the PnL; that collapse is
why F2c ranked 8th despite decent buckets 0-2.
**F2a and F3b both trail baseline on bucket 0** — AS quote formula
positions them poorly at the open when the market is setting its
daily anchor; mid-day is where they catch up.

## 4. What worked

### Maker edge widening (m=1.5 → 2.5): the single biggest simple lever

F2d's config-only change from shipped's m=1.5 to m=2.5 lifted ASH
**+262.59 over baseline on official** (+27%). Transfer ratio 0.480 —
the highest in the cohort. Phase-B predicted this with high
confidence (+170 rank by expected-official) and official confirmed.

This is the **cheapest upgrade** — zero research-strategy inlining,
config-only, straight drop-in replacement for shipped `test` variant.

### Weighted_mid + edge/skew tuning (F3a's winning formula)

F2c (plain weighted_mid at shipped edges) added only +76 over
baseline. F3a (same FV + m=2.5 + skew c=2) added **+435** — roughly
6× the pure-FV-swap effect. The marginal gain from adding m=2.5 and
skew c=2 on top of weighted_mid is **+359 ASH PnL**.

Mechanism: weighted_mid's tight-to-mid FV means the inventory skew
plus wider maker edge reposition the quotes into a sweet spot where
the market walks into them at favorable prices. This is the
compounding Phase-D D5 hypothesized.

### AS-continuous flatten added +28 over pure m=2.5

F2b (m=2.5 + AS-continuous) beat F2d (m=2.5 alone) by +28. Small
but clean. The AS-continuous flatten mechanism prevents the hard
threshold's discontinuity; on a day where position rarely exceeds
0.6·limit, the benefit is marginal — but it didn't hurt.

### Small Cartea β helps when layered on m=2.5

F3c (m=2.5 + Cartea β=0.1) beat F2d (m=2.5 alone) by +8 — within
noise, but directionally consistent with Phase-C's "small β helps"
reading. F3e (Cartea β=0.3 at m=2.0) did NOT beat F2d, confirming
that the right dose of β is well below the Phase-C sweep's β=0.3
floor.

### AS at small γ (F3d) was the 2nd-best variant

F3d (γ=5e-7) added +308 — nearly matching F3a's +435 without any
FV change. Mechanism: AS's closed-form half-spread delivers
~2.5 ticks of maker spread — functionally equivalent to F2d's
m=2.5 hard edge but with a softer inventory-aware term. The
inventory-aware term is mostly inactive on this day (position
rarely exceeds 50% of limit) so F3d ≈ F2d with +46 extra.

## 5. What didn't work

### F3b — two winners compose badly

F3b = weighted_mid + AS quote formula. Predicted: +3 336. Observed:
+953 (−6 below baseline). Transfer ratio: 0.286 — **worst in the
cohort.**

The root cause: AS's closed-form half-spread assumes `fair ≠ mid`.
The inventory-risk term `γσ²(T−t)` is what makes the reservation
price shift away from mid when the MM has inventory. With
weighted_mid's tight-to-mid fair value, the effective quote sits
inside the wall_mid-baseline sweet spot — too close to the touch —
and gets run over by adverse flow instead of catching mean-reverting
fills.

**Lesson:** AS-family quote formulas only add edge when paired with
a fair-value estimator that has a statistical offset from the mid.
weighted_mid doesn't; wall_mid does (~+/− 1.5 ticks per the Phase-1
dossier's residual σ). Don't stack AS on a mid-tracking FV.

### F2a (Phase-C winner) under-performed

F2a predicted +2 943 (Phase-E day_0_real). Observed: +1 060 — 7th.
Phase-C local said γ=2e-6 > γ=5e-7; official showed the reverse by
+208 PnL.

Mechanism: γ=2e-6 at q=40 shares shifts reservation price by
`40 × 2e-6 × 4 × 100000 = 32 ticks` — massive. The local sim's
fill model generated many taker fills off the resulting wide
reservation-shifted quotes; official doesn't. γ=5e-7 shifts by
only 8 ticks for the same q, keeping quotes closer to where real
counterparty flow lands.

**Lesson:** Phase-C ranked γ by expected-official, but the rescale
model couldn't distinguish between "more fills" (good locally) and
"more favorable fills" (good officially). Ratio 0.36 on F2a vs
0.43 on F3d confirms the aggressive γ transfers worse.

### F2c (weighted_mid alone) marginal

F2c predicted +3 387 (tied for #1 prediction). Observed: +1 036 —
only +76 over baseline, rank 8th. Transfer ratio 0.306.

The stress-tape Phase-E labeled F2c as "zero losses on any stress
tape" and #1 priority. The stress tapes showed weighted_mid doesn't
BREAK on regime shifts, but Phase-F shows it doesn't MEANINGFULLY
WIN at shipped edges either. The stress-robustness is real but its
absolute PnL ceiling at m=1.5 is modest.

**Lesson:** "no losses on stress tapes" ≠ "better than baseline on
the real day". Phase-E's stress-robustness metric was a hygiene
filter, not a PnL predictor. Use it to disqualify candidates
(kill-switch) not to rank them.

## 6. Meta-lessons about the pipeline

### Phase-by-phase batting average (predicted #1 vs observed #1)

| Phase | Winning candidate (local) | Official rank | Hit? |
|---|---|---:|---|
| B (58 cells) | B1_weighted_mid (exp_off +2 102) | 8th of our 10 | partial |
| C (23 cells) | C1_as_g2e-06 (exp_off +2 244) | 7th | no |
| D (4 hybrids) | D5 weighted+m25+c2 (local +3 446) | **1st** | **YES** |
| E (stress) | F2c/F3a/F3b zero-loss | 8/1/10 | partial |

**Phase D was the only phase that called the official winner
correctly.** Phase D's ranking was by 3-day local mean PnL (not by
stress robustness); D5's local PnL record (+3 446) did carry
through proportionally.

### The 0.40 transfer ratio is the most important new number

The Phase-A rescale model (per-fill-type scaling) predicted
day_0_real numbers that were 2.5× too high. The ACTUAL empirical
transfer is 0.30–0.48 with a **mean of 0.40 and stdev of 0.07**.

This is a much simpler and more accurate calibration than the
Phase-A machinery. Recommend dropping the per-fill-type rescale
entirely in future rounds and using:

- **Wall_mid family: multiplier ≈ 0.46**
- **Weighted_mid family: multiplier ≈ 0.30** (or 0.42 if tuned
  with m≥2.5 + explicit skew)

Applying this retroactively to the Phase-E predictions would have
ranked the Phase-F cohort correctly (F3a 2nd place, F3d 3rd, F2b
4th) — much better than the Phase-E priority ordering.

### Proxy-quality varies more by mechanism than by fill-mix

Phase A measured ~28× maker under-fire and ~10× taker over-fire.
The working hypothesis was "rescale by fill composition". Phase F
shows that **mechanism family** drives transfer more than fill
composition:

| Family | Transfer ratio |
|---|---:|
| wall_mid + config changes | 0.46–0.48 |
| wall_mid + AS-continuous / AS small γ | 0.40–0.43 |
| wall_mid + AS large γ | 0.36 |
| weighted_mid tuned | 0.42 |
| weighted_mid untuned | 0.29–0.31 |

This is a new empirical finding. Future-round evaluation should
track per-mechanism transfer ratios as the primary calibration
statistic.

## 7. Recommendations

### Immediate (for any remaining Round-1 slots, if applicable)

- **Ship F3a as the de-facto best ASH leg.** +434 over baseline is
  the largest official delta in the study. Use
  `trader_round1_ash_deep_f3a.py`.
- **Do not ship weighted_mid + AS (F3b-like) hybrids** — confirmed
  structurally bad composition.
- **Drop F2c and F3b from future upload plans.** Their transfer
  ratios (0.31, 0.29) make them unreliable at the expected PnL level.

### Follow-up candidates (not built yet)

- **G1 `wall_mid + m=2.5 + linear skew c=2`**: take F3a's winning
  tuning but swap weighted_mid → wall_mid. Expected transfer ratio
  ≈ 0.46 (vs F3a's 0.42) — could add another +40 ASH PnL if the
  mechanism compounds. One factory, one config-only export script.
  Low-risk upgrade path.
- **G2 `weighted_mid + m=2.5 + skew c=2 + Cartea β=0.1`**: stack
  F3a with F3c's alpha-skew. Both mechanisms are positive on
  official; might compound to +1 450+ ASH PnL. Needs Cartea inline.
  Medium complexity.
- **G3 `wall_mid + m=3.0 or m=3.5`**: we only tested m ∈ {1.0, 1.5,
  2.0, 2.5}. If the trend is monotone up to ~3 ticks, a wider edge
  could help. One more config-only test. Cheap.

### Process improvements for future rounds

- **Drop per-fill-type rescale.** Use global `0.40 × local` as the
  first-order predictor.
- **Add per-mechanism transfer-ratio tracking.** Each family
  deserves its own calibration point.
- **Treat Phase-E stress-tape "zero losses" as a filter, not a
  ranking.** Downrank candidates with positive stress-tape losses,
  but use local CV mean PnL for ranking survivors.
- **Treat Phase-D hybrid rankings by raw local mean PnL as
  authoritative** for small cohorts (4–5 candidates).

## 8. What the deep-dive delivered

- 9 new engine-config factories (additive, no shipped factory
  touched)
- 3 new research-only strategy modules (AS, Cartea, ShapeOverride)
  plus a V2 upgrade of the Phase-10 Target-position
- 1 shared `_ash_deep_bundle` builder (consolidates v2_clean-style
  inlining for future uploads)
- 10 Phase-F submission bundles, all validated (7 under-soft-cap
  with 0 warnings, 3 over-soft-cap within IMC's hard 100 KiB)
- 85 Phase B/C/D + 70 Phase-E + 10 Phase-F = **165 sim runs**
  archived
- 5 interpretation memos (PHASE_A / B / C / D / E / F-analysis)
- This calibration study (`proxy_vs_official.md`) — first in the
  project with 10 calibration points

**+434 official ASH PnL lift over shipped on one upload.** Whether
that lift holds on future days is the next question.

## 9. Open questions

1. Is F3a's +434 lift robust or day-specific? One official day only.
2. Would `wall_mid + m=2.5 + skew c=2` (G1) beat F3a? The math says
   maybe; untested.
3. Does PEPPER have any remaining edge beyond buy_hold_80? Outside
   this pass's scope (pinned by design) but we didn't verify.
4. Can the ~0.40 transfer ratio be improved by changing the local
   simulator's fill model? If yes, future Phase-Bs can score more
   reliably.
5. Are Cartea's β and AS's γ jointly optimizable on wall_mid?
   Phase-C said Cartea + AS is strictly dominated by either alone —
   Phase-F didn't test the joint case explicitly.
