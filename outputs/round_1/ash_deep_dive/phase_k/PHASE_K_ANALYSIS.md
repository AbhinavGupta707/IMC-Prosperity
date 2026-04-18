# Phase K — J2 neighborhood optimization

**Uploads:** K1 (213 473), K2 (213 280), K3 (213 029), K5 (212 807).
**Baseline:** J2 (+1 646.97 ASH). Original: F3a (+1 394.56).
**Status:** SCORED, 2026-04-16.

---

## 1. Headline: K2 wins. +370 over F3a. +118 over J2.

| Variant | ASH PnL | Δ vs F3a | Δ vs J2 | Total PnL |
|---|---:|---:|---:|---:|
| F3a (original) | +1 394.56 | — | −252 | +8 680.56 |
| J2 (prev top) | +1 646.97 | +252 | — | +8 932.97 |
| **K2** | **+1 764.88** | **+370** | **+118** | **+9 050.88** |
| K5 (asymmetric) | +1 737.00 | +342 | +90 | +9 023.00 |
| K1 (inner 67%) | +1 241.41 | −153 | −406 | +8 527.41 |
| K3 (4-level) | +1 166.28 | −228 | −481 | +8 452.28 |

**Total PnL +9 051 is a new all-time high (was +8 933 from J2, +8 681
from F3a).**

---

## 2. Why K2 won — tight outer matches the OU amplitude distribution

K2's edges (2.5, 4, 6) vs J2's (2.5, 5, 8):

| Metric | F3a | J2 | **K2** |
|---|---:|---:|---:|
| Round-trip volume | 238 | 225 | **245** |
| Edge per share | 5.86 | 7.30 | **7.09** |
| Transfer ratio | 0.405 | 0.451 | **0.505** |
| Fills | 92 | 83 | 90 |

**K2 beats J2 on volume (+20) AND has 0.505 transfer ratio — highest
ever observed.** Slightly lower edge/share (7.09 vs 7.30) is more
than offset by the volume gain.

### 2a. Depth distribution

Buy-side volume by distance below mid:

| d= | F3a | J2 | **K2** |
|---|---:|---:|---:|
| 1 | 48 | 34 | 26 |
| 2 | 55 | 37 | **46** |
| 3 | 10 | 23 | 10 |
| 4 | 34 | 17 | 29 |
| 5 | 25 | 25 | **51** |
| 6 | 47 | 50 | **49** |
| 7 | 9 | 10 | 6 |
| 8 | 0 | 6 | **17** |

K2 has MORE volume than J2 at d=5 (51 vs 25) and d=8 (17 vs 6).
The tight-outer edges (4, 6) fire more often because they're
closer to the touch, catching more of the OU's middle-amplitude
oscillations.

**The OU amplitude distribution has most mass at d=3-6, not d=5-8.**
Matching the distribution with K2's edges captures more of it.

---

## 3. Why K5 succeeded — buy-side matches K2

K5 uses buy=(2.5, 4, 6), sell=(2.5, 5, 8). Its buy-side schedule is
identical to K2's entire schedule. Sell side retains J2's wider
spacing.

K5 PnL +1 737 = most of K2's buy-side gain (+343) + some of J2's
sell-side (+90). Confirms that **the buy-side tight-outer schedule
is the dominant lever**.

This also means an all-tight asymmetric (buy=(2.5,4,6),
sell=(2.5,4,6) == K2 symmetric) would likely match K2. No asymmetric
advantage to preserve J2's sell-side wideness.

---

## 4. Why K1 and K3 failed

### 4a. K1 (67% inner): over-filtering killed edge

K1's 4/1/1 weights push inner to 67% (vs J2's 60%). Result: **edge/
share collapsed to 5.89 — identical to F3a.** Outer levels fired
too rarely to catch enough deep-amplitude fills.

**Sweet spot is 60% inner (J2/K2). Heavier is strictly worse.**

### 4b. K3 (4-level with d=12): dilution and over-depth

K3's 3/1/1/1 weights mean inner 50%, outer 50%/3 per level = 16.7%
each. The 4th outer at d=12 fires essentially never officially
(ASH rarely reaches that depth). Meanwhile inner drops from 60%
to 50%, losing F3a's volume.

**Adding more outer levels hurts: spread dilution + rarely-firing
deep level = worse on both counts.**

---

## 5. Key insights after Phase K

1. **60% inner is the weight sweet spot.** K1 (67%) loses edge; J2/K2
   (60%) wins.
2. **Tight outer edges (4, 6) > wider outer edges (5, 8).** Matches OU
   amplitude distribution.
3. **3 levels is optimal structure.** 4 levels dilutes (K3 lost).
4. **Buy-side schedule drives most improvement** (K5 data).
5. **Transfer ratios are monotonically improving as we refine.** 0.405
   (F3a) → 0.451 (J2) → 0.505 (K2). The local simulator's inner-level
   under-firing gives tight-ladder variants a hidden boost.

---

## 6. Where to go next

Given K2's success, neighborhood candidates for Phase L:

| Candidate | Change from K2 | Expected |
|---|---|---|
| **L1 K2_tighter** (2.5, 3.5, 5) | Even tighter outer | ±50 |
| **L2 K2_slightly_wider** (2.5, 4.5, 7) | Split difference K2/J2 | ±50 |
| **L3 K2_inner_shifted** (3, 4, 6) | Wider inner level | −100 |
| **L4 K2_plus_d8** (2.5, 4, 6, 8, 3/1/1/1) | Add a 4th outer | +20 to +60 |
| **L5 K2_buysize** (2.5, 4, 6, sizes 1, 3, 5) | Bigger outer sizes | +40 to +100 |
| **L6 K2_62pct_inner** (weights 5/2/2) | Slightly less inner | +10 to +50 |

**Ranked by expected gain:**
1. L5 — size scaling on outer levels. Same edge, more volume per fill.
2. L4 — adds d=8 as 4th outer. Keeps 3/1/1/1 structure tight.
3. L1 — tighter outer. Marginal move.
4. L6 — slightly less inner. Small.
5. L2 — split difference. Uninteresting.
6. L3 — would lose F3a inner volume. Don't.

---

## 7. Remaining untested directions

Beyond neighborhood:
- **K2 with slow FV instead of weighted_mid.** Already refuted by H5;
  but H5 was with single-level. Could revisit with K2 structure.
- **Dynamic edges based on recent volatility.** Adaptive ladder.
  Complex but potentially large upside.
- **Multi-size quote stacking within a level.** Post (price=X,
  size=3) and (price=X-1, size=5). Engine change required.
- **PEPPER optimization.** PEPPER has been pinned at buy_hold_80 all
  phase. We've never attempted to extract additional edge. Probably
  diminishing returns given PEPPER is deterministic.

---

## 8. Cumulative progress

| Phase | Top candidate | Official ASH | vs baseline |
|---|---|---:|---:|
| Shipped (F1) | C_h1_alt | +960 | (ref) |
| F | F3a | +1 395 | +435 |
| G | (skip — locked F3a) | — | — |
| H | H5 REFUTED | +888 | — |
| I | I2a (tied F3a) | +1 365 | −30 |
| J | J2 | +1 647 | +687 |
| **K** | **K2** | **+1 765** | **+805** |

**We've gone from +960 to +1 765 on ASH over the ASH deep-dive
phases — +84% improvement.** Ceiling seems to keep moving up as we
find tighter mechanisms.
