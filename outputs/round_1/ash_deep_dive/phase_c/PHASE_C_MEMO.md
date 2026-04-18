# Phase C — academic composites, interpretation memo

**Inputs:** `results_all.csv`, `summary.json`, per-lever CSVs.
**Author-date:** 2026-04-16.
**Status:** Phase C complete (23 cells, 111 s of sim). Changes the
Phase-D hybrid scope.

---

## 1. Headline ranking

Baseline for comparison: the Phase-B winners.
- C_h1_alt (shipped): +883 exp-off
- B1_weighted_mid: +2 102 exp-off
- B2_m2.5_t0.5: +2 053 exp-off

Phase-C cells sorted by expected-official PnL/day (top 10):

| rank | cell | local mean | maker | taker | **exp-off** | Δ vs shipped |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `C1_as_g2e-06` | +2 937 | 19 | 770 | **+2 244** | **+1 361** |
| 2 | `C1_as_g5e-07` | +2 967 | 16 | 764 | +1 974 | +1 091 |
| 3 | `C1_as_g1e-07` | +2 999 | 14 | 755 | +1 804 | +921 |
| 3' | `C2_gueant_g*` (all 3) | +2 999 | 14 | 755 | +1 804 | +921 |
| 7 | `C3_cartea_b0.3` | +2 643 | 11 | 937 | +1 107 | +224 |
| 8 | `C5_tau500_a0.3` | +919 | 8 | 371 | +627 | −256 |
| 9 | `C3_cartea_b0.6` | +2 229 | 8 | 1 081 | +671 | −212 |
| 10 | `C5_tau500_a0.6` | +880 | 8 | 435 | +526 | −357 |

**The Phase-C winner beats the best Phase-B cell.** C1_as_g2e-06 at
+2 244 exp-off is +142 over Phase-B's best (`B1_weighted_mid`). But
the result is achieved with a *different mechanism* — AS formula
delivers ~2.5-tick half-spread via the closed-form, whereas
weighted_mid wins through a better fair-value estimator. This
strongly suggests a hybrid (combining the two).

## 2. Per-composite verdicts

### C1 — Avellaneda-Stoikov (3 γ cells)

All three γ values deliver local mean ≈ +2 950 and exp-off in the
+1 800 to +2 240 range — roughly monotone in γ. Higher γ → larger
reservation-price shift → more maker fills (14 → 16 → 19).

**Winner:** `C1_as_g2e-06`. Works because:
1. Second-term of AS half-spread `(1/γ)·ln(1 + γ/k) ≈ 1/k = 2.5 ticks`
   — effectively a 2.5-tick half-spread. This matches the Phase-B
   finding that `m=2.5` was optimal.
2. First-term `γσ²(T-t)/2` decays linearly from ~0.4 ticks at t=0
   to 0 at t=T. A soft inventory-sensitive widening near day-start.
3. Reservation-price shift `q·γ·σ²·(T-t)` at q=20, t=0 is ~0.8 ticks
   — mild inventory skew, comparable to `inventory_skew=4`'s skew at
   q_ratio=0.25.

**Advance to Phase D.**

### C2 — Guéant mean-reverting extension

**All three γ cells gave IDENTICAL results** (+2 999 local / +1 804
exp-off). This is not a bug — it's the theoretical prediction.

At θ=0.10 and T-t=100 000, the GLF-T mean-reverting factor saturates
to `1/(2θ) = 5`. Compare with the AS factor `T-t = 100 000`. The
inventory-adjustment term is **20 000× smaller** than AS, reducing
the reservation-price shift to ~0.0004 ticks per share — effectively
zero. So Guéant-with-fast-reversion reduces to a pure fixed-edge MM
with half-spread `≈ (1/γ)·ln(1 + γ/k) = 2.5 ticks`. All three γ
values produce the same effective quote.

**Interpretation:** fast mean reversion dissipates inventory risk
within the episode — the MM should *not* pay the full AS inventory
tax. The model is correct in saying "ignore inventory, just quote
the spread." But because that's what Guéant-θ=0.10 reduces to, C2 is
**strictly dominated by C1 + a tuned γ** that hand-picks the right
inventory-shift magnitude.

**Decision: drop C2 from Phase D.** Its role was to show mean-
reversion-aware spreads; on ASH that role collapses to "no inventory
adjustment", which C1 at low γ already provides.

### C3 — Cartea alpha-skew

| β | local mean | exp-off | taker fills |
|---:|---:|---:|---:|
| 0.3 | +2 643 | +1 107 | 937 |
| 0.6 | +2 229 | +671 | 1 081 |
| 1.0 | +1 524 | +392 | 1 382 |
| 1.5 | +602 | +193 | 1 841 |

**Monotonically worse with higher β.** The alpha signal (residual
z-score) is real — Phase-A confirmed corr = −0.62 — but applying it
as an asymmetric quote shift *hurts* in local sim:

1. **Taker-fill count rises with β** (937 → 1 841). Cartea shifts
   both quotes toward the direction the residual predicts. One side
   gets clipped by the book (best_bid/best_ask constraint), effectively
   widening to beyond the touch. The other side gets pushed through
   the touch, becoming a taker-like cross.
2. **Positive-markout erodes** (+1.72 → +0.44 at t+1). More takes →
   more half-spread paid → weaker markout structure.
3. **Expected-official is hurt by the fill-mix shift toward takers**
   (rescale down-weights taker PnL by 10×).

**Is the mechanism wrong for ASH?** Not fundamentally — the alpha
signal is there. But in a simulator where taker over-fires 10× and
maker under-fires 28×, any mechanism that *increases* taker fills to
act on alpha is structurally punished by the rescale.

**Decision:** Drop `β ∈ {0.6, 1.0, 1.5}` from Phase D. Consider one
β=0.1 cell in Phase D (smaller than tested — structurally the smallest
skew that still moves quotes by a fraction of a tick on large α). If
it survives it earns a Phase-F upload; otherwise Cartea is dead on
this product under this simulator.

### C5 — Target-position V2

All 12 cells produced local mean ≤ +1 000 (vs baseline +2 827) and
exp-off ≤ +627. Best: `C5_tau500_a0.3` at +627 exp-off (below the
shipped +883 baseline).

The three Phase-10 "fixes" (EWMA anchor, σ-aware α, flatten-clip)
did address the saturation failure, but the core mechanism still
does not beat plain MM on ASH:

- Position swings rarely exceed 10 shares — the target-pull logic
  mostly produces `target ≈ 0`, equivalent to MM with very low
  fire rate.
- When the target does fire, the small dead-zone (≥ 2 ticks) plus
  sigma-ref damping (α/1.06 ≈ 0.6 effective at most) produces 1–3
  tick targets. On a 16-tick spread, this is too subtle for the
  execution layer to convert into a noticeable edge.
- The `maker`-only cell (`C5_linear_maker_d0.0`) fires **zero** taker
  trades and only 7 maker fills over 3 days (PnL = +7). Confirms
  that on the local simulator, pure-maker target-position is
  untestable — same finding as Phase 10.

**Decision:** Drop C5 from Phase D. Note for the record: target-
position v2 on ASH is not testable on this simulator, even with the
Phase-10 fixes. Revisit only if we build an ASH-specific stress
tape in Phase E that delivers larger position swings, OR if we
see unexpected official-environment fills that suggest the
mechanism could work.

## 3. Cross-phase observations

### The Phase-A "kill-switch on maker-only untestability"

Phase-C `C5_linear_maker_d0.0` (zero taker fills, 7 maker fills over
3 days) confirms PLAN.md §11.2:
> "Phase A shows the maker fill curve is essentially zero for any
> δ > 1.0. Downgrade every maker-shape candidate from 'decides ship'
> to 'official confirmation required'."

We cannot distinguish maker-only variants in the local simulator.
This is not specific to C5; it's a property of the simulator. The
same issue will bite Phase-E maker-heavy stress-tape cells.

### Guéant's θ × T product rules out the full-inventory-aware family

At any plausible θ ≥ 0.05 per tick and T = 100 000 ticks, the
mean-reverting factor `(1 - e^{-2θT})/(2θ)` saturates to 1/(2θ) ≈
5–10 ticks. The AS inventory term `γσ²(T-t)` at γ-values producing
1-tick-per-share shifts becomes essentially **negligible** under
Guéant. So the full suite of "inventory-aware MM" strategies from
the literature collapses on ASH to "ignore inventory".

**Implication:** the relevant mechanism space for ASH is:
- fair-value choice (B1 winner: weighted_mid)
- maker-edge width (B2 winner: m=2.5)
- soft skew coefficient (B3 winner: linear c=2)
- AS-style soft reservation-price shift at tiny γ (C1 winner: g=2e-6)

Hybrids in Phase D should combine these, not re-test different
inventory-aware mechanisms.

## 4. Scope deltas vs PLAN.md after Phase C

| Item | Previously planned | Revised after C |
|---|---|---|
| C1 AS | 3 γ cells | Confirmed; advance to Phase D |
| C2 Guéant | 3 γ cells | **Dropped** — reduces to C1 under fast reversion |
| C3 Cartea | 4 β cells | **Dropped for β ≥ 0.6**; keep a β=0.1 probe in Phase D |
| C5 Target-v2 | ~12 cells | **Dropped** — all 12 under baseline |
| Phase-D hybrid count | 4 (D1, D3, D5, D6) | **Revised: D5, D6, D7, D8** (see below) |

**Revised Phase-D candidate list:**

- **D5** = `weighted_mid + m=2.5, t=0.5 + linear skew coef=2` (empirical stack from Phase B)
- **D6** = `wall_mid + m=2.5, t=0.5 + AS-continuous flatten (γ=5e-7)` (Phase-B B4 surprise + m=2.5)
- **D7** = `weighted_mid fair + AS quotes (γ=2e-6, σ=2, k=0.4, T=100k)` (Phase-B FV winner + Phase-C quote formula)
- **D8** = `wall_mid + m=2.5 + Cartea β=0.1` (ultra-mild Cartea on top of Phase-B B2 winner; probes whether Cartea can help at any β)

4 hybrids. Each carries an obvious hypothesis — no "stack
everything" candidates because that's where the Cartea+AS+Guéant
interaction would live, and the Phase-C evidence says Cartea+AS
together is a net-negative combination.

## 5. Open questions after Phase C

1. **Does weighted_mid + AS quote formula compound**, or does
   swapping AS for weighted_mid simply recover the Phase-B B1
   result? D7 answers this.
2. **Is Cartea viable at very small β (~0.1)?** D8 probes this.
3. **Is the "AS-continuous flatten + m=2.5" composition robust?**
   D6 gets exactly this test.
4. **Is there a maker-heavier Phase-C candidate worth uploading
   on faith?** Given the simulator under-fires makers 28×, some
   maker-heavy C1/C3 cell might look mediocre locally but win on
   official. The strongest candidate by this reasoning is
   `C1_as_g2e-06` (19 maker fills, highest of all C1 cells).
   Already on the Phase-F list.

## 6. Phase-F upload cohort (revised)

From Phase B and C combined:

| F-batch | Candidate | Source | Local exp-off | Rationale |
|---|---|---|---:|---|
| F2a | `weighted_mid_m15_t05` | B1 winner | +2 102 | Phase-B FV winner |
| F2b | `m2.5_t0.5` | B2 winner | +2 053 | Phase-B edge winner |
| F2c | `linear_c2` | B3 winner | +1 375 | Phase-B skew winner |
| F2d | `as_continuous` | B4 surprise | +1 172 | Phase-B flatten surprise |
| F3a | `C1_as_g2e-06` | C1 winner | **+2 244** | Phase-C overall winner |
| F3b | `C1_as_g5e-07` | C1 alternate | +1 974 | Safer γ |
| F3c | `C3_cartea_b0.3` | C3 mild | +1 107 | Minimum Cartea β that still clears baseline |
| F4a | D5 | Phase-D | TBD | Empirical hybrid |
| F4b | D6 | Phase-D | TBD | AS-continuous hybrid |
| F4c | D7 | Phase-D | TBD | weighted_mid + AS hybrid |
| F4d | D8 | Phase-D | TBD | Mild Cartea hybrid |

11 upload candidates total (was ~12 in original plan; down 1
because C5 was dropped). Within budget.

---

## 7. Files

```
outputs/round_1/ash_deep_dive/phase_c/
  PHASE_C_MEMO.md                (this file)
  summary.json                   (top-level index)
  results_all.csv                (23 rows)
  C1/results.csv                 (3 rows)
  C2/results.csv                 (3 rows)
  C3/results.csv                 (4 rows)
  C5/results.csv                 (13 rows)
```
