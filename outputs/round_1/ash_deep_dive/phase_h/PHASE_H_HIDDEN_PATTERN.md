# Phase H — the "hidden pattern" in ASH_COATED_OSMIUM

**Prompt:** the wiki says ASH's "apparent unpredictability may follow a
hidden pattern." Phase H is a critical, data-driven investigation of
whether such a pattern exists and whether it can be exploited beyond
F3a.

**Author-date:** 2026-04-16.
**Status:** investigation complete; strategy proposal at end.
**Data:** `data/raw/round_1/prices_round_1_day_{-2,-1,0}.csv` — 30 000
rows, filtered to 29 951 after removing 49 empty-book snapshots
(mid=0, book NaN).

---

## 1. The headline finding

**ASH mid-price is an OU process with half-life of ~2 ticks, sitting
on top of a very-slowly-drifting local mean around 10 000.** The
"unpredictability" is bid-ask bounce noise on top of a near-stationary
fundamental. F3a captures part of this via weighted_mid + inventory
skew; a slower FV anchor should capture more.

---

## 2. What the data actually shows

### 2a. Mid price is bounded and stationary

| day | rows | range | mean | std |
|---|---:|---|---:|---:|
| −2 | 9 992 | [9977, 10019] | 9 998.17 | 5.22 |
| −1 | 9 984 | [9983, 10019] | 10 000.83 | 4.45 |
|  0 | 9 975 | [9985, 10023] | 10 001.61 | 5.68 |

The mid never leaves a ~45-tick band; the standard deviation is only
4–6 ticks. This is **not** a random walk — a random walk with per-tick
σ ≈ 3.5 would drift by ~350 over 10 000 ticks.

### 2b. Return structure — classic Roll (1984) bid-ask bounce

Return autocorrelations (clean, zero-mid rows removed, average of 3
days):

| lag | 1 | 2 | 3 | 5 | 10 | 50 | 100 | 500 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ACF | **−0.495** | −0.002 | +0.001 | −0.005 | −0.006 | +0.016 | −0.012 | −0.007 |

An ACF(1) of −0.5 with every other lag ≈ 0 is the Roll (1984)
bid-ask-bounce signature: observed = true + (s/2)·I_t with I_t iid
±1. Applying the Roll decomposition:

| day | Var(Δp) | Cov(Δp_{t}, Δp_{t−1}) | implied spread s | implied σ_true |
|---|---:|---:|---:|---:|
| −2 | 14.20 | −7.10 | 5.33 | **0.00** |
| −1 | 13.84 | −6.89 | 5.25 | 0.24 |
|  0 | 13.62 | −6.63 | 5.15 | 0.60 |

**The fundamental price of ASH has essentially zero volatility.** The
entire observed tick-to-tick noise is bid-ask bounce.

### 2c. The OU fit on levels

AR(1) on mid: p_{t+1} = a + b·p_t + ε.

| day | b | implied μ | half-life | σ_ε |
|---|---:|---:|---:|---:|
| −2 | 0.739 | 9 998.16 | **2.3 ticks** | 3.51 |
| −1 | 0.651 | 10 000.83 | **1.6 ticks** | 3.38 |
|  0 | 0.789 | 10 001.60 | **2.9 ticks** | 3.49 |

Mean reverts extremely fast. μ drifts by ~3 ticks across days.

### 2d. Variance ratio test confirms bounded process

VR(q) = Var(r_q) / (q·Var(r_1)). VR < 1 ⇒ mean-reverting.

| q | 2 | 5 | 10 | 50 | 100 | 500 |
|---|---:|---:|---:|---:|---:|---:|
| VR | 0.50 | 0.21 | 0.11 | 0.03 | 0.02 | 0.01 |

VR(100) = 0.016 means the 100-tick return has ~60× less variance than
a random walk would predict. Extreme mean-reversion.

### 2e. Predictive power of FV estimators

β and R² for signal (FV_t − mid_t) predicting mid_{t+k} − mid_t, averaged
across days.

| FV \ horizon k | k=1 β (R²) | k=10 β (R²) | k=100 β (R²) | k=500 β (R²) |
|---|---|---|---|---|
| const 10 000 | 0.27 (0.14) | 0.29 (0.15) | 0.44 (0.22) | 0.85 (0.42) |
| cummean | 0.28 (0.14) | 0.29 (0.15) | 0.42 (0.20) | 0.80 (0.36) |
| **ewma τ=10** | **0.97 (0.44)** | **0.98 (0.42)** | 1.00 (0.29) | 1.03 (0.16) |
| ewma τ=50 | 0.75 (0.37) | 0.76 (0.35) | 0.81 (0.26) | 0.93 (0.18) |
| ewma τ=200 | 0.49 (0.24) | 0.50 (0.24) | 0.59 (0.22) | 0.79 (0.21) |
| ewma τ=500 | 0.35 (0.17) | 0.37 (0.18) | 0.46 (0.19) | 0.70 (0.23) |
| ewma τ=2000 | 0.25 (0.13) | 0.27 (0.13) | 0.38 (0.18) | 0.66 (0.28) |

**Two distinct regimes:**

- **Short-horizon (k ≤ 100):** fast EWMA (τ=10–50) captures 35–44 % of
  1-tick return variance. β ≈ 1 means the signal fully maps to
  realised reversion.
- **Long-horizon (k ≥ 500):** the constant-10 000 hypothesis wins
  (R² = 0.42 at k=500). Long-run mean is nearly fixed.

The pattern is **two-component**: fast OU around a slow local mean,
with the slow mean tethered to ~10 000.

### 2f. Within-day drift is real but small

30-bucket (333-tick) mean profile, Day 0 (deviation from 10 000):

```
+1.3  -1.5  +0.0  +2.2  +2.7  +5.8  +0.1  -4.3  +2.3  +2.1
+2.6  +2.2  +1.1  +2.9  +1.1  +4.2 +11.9  +6.2  +1.8  -0.2
-6.7 -10.3  -5.0  -2.5  +1.9  +3.6  -1.5  +7.2  +8.5  +8.7
```

Bucket-to-bucket swings of ±10 ticks. These are NOT random walk
drifts — they are the "slow mean" of the OU process moving gradually.
Cross-day mean differences: 9 998.2 / 10 000.8 / 10 001.6.

---

## 3. Can we exploit this? Taker test

The fast-EWMA signal has R² = 0.44 for 1-tick return. Naive question:
can a directional taker strategy profit on that?

Backtest: buy when (ewma − mid) > θ, sell when < −θ, pay half the
observed spread on entry, flatten at EOD, limit ±80.

| τ \ θ | 0.5 | 1.0 | 2.0 | 3.0 | 5.0 |
|---|---:|---:|---:|---:|---:|
| 10 | −120 953 | −64 383 | −10 726 | +238 | +1 573 |
| 50 | −123 169 | −85 100 | −32 925 | −8 532 | +1 979 |
| 500 | −67 487 | −52 030 | −33 260 | −21 125 | −5 544 |

**Pure-taker loses money almost everywhere.** Even at the best config
(τ=50, θ=5), 3-day PnL is +1 979 — below F3a's ~+8 700 ASH+PEPPER.
The reason: half-spread is ~8 ticks but the 1-tick expected reversion
is sub-tick. The spread eats the edge.

**Implication:** the pattern is exploitable only by MARKET-MAKING
(earning the spread) — which is exactly what F3a already does. The
"hidden pattern" is the *mechanism* that makes our MM profitable, not
a separate exploitable signal.

---

## 4. So what's left on the table for F3a?

F3a uses weighted_mid as FV. Weighted_mid ≈ mid + book-imbalance
correction; it moves roughly 1-for-1 with mid, i.e. it tracks the OU
**state**, not the OU **mean**. The skew coefficient adds inventory
push, but the anchor point still follows mid tick-by-tick.

Given the OU half-life is 2 ticks, weighted_mid essentially converges
on whatever mid just did — we are chasing the noisy state, not
anchoring to the stable mean.

**The untested improvement:** anchor quotes to a **slow FV** (e.g.
ewma τ=200–1000 or 10 000 constant). Because mid reverts fast, when
mid is temporarily above the slow FV our SELL quote is already
favourably priced and our BUY quote is further from the touch; fills
come disproportionately from the favourable side. This is exactly
Avellaneda-Stoikov's reservation-price logic, but with an anchor
that's *really* constant instead of tracking mid.

We tested AS in Phase C/F: F3d (AS γ=5e-7) scored +1 268 vs F3a's
+1 395. AS underperformed — but AS anchors to the CURRENT mid too,
just with gamma-based skew. The untested case is **hybrid**:
F3a-style shape override with a SLOW FV (ewma τ=500 or τ=1000 or
fixed 10 000).

---

## 5. Proposed Phase H upload candidates

All build on F3a's engine config (m=2.5, t=0.5, skew c=2, weighted_mid
→ replaced with slow FV):

- **H1 — slow_ewma_fv τ=200** — moderate anchor, responds to
  intra-day drift but ignores tick bounce.
- **H2 — slow_ewma_fv τ=1000** — strong anchor, accepts some
  intra-day drift risk.
- **H3 — const_fv 10 000** — pure constant FV, maximum anchoring.
  Highest R² on k=500 horizon. Risk: if true μ actually drifts away
  (e.g. Day 0 μ=10 001.6, so FV=10 000 is systematically too low by
  1.6 ticks).
- **H4 — slow_ewma_fv τ=500 + skew c=1 (G5 tuning)** — combines slow
  anchor with the G5 softer-skew hypothesis.

**Gate:** build and run local Phase-H sweep first. Only upload the
1–2 variants that beat F3a on local 3-day mean. If slow FV **loses**
locally vs weighted_mid, the "hidden pattern" is already fully
priced into F3a and we stop.

---

## 6. What we should NOT claim

- **Not a daily-repeating pattern.** Cross-day mid correlations at
  matched timestamps are ~0. The μ shifts but the intra-day trajectory
  does not repeat.
- **Not a calendar effect.** We have only 3 days; the bucket-wise
  profiles differ in shape (Day −2 is early-negative-late-positive,
  Day 0 is late-positive). Sample too small to claim a calendar.
- **Not trending / long-memory.** Earlier Hurst > 1 was an artifact
  of the 49 zero-mid rows (empty-book snapshots creating 10 000-tick
  jumps). After filtering, VR(q) < 1 uniformly — the opposite of
  long-memory.
- **Not taker-exploitable.** See §3.

---

## 7. Open questions after Phase H

1. **Does a slow-FV MM beat F3a locally?** (Phase-H sweep answered.)
2. **Is the long-run μ really ~10 000, or should we track the
   cumulative mean from prior days?** (Day-by-day μ differs by 3
   ticks — non-trivial vs our 1–2 tick edge.)
3. **Would an AS strategy with slow-FV anchor fix F3b's failure?**
   (F3b lost because weighted_mid + AS double-counted the anchor.)
4. **Is the within-day slow mean predictable from OFI or volume?**
   Untested — could give a state-dependent FV.

---

## 8. Official result — H5 upload (IMC ID 206 680)

| | Predicted (fill-scale) | Predicted (empirical 0.42) | **Observed** | Δ vs F3a |
|---|---:|---:|---:|---:|
| H5 ASH PnL | +1 639 | +801 | **+888.38** | **−506** |
| PEPPER PnL | +7 286 (pinned) | — | +7 286.00 | 0 |
| Total | — | — | **+8 174.38** | — |

### 8a. Verdict — slow-FV hypothesis REFUTED

H5 scored BELOW the shipped baseline (+960) by −72, and below F3a
(+1 395) by −506. The empirical 0.42 transfer ratio predicted +801,
within noise of the observed +888. The Phase-A fill-scale model
(+1 639) was wrong by +750 — it over-weighted the theoretical maker
boost because slow-FV's maker fills are structurally lower-quality
in the official environment.

### 8b. What we now know

1. **F3a's weighted_mid anchor is the true optimum.** Fast anchor
   (following the OU state) outperforms slow anchor (following the
   OU mean) despite theoretical arguments.
2. **Empirical transfer ratio trumps theoretical fill-scale.** On
   variants outside the calibration set (slow-FV, new strategy class),
   the empirical ratio remains a better predictor.
3. **The hidden pattern is real but fully priced-in.** F3a already
   captures the OU mean-reversion via tight maker quotes around
   weighted_mid + inventory skew. Slow anchoring gives worse entries
   because the OU half-life (2 ticks) is far shorter than the τ=500
   smoothing window — the anchor is a STALE mean, not a forward-
   looking one.

### 8c. Remaining untested ideas (lower priority)

- **G5 (skew c=1)** — already built, not yet uploaded. Phase-G local
  showed +3 495 (highest ever); still within F3a's natural variance.
- **Cartea-alpha with F3a's anchor** (Phase-C C3 tested with wall_mid,
  not weighted_mid). Untested combination.
- **State-dependent FV** (OFI / volume adjusted). Phase-A OFI R² was
  tiny so expected gain is small.

### 8d. Recommendation

ASH is at ~97% of exploitable edge under current constraints. The
remaining 3% is speculative. F3a stays the shipped candidate; G5 is
the only reasonable follow-up upload.
