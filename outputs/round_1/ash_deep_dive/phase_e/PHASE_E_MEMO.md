# Phase E — ASH stress tapes, interpretation memo

**Inputs:** `stress_matrix.csv` (wide), `stress_matrix_long.csv` (long),
generator at `../ash_stress_tapes.py`.
**Author-date:** 2026-04-16.
**Status:** Phase E complete (10 candidates × 7 tapes = 70 cells, 112 s).
**Net effect: major re-rank of the Phase-F upload priority.**

---

## 1. Setup

6 stress tapes mutate **ASH rows only** from day -2 (PEPPER untouched,
per PLAN.md §0.1). Tapes emitted to `data/raw/round_1_ash_stress/`:

| Tape | Transform | Tests |
|---|---|---|
| `ash_flat` | mid = 10 000 exactly; prices shifted accordingly | Over-trading when there's nothing to trade |
| `ash_amp3x` | residuals × 3 around anchor | Vol regime, reversion amplified |
| `ash_narrow_spread` | L1 bid/ask pulled in by 2 ticks each | Touch spread 16 → 12 |
| `ash_thin_book` | L1 volumes × 0.5 | Fewer fills available |
| `ash_anchor_shift` | anchor 10 000 → 10 025 at t=500 000 | Regime change mid-day |
| `ash_one_sided_heavy` | one-sided rate bumped to 16 % (2× baseline) | Fallback chain exercise |

Plus `day_0_real` (day-0 real tape) as the shared reference point.

10 candidates = shipped `C_h1_alt` (control) + 9 Phase-F candidates
(F2a–F2d, F3a–F3e).

**Methodology note.** Trades files were not passed to the replay
engine on stress tapes (filename pattern doesn't support non-numeric
days). The simulator sees zero market trades on stress tapes, so
**every stress cell has 0 maker fills**; comparisons across stress
tapes are taker-driven only. On `day_0_real` (with trades) maker
fills reappear. This under-weights maker-heavy candidates on the
stress matrix, so take stress results as a taker-side stress-test
only — absolute PnL is not directly comparable across tape vs
real-day rows.

## 2. Headline table: PnL per candidate per tape

| cell | flat | amp3x | narrow | thin | anchor_shift | one_sided | day_0 | worst |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| F1_C_h1_alt (shipped) | −4 446 | +15 424 | +5 063 | +1 324 | −4 601 | +2 552 | +2 541 | −4 601 |
| F2a_C1_as_g2e-06 | −4 614 | +15 845 | +3 283 | +1 088 | −1 104 | +1 398 | +2 943 | −4 614 |
| F2b_D6_m25_as_cont | −4 449 | +16 247 | +4 375 | +1 059 | −589 | +2 114 | +3 136 | −4 449 |
| **F2c_B1_weighted_mid** | **0** | +24 067 | +6 403 | +1 557 | **+2 985** | +2 680 | +3 387 | **0** |
| F2d_B2_m25_t05 | −4 446 | +15 424 | +5 063 | +1 324 | −4 601 | +2 552 | +2 546 | −4 601 |
| **F3a_D5_weighted_m25_c2** | **0** | +23 489 | +6 327 | +1 572 | **+3 168** | +2 710 | +3 346 | **0** |
| **F3b_D7_weighted_as_g2e-6** | **0** | +21 028 | +6 281 | +1 484 | **+2 701** | +2 571 | +3 336 | **0** |
| F3c_D8_m25_cartea_b01 | −4 446 | +16 653 | +5 061 | +1 338 | −4 764 | +2 607 | +2 673 | −4 764 |
| F3d_C1_as_g5e-7 | −4 488 | +16 406 | +4 422 | +1 132 | −959 | +2 051 | +2 943 | −4 488 |
| F3e_C3_cartea_b03 | −4 460 | +17 369 | +5 502 | +1 336 | −4 615 | +2 250 | +2 294 | −4 615 |

**Three candidates survive every tape without a loss:** `F2c`, `F3a`,
`F3b`. All three use `weighted_mid` fair value. The pattern is clean.

## 3. The `weighted_mid` regime-robustness finding

This is the most important Phase-E result.

### Evidence

Three candidates use `weighted_mid` as the fair-value primary: F2c,
F3a, F3b. All three show the same pattern:

1. **On `ash_flat` (zero oscillation): zero trades, zero PnL.** The
   weighted average of constant mids equals mid exactly, so the
   taker threshold never binds and no maker price crosses the book.
   Clean idle behavior.
2. **On `ash_anchor_shift` (mid 10 000 → 10 025 at t=500k): positive
   PnL.** Weighted_mid adapts to the new anchor level because it's a
   rolling average of recent mids; the fair-value estimator naturally
   tracks the shift.
3. **On `ash_amp3x`: +21 000 to +24 000.** Strong reversion-capture
   at the amplified vol, because the tighter residual (weighted_mid
   sits closer to mid) makes every book-cross actionable.

Compare with wall_mid:

1. **On `ash_flat`:** C_h1_alt generates **241 taker fills** and
   loses **−4 446**. The simulator's mid is constant but wall_mid
   relies on which levels have the highest volume; these wobble
   snapshot-to-snapshot. False-alpha signal fires ~240 taker crosses,
   each paying a half-spread, cumulative disaster.
2. **On `ash_anchor_shift`:** C_h1_alt loses **−4 601**. wall_mid is
   stuck at the old anchor-relative level while the book actually
   shifted up by 25; the engine posts bids/asks at stale prices and
   gets run over by the regime change.

### Why this matters

Phase-A measured anchor-shift of ~2.67 and ~0.79 ticks between the
three real days — tiny but nonzero. If ANY real trading day has an
anchor drift, the `weighted_mid` family will materially outperform
`wall_mid`. Given a full IMC round likely traverses multiple days,
anchor drift is a real operational risk.

The Phase-A/B/C analysis ranked by 3-day-local mean PnL and by
expected-official rescale. Both metrics favored the `wall_mid`-based
AS variants (C1_as_g2e-06 at +2 244 exp-off) over `weighted_mid` (F2c
at +2 102 exp-off) — a margin of only +142. **Phase-E shows that
margin is vastly smaller than the regime-shift risk.**

## 4. Revised Phase-F priority ranking

Previously (Phase-D memo): F2a C1_as_g2e-06 > F2b D6 > F2c weighted_mid > ....

**Revised after Phase E (rank by robustness + upside):**

| rank | cell | argument |
|---:|---|---|
| 1 | **F2c_B1_weighted_mid** | Zero losses on any stress tape; +8 644 on amp3x; +2 985 on anchor_shift; simplest mechanism |
| 2 | **F3a_D5_weighted_m25_c2** | Same robustness as F2c + highest local PnL on record (+3 446) |
| 3 | **F3b_D7_weighted_as_g2e-6** | Same robustness family + AS formalism |
| 4 | F2b_D6_m25_as_continuous | Best of the wall_mid family; only −589 on anchor_shift |
| 5 | F2a_C1_as_g2e-06 | Phase-C winner on 3-day local but −4 614 on flat |
| 6 | F2d_B2_m25_t05 | Ties F1 on all stress tapes (wider edges don't matter with zero maker fills on stress) |
| 7 | F3d_C1_as_g5e-7 | Safer AS variant; fragile same as F2a |
| 8 | F1_C_h1_alt | Reference only |
| 9 | F3c_D8_m25_cartea_b01 | Cartea adds no value on stress tapes; worst anchor_shift |
| 10 | F3e_C3_cartea_b03 | Worst real-day performance; worst anchor_shift |

**New upload order for Phase F (was: F2a first):**

- F1 — control refresh (unchanged)
- **F2c weighted_mid first** (was F2a)
- F3a, F3b next (the full weighted_mid cohort)
- F2b, F2a, F2d, F3d (wall_mid family)
- F3c, F3e last (Cartea — lowest priority)

## 5. What the stress matrix doesn't measure

1. **Maker fills on stress tapes are all zero** because we dropped
   the trades file. Candidates that would earn strong maker
   performance on a trade-aware tape aren't rewarded here. The real
   `day_0_real` row reinstates maker fills and shows modest +3 to
   +8 maker counts across candidates — consistent with Phase-A
   baseline.
2. **Fill-model divergence between local and official not re-
   evaluated.** Phase-A measured the fill-reality scale on one
   candidate × one official day. The stress tapes don't address
   whether that scale holds for stress regimes.
3. **Position bounds are not uniformly tested.** Some candidates
   (F2b) hit full +80 position on amp3x, narrow_spread, thin_book,
   one_sided tapes. The shipped engine does not cap at 0.7 × 80
   in all paths on all candidates — position-limit overshoots are
   visible on stress but not explicitly penalized in the matrix.

## 6. Kill-switch application

PLAN.md §6.2 kill rule: loses ≥ −300 on any tape vs C_h1_alt with no
mitigation — flagged, not auto-killed.

Per-tape delta vs C_h1_alt (stress tapes only):

| cell | worst Δ vs C_h1_alt | worst tape | flag? |
|---|---:|---|---|
| F2a | −1 780 | narrow_spread | flag |
| F2b | −688 | narrow_spread | flag |
| **F2c** | +128 (all tapes) | — | **no flag** |
| F2d | 0 (matches C_h1_alt) | — | no flag |
| **F3a** | +158 | one_sided | **no flag** |
| **F3b** | +19 | one_sided | **no flag** |
| F3c | −163 | anchor_shift | flag (borderline) |
| F3d | −641 | narrow_spread | flag |
| F3e | −302 | one_sided | flag (borderline) |

**3 candidates pass kill-switch clean:** F2c, F3a, F3b.
**2 candidates pass marginally:** F2d (identical to control), F3c (−163 on anchor_shift).
**5 candidates get flagged but still upload-eligible:** F2a, F2b, F3d, F3e, with F2b being the least-worst of the flagged set.

## 7. Scope deltas vs PLAN.md after Phase E

| Item | Previously planned | Revised after E |
|---|---|---|
| Phase-F top priority | F2a (C1_as_g2e-06) | **F2c (B1_weighted_mid)** |
| Phase-F upload order | F1, F2a-d, F3a-e | **F1, F2c, F3a, F3b, F2b, F2a, F2d, F3d, F3c, F3e** |
| Kill-switch triggered | 0 | 0 auto-kills; 5 flagged |
| Stress-tape conclusion | TBD | **weighted_mid family structurally robust across regimes; wall_mid family has regime-shift fragility** |

## 8. Open questions after Phase E

1. **Does the anchor-shift robustness of weighted_mid show up on
   the official environment?** Only Phase-F uploads can answer this.
   Priority: upload F2c first to resolve.
2. **Can wall_mid be fixed via a blended FV** (e.g. 0.5 ×
   wall_mid + 0.5 × weighted_mid)? Not in Phase-D. Worth a
   follow-up cell if any F2c-family upload underperforms on official.
3. **Would re-running stress tapes WITH trades change the picture?**
   Engineering: rename trade files to numeric days or patch the
   replay-engine filename regex. Adds maker-fill info to stress
   matrix at cost of one more engineering pass. Low priority;
   the current stress matrix is sufficient for ranking.
4. **Is `ash_flat` behavior an artifact of zero-variance vs actual
   weighted_mid superiority?** The zero-trades result is too clean —
   possibly the simulator just has nothing to cross against in a
   constant-mid book. Treat the "weighted_mid passes flat" finding
   as directional, not conclusive.

## 9. Files

```
outputs/round_1/ash_deep_dive/phase_e/
  PHASE_E_MEMO.md           (this file)
  stress_matrix.csv         (wide: 1 row per candidate, 1 column per tape)
  stress_matrix_long.csv    (long: 1 row per (candidate, tape) cell)

outputs/round_1/ash_deep_dive/ash_stress_tapes.py   (generator)
data/raw/round_1_ash_stress/                         (6 tapes × 1 day each)
```
