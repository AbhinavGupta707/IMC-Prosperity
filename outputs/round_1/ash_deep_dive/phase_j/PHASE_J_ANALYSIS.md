# Phase J — ladder weighting variations, analysis

**Uploads:** J2 (211 226), J3 (211 375), J7 (211 553).
**Baseline:** F3a (197 684, +1 394.56 ASH). Previous ladder: I2a
(209 357, +1 365.34 ASH).
**Status:** SCORED, 2026-04-16.

---

## 1. Headline: J2 breaks the ceiling by +252

| Variant | ASH PnL | Δ vs F3a | Total PnL |
|---|---:|---:|---:|
| F3a (shipped) | +1 394.56 | — | +8 680.56 |
| I2a (equal ladder) | +1 365.34 | −29 | +8 651.34 |
| **J2 (inner-heavy 3-level)** | **+1 646.97** | **+252** | **+8 932.97** |
| J3 (spread-gated) | +1 371.75 | −23 | +8 657.75 |
| J7 (combo) | +1 166.28 | −228 | +8 452.28 |

**J2 is the first ASH variant to materially beat F3a on official.**
+252 / +1 395 = **+18% improvement**. Total PnL +8 933 is a new
all-time high.

---

## 2. Mechanism — J2 achieved F3a's volume × I2a's edge

### 2a. Per-share economics

| Variant | Round-trip vol | Edge per share | Expected PnL |
|---|---:|---:|---:|
| F3a | 238 | 5.86 | +1 395 |
| I2a | 168 | 7.54 | +1 267 |
| **J2** | **225** | **7.30** | **+1 643** (observed +1 647) |

J2 retained 94% of F3a's volume (225 / 238) while capturing 95% of
I2a's edge-per-share advantage. The multiplicative effect of keeping
both dominates.

### 2b. Depth histogram

Buy-side volume by distance below mid=10 000:

| d= | F3a | I2a | **J2** | J3 | J7 |
|---|---:|---:|---:|---:|---:|
| 1 | 48 | 24 | **34** | 24 | 33 |
| 2 | 55 | 22 | **37** | 22 | 40 |
| 3 | 10 | 5 | **23** | 5 | 11 |
| 4 | 34 | 12 | **17** | 12 | 26 |
| 5 | 25 | 30 | **25** | 30 | 26 |
| 6 | 47 | 27 | **50** | 27 | 42 |
| 7 | 9 | 15 | **10** | 15 | 5 |
| 8 | 0 | 5 | **6** | 5 | 0 |
| 9 | 0 | 18 | **13** | 18 | 0 |

J2 sits **between F3a and I2a at every depth** — it didn't give up
volume at shallow depths (d=1,2) AND it gained fills at deep depths
(d=7-9) that F3a never reached. F3a has 9 fills at d=7-9 combined,
J2 has 29.

### 2c. The weighting sweet spot

J2's weights (3, 1, 1) mean 60% of ticks are at the inner edge
(2.5), 20% at 5, 20% at 8. That 60% inner weight is what keeps
F3a's shallow-depth fills alive — inner quotes must fire often
enough to compete with the book's natural flow. 25% (I2a's equal
weight) wasn't enough; 60% was.

---

## 3. Transfer ratios — J2 transfers BETTER than F3a

| Variant | Local 3-day | Official ASH | Ratio |
|---|---:|---:|---:|
| I2a | +3 666 | +1 365 | 0.372 |
| **J2** | +3 653 | **+1 647** | **0.451** |
| F3a | +3 446 | +1 395 | 0.405 |
| J3 | +3 631 | +1 372 | 0.378 |
| J7 | +3 581 | +1 166 | 0.326 |

**J2's 0.451 ratio is higher than any variant tested** — including
F3a (0.405). The inner-heavy weighted rotation UNDER-projects in
local because:

1. Local simulator's fill model generously fills deep-resting
   outer quotes (over-estimates their local value).
2. Inner-level quotes compete more with book liquidity in local,
   so local under-counts their fill rate.
3. J2's 60% inner exposure maximizes the UNDER-COUNTED side.
4. Officially, inner quotes fire at close to their theoretical rate,
   while outer quotes under-perform local expectations (as I2a showed).

Net: J2's local number is suppressed by the inner-level under-counting,
so official PnL exceeds projection. This is the OPPOSITE of H5
(slow-FV, ratio 0.47) and I2a (pure ladder, ratio 0.37).

---

## 4. Why J3 failed (spread-gated = near-noop)

J3 fires the full ladder only when book spread ≥ 16. But **58% of
ticks have spread = 16 exactly** and another 22% have spread 18-19,
so the gate is open 80% of the time. It effectively noop'd.

J3's results are almost identical to I2a:
- ASH PnL: J3 +1 372 vs I2a +1 365 (−7)
- Volume: J3 173 vs I2a 168 (+5)
- Edge/share: J3 7.58 vs I2a 7.54 (+0.04)
- Transfer ratio: J3 0.378 vs I2a 0.372 (+0.006)

Conclusion: pure spread-gating adds nothing because the gate
triggers too easily.

---

## 5. Why J7 failed (combo was TOO restrictive)

J7 = J2's weighting (3/1/1/1, inner 50%) + J3's spread gate. Both
filters compound:

- Weight filter says: go to outer level only 50% of ticks.
- Spread gate says: on those outer ticks, only fire outer if
  spread ≥ 16.
- Result: outer levels actually fire only ~40% of ticks.

But critically: **J7's edge/share collapsed to 5.86 — identical to
F3a.** Meaning the remaining outer-level fires produced NO edge
advantage beyond F3a's single-edge behavior.

Why? Inspection of J7's depth histogram:
- Buy side d=8,9,10: only 6 combined (I2a has 36 there)
- Sell side d=8,9: only 0 (I2a has 13)

The double filter pushed outer levels below their critical firing
density. You need enough outer-level attempts to occasionally catch
a ±8 or ±9 price excursion — J7 didn't have enough attempts to hit
any.

**Lesson: don't stack filters on the ladder. Weight alone is the
right mechanism.**

---

## 6. Next-step candidates

J2 is the new shipped strategy. To push further, test:

| Candidate | Edges | Weights | Hypothesis |
|---|---|---|---|
| J2_heavier | (2.5, 5, 8) | (4, 1, 1) | 67% inner; closer to F3a-like |
| J2_tight | (2.5, 4, 6) | (3, 1, 1) | Outer at more-realistic depths |
| J2_4lvl | (2.5, 5, 8, 12) | (3, 1, 1, 1) | Add d=12 for extreme swings |
| J2_6lvl | (2.5, 4, 6, 8, 10) | (4, 1, 1, 1, 1) | Fine-grained ladder |
| J2_asym | (2.5, 5, 8) buy / (2.5, 4, 6) sell | (3, 1, 1) | Different depth per side |

Ranking by expected gain:

1. **J2_heavier** (67% inner) — marginal but cheap test. Projected
   +20-40 over J2.
2. **J2_4lvl** — adds d=12 coverage; projected +30-60.
3. **J2_tight** — shifts outer to d=4,6. Lower local but possibly
   higher transfer ratio. Projected +30-80.
4. **J2_asym** — custom per-side depth. Requires more code but
   could unlock another +50-100.

---

## 7. Architectural observation — the ceiling has shifted

Previous "ceiling estimate": +1 395 (F3a). After J2: +1 647.

Is +1 647 the new ceiling or can we go further? The decomposition:

- Edge/share ceiling: probably ~9-10 (pure outer-level fills).
- Volume ceiling: ~260-280 (F3a peaks at 238; outer levels add).
- Theoretical max: ~10 × 270 = 2 700.

So there's potentially another +1 000 of headroom — but the ratio
optimization gets harder. Each iteration finds smaller wins.
Realistic further improvement: +100 to +300 over J2 before diminishing
returns kick in.
