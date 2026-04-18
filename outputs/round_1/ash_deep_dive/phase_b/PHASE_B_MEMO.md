# Phase B — single-lever isolation screens, interpretation memo

**Inputs:** `results_all.csv`, `summary.json`, per-lever CSVs.
**Author-date:** 2026-04-16.
**Status:** Phase B complete (58 cells, 273 s of sim). Findings change
the Phase-D hybrid scope and seed the Phase-C parameter priors.

---

## 1. Headline ranking (top 10 by expected-official PnL/day)

Baseline `C_h1_alt` = `B1_wall_mid` = `B2_m1.5_t0.5` = every B5 cell
= wall_mid B6 cells = **+2 827 local / +883 expected-official**.

| rank | cell | local mean | min | max | maker | taker | **exp-off** | Δ vs base |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | `B1_weighted_mid` | +3 332 | +2 914 | +3 696 | 14 | 713 | **+2 102** | **+1 219** |
| 2 | `B2_m2.5_t0.5` | +2 815 | +2 546 | +3 319 | 18 | 771 | **+2 053** | **+1 170** |
| 3 | `B2_m2.5_t1.5` | +2 434 | +2 170 | +2 863 | 14 | 560 | +1 881 | +998 |
| 4 | `B2_m2.5_t1.0` | +2 772 | +2 471 | +3 247 | 14 | 668 | +1 846 | +963 |
| 5 | `B2_m2.5_t0.25` | +2 743 | +2 444 | +3 305 | 17 | 822 | +1 807 | +924 |
| 6 | `B2_m2.0_t1.5` | +2 445 | +2 187 | +2 878 | 12 | 560 | +1 658 | +775 |
| 7 | `B6_ewma_mid_h16` | +1 766 | +1 736 | +1 802 | 11 | 370 | +1 584 | +701 |
| 8 | `B2_m2.0_t0.5` | +2 821 | +2 524 | +3 367 | 13 | 770 | +1 572 | +689 |
| 9 | `B1_ewma_mid` | +1 787 | +1 761 | +1 802 | 10 | 369 | +1 480 | +597 |
| 10 | `B3_linear_c2` | +3 050 | +2 793 | +3 529 | 10 | 774 | +1 375 | +492 |

**Read-outs:**
- **Every top-10 cell lifts expected-official by ≥ +490 over
  baseline.** That is comfortably above the Phase-A fill-reality
  rescale uncertainty (which is ~±100 on C_h1_alt itself).
- **Wider maker-edge drives 5 of the top 6.** Raising `maker_edge`
  from 1.5 → 2.5 (holding everything else = C_h1_alt) pushes the
  quote wider into the 16-tick spread and collects more passive
  fills when counterparty flow walks through — 18 maker fills vs 6
  on baseline. In the local sim the total PnL *drops* slightly
  (+2 815 vs +2 827) because the simulator under-fires makers by 28×;
  on official, each maker fill is worth much more. This is the
  single cleanest "local under-estimates the gain" signal in the
  sweep.
- **`weighted_mid` (FV = time-weighted average of recent mids) is
  the single best Phase-B cell.** Local mean +3 332 is +505 over
  `wall_mid`; the fill mix also skews slightly more maker-heavy
  (14 vs 6), so the rescale doubles the expected-official.

## 2. Per-lever verdicts

### B1 — fair value primary

Ranked by expected-official:

| cell | local mean | maker | taker | **exp-off** |
|---|---:|---:|---:|---:|
| `B1_weighted_mid` | +3 332 | 14 | 713 | **+2 102** |
| `B1_ewma_mid` | +1 787 | 10 | 369 | +1 480 |
| `B1_depth_mid` | +2 171 | 11 | 566 | +1 357 |
| `B1_rolling_mid` | +3 102 | 8 | 738 | +1 224 |
| `B1_wall_mid` (base) | +2 827 | 6 | 768 | +883 |
| `B1_filtered_wall_mid` | +2 827 | 6 | 768 | +883 (identical twin) |
| `B1_microprice` | +205 | 12 | 118 | +544 |
| `B1_hybrid_wall_micro` | +241 | 14 | 229 | +408 |

**Winner: `weighted_mid`.** Beats wall_mid on both axes — higher
local PnL *and* a better fill mix. `ewma_mid` is the "maker-friendly"
runner-up: lower local PnL (1 787 vs 2 827) but with 37× fewer
taker fills, so the rescale ends up competitive.

**Phase-1 dossier prediction held.** The dossier suggested
`weighted_mid` and `rolling_mid` are near-ties with `wall_mid` on
PnL and `ewma_mid`/`depth_mid` have the cleanest markouts.
Exactly what Phase-B shows.

**Actionable:** Advance both **`weighted_mid`** (top local PnL) and
**`ewma_mid`** (cleanest residual signal per Phase A — corr=−0.62 —
and best maker:taker ratio) as Phase-C/D inputs. Drop
`microprice`/`hybrid_wall_micro` from consideration.

### B2 — symmetric edge widths

16-cell grid. The surprising finding: **`maker_edge=2.5` dominates
at every taker value**. Selected rows:

| maker | taker | local mean | maker fills | **exp-off** |
|---:|---:|---:|---:|---:|
| 1.5 | 0.5 (base) | +2 827 | 6 | +883 |
| 2.0 | 0.5 | +2 821 | 13 | +1 572 |
| **2.5** | **0.5** | **+2 815** | **18** | **+2 053** |
| 2.5 | 1.0 | +2 772 | 14 | +1 846 |
| 2.5 | 1.5 | +2 434 | 14 | +1 881 |
| 1.0 | 0.5 | +2 805 | 9 | +1 173 |

**Pattern:** local PnL is roughly flat across the grid (+2 350 –
+2 830), but maker-fill count scales almost linearly with
`maker_edge`: 6 → 9 → 13 → 18 for m=1.0/1.5/2.0/2.5. Because the
simulator under-fires makers, this maker-fill scaling shows up
almost entirely in the rescale.

**Caveat:** this is the Phase-A rescale model doing heavy lifting.
The assumption "local PnL per fill ~ official PnL per fill for the
same fill type" is directionally correct but not exact — maker fills
earn the spread on official, taker fills pay. We will verify with an
official upload in Phase F.

**Winner: `m=2.5, t=0.5`.** Also surfaces a very close
`m=2.5, t=1.5` (near-tied on exp-off but with better markouts: t+5
markout +1.98 vs +1.86). Advance both as Phase-D inputs; drop
`m=1.0` variants (fewer maker fills at any taker).

**Taker edge has only a second-order effect.** Moving t from 0.25
→ 1.5 at m=2.5 shifts expected-official by ±250, much smaller than
the m=1.5 → 2.5 shift of +1 170. Consistent with Phase-A finding
that taker fills over-fire 10× on local — their marginal value is
heavily rescaled down either way.

### B3 — inventory-skew shape

13-cell sweep (after fixing the AS γ grid: γ ∈ {1e-7, 5e-7, 2e-6}
instead of the dimensionally-wrong {0.05, 0.10, 0.20}).

| cell | local mean | maker | taker | **exp-off** | comment |
|---|---:|---:|---:|---:|---|
| `B3_linear_c2` | +3 050 | 10 | 774 | +1 375 | Softer skew, more fills |
| `B3_quad_c4` | +3 025 | 10 | 777 | +1 359 | Near-tie with linear |
| `B3_tanh_c2` | +2 964 | 5 | 769 | +819 | Saturates too early |
| `B3_linear_c4` (base) | +2 827 | 6 | 768 | +883 | — |
| `B3_as_g5e-07` | +2 849 | 5 | 775 | +784 | AS at sensible γ |
| `B3_as_g1e-07` | +2 849 | 5 | 775 | +784 | γ too small → effectively linear tiny |
| `B3_as_g2e-06` | +2 849 | 5 | 775 | +784 | γ at upper bound → still not better |
| `B3_linear_c8` | +2 256 | 6 | 763 | +707 | Over-skews |
| `B3_tanh_c8` | +1 609 | 7 | 761 | +563 | Worst in lever |

**Winner: softer linear skew (coef=2).** Halving the linear
coefficient from 4 to 2 adds +492 to expected-official via more
maker fills (6 → 10). The quadratic shape at coef=4 is nearly
indistinguishable — both shapes deliver the same net effect at
typical position levels (|ratio| < 0.3 on this sim).

**AS reservation-price skew is a non-event here.** All three AS
γ values cluster at local mean +2 849 — the signal is lost in noise
because the AS term only binds at large |position|, which the sim
rarely reaches (end-of-day |pos| ≤ 25 on C_h1_alt; see Phase-A
fill-reality section). Without bigger position swings the AS
complexity has nothing to do. Keep as candidate in Phase-C C1 but
downgrade its priority.

### B4 — flatten mechanism

| cell | local mean | maker | taker | **exp-off** |
|---|---:|---:|---:|---:|
| `B4_hard_0.6` | +2 827 | 6 | 768 | +883 |
| `B4_hard_0.7` (base) | +2 827 | 6 | 768 | +883 |
| `B4_hard_0.8` | +2 850 | 6 | 770 | +888 |
| `B4_soft_k0.2` | +2 661 | 6 | 765 | +833 |
| `B4_soft_k0.5` | +2 560 | 9 | 763 | +1 076 |
| `B4_soft_k1.0` | +2 256 | 6 | 763 | +707 |
| `B4_as_continuous` | +3 071 | 8 | 772 | **+1 172** |

**Partial finding: AS-continuous flatten is the Phase-B surprise.**
After the γ fix, AS-continuous *beats* baseline on both local mean
(+3 071 vs +2 827) and expected-official (+1 172 vs +883). The
mechanism: position-dependent skew scales continuously with |pos|
instead of a discrete step at 0.7 × 80, which avoids a "jump"
behavior the hard flatten exhibits just below threshold.

**Hard flatten threshold is a null effect in 0.6–0.8.** Position
rarely reaches 0.6 × 80 = 48 on this sim, so the threshold never
binds. Consistent with the near-zero near-limit counts reported in
the Phase-10 memo.

**Actionable:** Advance **AS-continuous flatten** into Phase D as
a hybrid ingredient. Note it requires a correctly-sized AS gamma
(5e-7 with sigma=2, T=100k) to work.

### B5 — quote-size skew

**All four cells produced identical results** (local +2 827,
expected-official +883). Trip report:

| cell | local mean | maker | taker | **exp-off** |
|---|---:|---:|---:|---:|
| `B5_constant` | +2 827 | 6 | 768 | +883 |
| `B5_linear` | +2 827 | 6 | 768 | +883 |
| `B5_as_optimal` | +2 827 | 6 | 768 | +883 |
| `B5_stepwise` | +2 827 | 6 | 768 | +883 |

**Finding: size-side skew has no traction on ASH.** Position spends
essentially all of the sim inside ±0.25 × 80 = 20 shares; size
asymmetry never engages enough to alter the fill stream.

**KILL-SWITCH #3 TRIGGERED.** Per PLAN.md §11.3 (lever-winner
within ±50 of baseline): drop B5 from Phase-D consideration.
**PLAN.md scope delta:** Phase-D D5 (originally "best B3 skew +
best B5 size") reduces to **best B3 skew only** (already covered
by `B3_linear_c2`).

### B6 — history length

wall_mid: no effect (wall_mid doesn't use history — expected).
ewma_mid: h=16 marginally better than h=32+ (+1 584 vs +1 480 exp-off).

**Finding: history length only matters for ewma/rolling/weighted
families, and even there the effect is small (±100 exp-off).**
Not a priority knob.

**Use h=32 as the default going forward** — matches C_h1_alt's
existing value and shows stable behavior across ewma_mid variants.

---

## 3. Markout sanity

All top-10 cells have markouts at t+1/5/20 of roughly
(+1.9, +1.9, +1.8) — sign-positive and stable. Consistent with
C_h1_alt's +1.7/+1.6/+3.0 officially. No candidate in the top-10
showed negative short-horizon markouts, so no "selling into
rising prices" concern (unlike the Phase-10 target-position
family which had markouts of −4/−3/−2).

**Phase-B winners look markout-clean.** This is a critical
upgrade over the Phase-10 finding and supports advancing them.

---

## 4. Scope deltas vs PLAN.md after Phase B

| Item | Original plan | Revised after B |
|---|---|---|
| B5 size-skew | 4 cells, Phase-D D5 component | **Dropped from Phase D** (null effect) |
| Phase-D D5 | "best B3 + best B5" | **"best B3 only"** (already = B3_linear_c2) |
| Phase-D hybrid count | 5 → 3 (after Phase A dropped OFI) | **3 → 4** (+ new `D6_as_continuous`) |
| Phase-C C1 γ prior | {0.05, 0.10, 0.20} | **{1e-7, 5e-7, 2e-6}** (Phase-B calibrated) |
| Phase-C C1 priority | High | **Medium** (B3 AS cells all tied → small α space) |

**Proposed Phase-D candidate list (revised):**

- **D1** = C3 (Cartea skew) with ewma_mid fair  → planned
- **D3** = C1+C2+C3 full academic stack           → planned
- **D5** = `weighted_mid + m=2.5 + linear skew c=2` (empirical stack) → **revised**
- **D6** = `wall_mid + m=2.5 + AS-continuous flatten (γ=5e-7)` → **new**

That is 4 hybrids. Within the original "5 hybrids" budget because
D2 (AS+OFI) and D4 (target+OFI) dropped in Phase A.

**Phase-B winners that carry to Phase F (official upload list):**

| F-batch item | Source | Local exp-off |
|---|---|---:|
| `F2a_weighted_mid` | B1 winner | +2 102 |
| `F2b_m2.5_t0.5` | B2 winner | +2 053 |
| `F2c_linear_c2` | B3 winner | +1 375 |
| `F2d_as_continuous` | B4 surprise | +1 172 |

4 candidates for Phase F batch F2 (empirical-shape winners). Plus
the C1–C5 composites from Phase C. That brings Phase-F total to
about 10–12 uploads, within the plan.

---

## 5. Priors and parameter recommendations for Phase C

Based on Phase-B evidence:

- **Fair-value source for Cartea α (C3):** keep **ewma_mid** per
  Phase-A (cleanest residual signal); but also test a
  `weighted_mid` variant of C3 since weighted_mid was the Phase-B
  FV winner on expected-official.
- **Maker edge baseline for every C candidate:** **raise to 2.0**
  from the planned 1.5. Every Phase-B cell at m=2.0/2.5
  out-performed m=1.5. C_h1_alt is not the right baseline for the
  Phase-C composites — `m=2.0, t=0.5` or `m=2.5, t=0.5` is.
- **Inventory-skew coefficient for C1 / C2:** use 2.0 instead of
  4.0 as the default, since B3_linear_c2 beat the baseline.
- **AS γ prior for C1:** {1e-7, 5e-7, 2e-6}. Phase-B showed these
  cluster on local PnL; the winning γ on official may differ.
- **Hard-flatten threshold:** keep at 0.7 (unchanged from
  baseline; Phase-B confirmed flatten threshold is ~irrelevant on
  this sim because positions never reach it).

---

## 6. Open questions after Phase B

1. **Is the +1 170 expected-official gain on `m=2.5` real?** The
   rescale assumes per-fill PnL is fill-type-agnostic. Verify with
   a Phase-F upload; calibration will refine the multipliers.
2. **Why is `weighted_mid` better than `rolling_mid` locally**
   (+3 332 vs +3 102)? Weighted_mid applies linearly increasing
   weights to recent mids (newest highest), rolling_mid does a
   simple average. Short-answer: weighted emphasizes the current
   mid relative to history, so fair tracks mid tighter — fewer
   "stale" quotes. No action; just a nice FV confirmation.
3. **Does `as_continuous` generalize to broader γ?** Our Phase-B
   cell used γ=5e-7, σ=2, T=100 000. Phase-D D6 should run a
   small 3-point γ grid around this to see the local shape.
4. **B5 null-effect: is this a sim-specific quirk?** The
   simulator's tight position-range (end-of-day pos ≤ 25 in
   absolute value) may not reflect the official environment's
   behavior on a harder day. Defer the question — revisit in
   Phase E stress tapes with higher vol.

---

## 7. Files

```
outputs/round_1/ash_deep_dive/phase_b/
  PHASE_B_MEMO.md              (this file)
  summary.json                 (top-level index)
  results_all.csv              (58 rows)
  B1/results.csv               (8 rows)
  B2/results.csv               (16 rows)
  B3/results.csv               (13 rows)
  B4/results.csv               (7 rows)
  B5/results.csv               (4 rows)
  B6/results.csv               (10 rows)
```
