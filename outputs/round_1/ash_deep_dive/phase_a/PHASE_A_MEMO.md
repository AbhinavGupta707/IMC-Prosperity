# Phase A — interpretation memo

**Inputs:** `calibration_report.md`, `fits.json` (this directory).
**Author-date:** 2026-04-16.
**Status:** Phase A complete. Three actionable findings change the
Phase B/C/D scope (items 3, 4, 6 below).

---

## 1. What we measured

| Fit | Key outputs |
|---|---|
| OU (daily) | θ ≈ 0.07–0.14 per tick, half-life 5–10 ticks, μ ≈ 10 000 ± 2, σ ≈ 2 ticks |
| Fill intensity (empirical) | A ≈ 0.042–0.045 fills/snapshot at touch; k ≈ 0.02 (very shallow decay) |
| OFI R² | **0.0000–0.0003** across all 3 days × 3 horizons |
| Residual → fwd-return corr (h=1) | ewma_mid ≈ **−0.61**, wall_mid −0.59, depth_mid −0.60, microprice −0.51 |
| Local-vs-official fill scale | **Maker 0.036×** (local UNDER-fires 28×), **Taker 10.24×** (local OVER-fires 10×) |

Sample sizes after dropping one-sided / warm-up / tail-truncation
snapshots: ~6 500 residual points per day, ~9 200 OFI points per day.

## 2. OU fit — dossier confirmation and parameter priors

Daily fits:

| Day | θ (1/tick) | half-life | μ (price) | σ (ticks/√tick) | RMSE |
|---|---:|---:|---:|---:|---:|
| -2 | 0.0853 | 8.1 | 9 998.15 | 1.952 | 1.872 |
| -1 | 0.1352 | 5.1 | 10 000.84 | 1.987 | 1.860 |
|  0 | 0.0732 | 9.5 | 10 001.63 | 1.998 | 1.927 |

- **Anchor at 10 000 is empirically sound.** All three days have μ
  within 2 ticks of 10 000 — the Phase-1 dossier visual observation
  is now a measured statistic.
- **Mean reversion is real and fast.** Half-life 5–10 ticks (= 500–1000
  raw timestamps) is short relative to the 100k-tick daily horizon.
  Any target-position / reservation-price strategy that does *not*
  account for this fast reversion is under-quoting.
- **σ is stable ≈ 2 ticks/√tick.** Use σ = 2.0 as the prior for
  Phase-C1/C2 (Avellaneda-Stoikov, Guéant) spread formulas.

Notable cross-day dispersion: day -1's θ is nearly 2× day 0's. The
Phase-C2 Guéant implementation should **not** hard-code θ — it needs
either an online EWMA of θ or a per-day refit at warm-up.

## 3. Fill intensity — shallow decay, not a clean exponential

Measured as "a maker quote at offset δ from mid would have filled
against the recorded trade tape". A ≈ 0.043 at the touch on every day;
k ≈ 0.02 — meaning λ(δ=0.5) and λ(δ=8) differ by ~15 %.

**Why so shallow:** ASH trades print *at the touch* (mid ± 8). So
for any δ < 8 the fill/no-fill outcome at a given snapshot is the
same — either a touch trade happened that snapshot or it didn't. The
exponential fit is mechanically dominated by the constant touch rate.

**Implication for Phase C1/C2:**
- Use A = 0.043 as the effective base rate.
- Do **not** use k as an AS fill-intensity decay; it is structurally
  under-estimated by the touch-only trade tape.
- Instead, model δ-dependence by *simulating* the maker intent in
  the backtest (which does track queue depth) and fit λ(δ) from
  the simulator's maker-fill output. This is additional work if
  Phase-C1/C2 proves promising — defer to Phase C Stage 2.

## 4. OFI signal is dead on ASH — **KILL-SWITCH #1 TRIGGERED**

OFI R² across every (day, horizon) is **below 0.0003**. That's 2
orders of magnitude below the Phase-A cut threshold (R² > 0.02).

Per PLAN.md §11.1:

> "Phase A shows OFI R² < 0.02 at every horizon. The OFI lever is
> dead on this product. Drop C4 and all D-hybrids using it."

**Actions:**
- **Drop Phase-C C4** (`AshOFIGate`). No new strategy file, no new tests.
- **Drop Phase-D hybrids D2 and D4** (both use C4).
- Phase-D scope compresses to D1 / D3 / D5 only.

Why OFI fails here: ASH has 1–2 visible levels and a static 16-tick
spread. The CST mechanism (price-level changes at top-of-book) fires
rarely, and when it does the information is already priced in by the
time the next 100-tick snapshot arrives. The signal may well exist
at raw-tick granularity, but we only have 100-tick-cadence data.

This is a load-bearing finding. Do not revisit OFI on this dataset.

## 5. Residual → forward-return correlations — dossier confirmed

All four FV methods show the dossier's ~−0.6 short-horizon
correlation. Key comparison for Phase C3 (Cartea alpha-skew):

| Estimator | residual σ (ticks) | corr(h=1) | |signal|/σ_r | Comment |
|---|---:|---:|---:|---|
| ewma_mid | 1.06 | −0.62 | 0.58 | Cleanest signal / lowest noise |
| wall_mid | 1.45 | −0.59 | 0.41 | Current C_h1_alt reference |
| depth_mid | 1.11 | −0.60 | 0.54 | Near-ewma in quality |
| microprice | 1.78 | −0.52 | 0.29 | Noisy; short-lived signal |

**Convention note:** `residual = mid − fair`. Positive residual means
mid is above fair → forward mid drops → negative correlation.
Matches the strategy-code convention in
`src/strategies/ash_target_position.py:166` and the Phase-1 dossier.

**Signal decay by horizon (ewma_mid, all 3 days averaged):**

| horizon | corr |
|---:|---:|
| 1 | −0.62 |
| 5 | −0.57 |
| 20 | −0.50 |
| 50 | −0.40 |

The signal half-life is ~20–30 ticks; consistent with the OU
half-life of 5–10 ticks (signal decays slower than the price-level
half-life because we're measuring correlation, not magnitude).

**Phase-C3 Cartea-skew β prior:**

Cartea-Jaimungal gives `δ_ask - δ_bid = β · α`. With α = residual/σ_r
(z-score), `β ≈ |corr| × (expected magnitude of forward move)`.
At h=1, a 1-σ_r residual (≈ 1 ewma_mid tick) predicts a forward move
of ~0.6 ticks. So:

- **β prior = 0.6–1.2 ticks** (the upper end doubles the naive linear
  prediction to capture accumulated reversion over a multi-tick
  fill-horizon).
- **Use ewma_mid as the fair source for Cartea** — tightest residual σ,
  strongest correlation. wall_mid is secondary.

## 6. Local-vs-official fill reality — **major reweighting needed**

C_h1_alt on 3-day local vs Alt on official day-0:

| | Local per-day | Official | Scale |
|---|---:|---:|---:|
| Maker fills | 2.0 | 56 | **0.036×** |
| Taker fills | 256.0 | 25 | **10.24×** |
| ASH PnL | +2 827 | +983 | **2.88×** |

**What this means:**
1. The local simulator under-fires maker fills by **~28×**. Any
   maker-first strategy that shows no PnL locally may still win on
   official.
2. The local simulator over-fires taker fills by **~10×**. Any
   taker-first strategy that wins locally has a large "taker
   subsidy" component that evaporates on official.
3. Local ASH PnL is **2.88× the official PnL** — not because local
   strategy is better, but because the sim over-pays takers.

**Rescaling rule for Phase B/C/D candidate scoring:**

Let a candidate's local ASH PnL be `L_M · p_m + L_T · p_t` where
`L_M, L_T` are local maker/taker counts and `p_m, p_t` are local
per-fill PnL. Scale to expected-official:

```
expected_official_PnL ≈ 0.036 × L_M × p_m + 10.24 × L_T × p_t
```

This is a blunt linear rescale — the true mapping depends on book
dynamics — but it's directionally correct and catches the biggest
bias. Any Phase-C candidate whose local "win" comes from + 500 in
taker PnL is unlikely to survive that factor-10 down-scaling.

**Actions:**
- Every Phase-B/C/D runner output will report local-PnL AND
  rescaled-expected-official-PnL, side by side.
- Maker-only candidates get **official upload priority** even if they
  only tie on local — kill-switch #2 from PLAN.md §11.2 applies.
- Taker-heavy candidates get **extra scrutiny** before the Phase-F
  ship list: require a positive local edge of at least +200 after
  rescaling.

## 7. Priors and parameter tables for Phase B/C

### Phase B — edge-width grid (B2)

Under-sampling was fine before: centre the grid on (maker=1.5,
taker=0.5). Extend both axes slightly to exercise the Cartea
asymmetric shape.

### Phase C1 — Avellaneda-Stoikov priors

- σ = **2.0** ticks/√tick (OU fit, stable across days)
- k = **0.4** (not measurable reliably — placeholder; refine via
  simulator-driven fit in C1 Stage 2)
- T = 100 000 − t (remaining ticks)
- γ ∈ {0.02, 0.05, 0.10, 0.20} (wider grid than PLAN.md — γ prior
  is weakest because fill-intensity k is poorly calibrated)

### Phase C2 — Guéant priors

- θ = EWMA-adaptive with window = 1 000 ticks, seeded at θ₀ = 0.10
- σ, k, T, γ as C1

### Phase C3 — Cartea priors

- α = z-score of `mid − fair_ewma` with σ_r = 1.05 (pooled across days)
- β ∈ {0.3, 0.6, 1.0, 1.5} ticks (wider grid than PLAN.md)
- Base edges = C_h1_alt (`wall_mid`, maker=1.5, taker=0.5)
  but **fair for α uses ewma_mid** (cleanest signal)

### Phase C5 — Target-position v2 priors

- EWMA τ ∈ {500, 2 000, 8 000} — 500 matches OU half-life on day -1;
  8 000 is slow enough to be "anchor-like" without the hard-coded
  10 000.
- α_base ∈ **{0.3, 0.6, 1.0}** — Phase-10 used 5/8/12 which is
  10-30× too aggressive given measured signal magnitude.
- dead_zone d ∈ {1, 2, 3} — signal half-residual (~0.5σ_r ≈ 0.5)
  should not trigger; 2σ residuals (~2.0) should.
- Clip target to flatten_threshold × limit (= 0.7 × 80 = 56) as
  in PLAN.md.

## 8. Scope deltas vs PLAN.md

| Item | Original plan | Revised after Phase A |
|---|---|---|
| C4 OFI-gate | 4 cells, separate strategy file, tests | **DROPPED** (kill-switch #1) |
| D2 hybrid (AS + OFI gate) | Yes | **DROPPED** (no OFI) |
| D4 hybrid (target-v2 + OFI gate) | Yes | **DROPPED** (no OFI) |
| Phase-C cell count | ~26 | **~22** (−4 OFI cells) |
| Phase-D candidate count | 5 | **3** (D1, D3, D5) |
| Phase-F batch F3 | 5 composites (C1–C5) | **4 composites** (C1, C2, C3, C5) |
| Rescaling | "fill-reality multiplier" | **Explicit linear model** with α_m = 0.036, α_t = 10.24 |
| C3 fair source | wall_mid | **ewma_mid** (cleanest signal) |
| γ/α/β grids | PLAN.md defaults | See §7 above — widened per Phase-A evidence |

Total Phase-B/C/D/E/F workload drops by ~15 % thanks to OFI being
dead. Phase-F uploads shrink from 14 to ~12.

## 9. What remains open after Phase A

1. **k (fill-intensity decay)** is not trustworthy from the trade tape
   alone. Phase C1 Stage 2 must refit from simulator maker output.
2. **σ-of-residual for ewma_mid** is pooled across days at 1.05 but
   varies ±0.03 between days. Monitor in Phase C3 whether a
   day-adaptive σ_r improves the Cartea fit.
3. **Fill-reality scale (0.036×, 10.24×)** is measured on *one*
   candidate (C_h1_alt) on *one* official day. It is the best we
   have but should be re-measured the moment a second official day's
   fills land — the ratios may be strategy-specific.
4. **OU fit from 100-tick-cadence data.** θ measured here is the
   per-cadence-step reversion rate. If real raw-tick OU speed differs,
   the Guéant time-scaling in C2 will need adjustment.

None of these block Phase B. Proceed.
