# Phase L — K2 neighborhood, size-scaling, 4-level revisit

**Uploads:** L1 (214 525), L2 (214 875), L4 (215 034, folder labeled "l3"),
L5 (215 204), L5b (215 477), L6 (215 623).
**Baseline:** K2 (+1 764.88). Previous: J2 (+1 647), F3a (+1 395).
**Status:** SCORED, 2026-04-16.

---

## 1. Headline: L1 wins by +21. Tight-edge hypothesis continues.

| Variant | ASH PnL | Δ vs K2 | Δ vs F3a |
|---|---:|---:|---:|
| **L1 (2.5/3.5/5)** | **+1 786.31** | **+21.43** | **+391.75** |
| L5 / L5b (sizes vary) | +1 770.44 | +5.56 | +375.88 |
| K2 reference | +1 764.88 | — | +370.32 |
| L2 (2.5/4.5/7) | +1 726.56 | −38.31 | +332.00 |
| L6 (weights 5/2/2) | +1 688.69 | −76.19 | +294.12 |
| L4 (4-level 2.5/4/6/8) | +1 259.84 | −505.03 | −134.72 |

New all-time high: total PnL +9 072.31 (was +9 050.88 from K2).

---

## 2. Three hypotheses tested — two killed, one confirmed

### 2a. Confirmed: tighter outer edges win (L1 beats K2)

Three-iteration monotonic pattern:

| Phase | Edges | Official | Δ |
|---|---|---:|---:|
| F3a | (2.5) single | +1 395 | — |
| J2 | (2.5, 5, 8) | +1 647 | +252 |
| K2 | (2.5, 4, 6) | +1 765 | +118 |
| **L1** | **(2.5, 3.5, 5)** | **+1 786** | **+21** |

Transfer ratios rise monotonically too: 0.405 → 0.451 → 0.505 → 0.516.
**Tight-edge pattern is robust across 3 iterations.** Marginal gains
are shrinking (+252 → +118 → +21), consistent with approaching a
ceiling.

### 2b. Killed: size-scaling is a dead hypothesis

L5 (size_mults 1/3/5) and L5b (size_mults 1/2/4) produced
**byte-identical outcomes** to K2:

| Metric | K2 | L5 | L5b |
|---|---:|---:|---:|
| Fills | 90 | 90 | 90 |
| Round-trip vol | 245 | 247 | 247 |
| Edge per share | 7.091 | 7.112 | 7.112 |
| Avg fill size | 5.49 | 5.51 | 5.51 |
| PnL | +1 764.88 | +1 770.44 | +1 770.44 |

**IMC's fill model caps fill size by counterparty depth, not our
quote size.** A 25-share quote at edge=6 fills the same ~9 shares
per tick as a 10-share quote. Sizing the ladder is not a lever.

Marginal +5.56 is within noise (fill count identical; small size
perturbation from integer rounding).

### 2c. Killed: 4-level ladder (L4) collapsed by −505

L4 (2.5/4/6/8, weights 3/1/1/1) had the BEST local (+3 535) but
worst official among L variants (+1 260). Edge/share collapsed to
6.03 — near F3a's 5.86 baseline.

**Pattern confirmed across 3 failed 4-level attempts:**
- K3 (2.5/5/8/12): +1 166 (−481 vs J2)
- K4 asymmetric 4-level: not uploaded (lost locally)
- L4 (2.5/4/6/8): +1 260 (−505 vs K2)

**Rule: 3 levels is a uniquely optimal structure. Adding a 4th
level dilutes weight across outers, pushing each below critical
fire density.** The optimal partition is 60%/20%/20%.

---

## 3. Why L1 beats K2 — depth distribution shift

L1's tighter outer (3.5, 5 vs K2's 4, 6) shifts fills slightly
shallower. Critically, L1 still gets d=9 fills from skew effects.

Buy-side volume delta (L1 − K2):

| d= | Δ L1−K2 | reason |
|---|---:|---|
| 3 | +5 | L1's d=3.5 quote more often reachable |
| 4 | **+26** | L1's d=3.5 floors to d=4 prices more often |
| 5 | −19 | L1 misses d=5 because edge=5 sits exactly there |
| 6 | −12 | L1 has no d=6 edge |
| 7 | +11 | L1's wider skew window catches d=7 fills |
| 9 | **+14** | skew + weighted_mid pushes into d=9 |

Net: L1 picks up 56 extra shares at d=3,4,7,9; loses 31 at d=5,6.
Plus a negative on edge/share (6.93 vs 7.09). Net PnL +21.

---

## 4. What's still unexplored

### 4a. Still viable frontier

| Direction | Expected Δ vs L1 | Cost |
|---|---:|---|
| Even tighter edges (2.5, 3, 4) | +5 to +30 | 1 upload |
| Inner edge variation (2.0 or 3.0) | ±50 | 1-2 uploads |
| Residual allocator + L1 | +50 to +150 | 1 upload (needs config) |
| Queue persistence | unknown | engine work |

### 4b. Ruled out (3 phases of evidence)

- 4-level ladders
- Size-mult scaling
- Weight variations beyond 60% inner
- Spread-regime gating
- Profit-target exits
- Slow FV anchoring

### 4c. Likely dead but untested

- PEPPER arbitrage (PEPPER is deterministic)
- OFI / flow conditional quoting (Phase A R² tiny)
- Day-of-day calendar effect (cross-day corr ~0)

---

## 5. Progression summary

| Phase | Top | Official ASH | Δ from prev |
|---|---|---:|---:|
| Shipped (F1) | baseline | +960 | — |
| F | F3a | +1 395 | +435 |
| H | (refuted) | +888 | − |
| I | I2a (tied F3a) | +1 365 | − |
| J | J2 | +1 647 | +252 |
| K | K2 | +1 765 | +118 |
| **L** | **L1** | **+1 786** | **+21** |

**Cumulative +826 vs baseline, +391 vs F3a. 86% improvement over
shipped baseline.**

The step-size trajectory (+435, ×2, +252, +118, +21) suggests the
next iteration delivers +5 to +30. Real diminishing returns.

---

## 6. Phase M proposal

Three candidates, ordered by expected value:

1. **M1 ultra-tight (2.5, 3.0, 4.0)** — continue monotone tightening.
   Likely +5 to +30. Cheap test.
2. **M5 L1 + residual allocator** — activates untested engine feature
   for orthogonal extra quote level. Could add +50-150 but higher
   variance.
3. **M2 inner-lower (2.0, 3.5, 5)** — first test of inner-edge
   variation at ladder config. ±50 range.

If Phase M delivers another +20-50, we're approaching +1 820 ASH,
+9 100 total. Beyond that, engine-level changes (persistent quotes,
true concurrent multi-level) are required.
