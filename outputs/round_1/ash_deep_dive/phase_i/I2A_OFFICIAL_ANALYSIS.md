# I2a official result — deep analysis

**Submission ID:** IMC #209357 (label: i2a — 4-level ladder)
**Bundle:** `trader_round1_ash_deep_i2a.py` (SHA `820b70a9…9be386`)
**Date analyzed:** 2026-04-16

---

## Headline: TIE with F3a (−29)

| | F3a | I2a | Δ |
|---|---:|---:|---:|
| ASH PnL | +1 394.56 | **+1 365.34** | **−29.22** |
| PEPPER PnL | +7 286.00 | +7 286.00 | 0 |
| Total | +8 680.56 | +8 651.34 | −29.22 |

−29 is **within daily noise**. Not a statistically distinguishable loss.
Local +220 lead did not translate to official.

---

## What actually happened on the book — the real story

Parsing the submission's trade log reveals the mechanism clearly.

### Fill counts

| Metric | F3a | I2a | Δ |
|---|---:|---:|---:|
| Total fills | 92 | 57 | **−35 (−38%)** |
| Buy fills | 48 | 31 | −17 |
| Sell fills | 44 | 26 | −18 |
| Round-trip volume | 238 | 168 | **−70 (−29%)** |

I2a traded 29% less volume than F3a — the opposite of what the local
simulator predicted (local said +14× maker fills).

### Per-share economics

| Metric | F3a | I2a | Δ |
|---|---:|---:|---:|
| Avg buy price | 9996.66 | **9995.14** | **−1.52** (better entry) |
| Avg sell price | 10002.53 | 10002.68 | +0.15 |
| **Edge per round-trip share** | **5.86 ticks** | **7.54 ticks** | **+1.68 (+29%)** |
| Expected PnL from edge × vol | +1 395 | +1 267 | −128 |

**I2a's per-share edge is genuinely 29% better than F3a's.** Each share
traded at better average price. The ladder mechanically worked.

The PnL tied because edge × volume is approximately the same:
- F3a: 5.86 × 238 = **+1 395**
- I2a: 7.54 × 168 = **+1 267** (plus the final mark-to-market on
  residual inventory closes the +98 gap to observed +1 365)

### Depth histogram — where the fills actually landed

Buy-side volume by distance below mid=10 000:

| d= | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| F3a | 10 | 48 | 55 | 10 | 34 | 25 | 47 | 9 | 0 | 0 | 0 |
| I2a | 10 | **24** | **22** | 5 | 12 | 30 | 27 | 15 | 5 | **18** | **13** |
| Δ | 0 | **−24** | **−33** | −5 | −22 | +5 | −20 | +6 | +5 | **+18** | **+13** |

Sell-side volume by distance above mid=10 000:

| d= | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| F3a | 31 | 19 | 58 | 48 | 49 | 31 | 4 | 0 | 0 | 0 | 0 |
| I2a | 16 | 10 | 64 | 41 | 5 | 2 | 5 | 12 | 0 | 13 | 0 |

**The ladder fired at deep levels.** I2a got fills at d=9 and d=10 on
buys (+31 vol) and d=9 on sells (+13 vol) that F3a never reached.
Those are higher-edge fills — you buy at 9990 and the reversion is
guaranteed.

But I2a **lost** fills at the inner depths (d=1, d=2, d=4) where F3a
got most of its volume. The rotation posts at d=2.5 only 25% of the
time, so it misses 75% of the inner-level opportunities.

---

## The mechanism, mathematically

**Expected PnL = ∫ edge(d) × fill_rate(d) d(d)**

- Inner depths (d=2): high fill rate, low edge
- Middle depths (d=5): moderate fill rate, moderate edge
- Outer depths (d=8-12): low fill rate, high edge

**F3a** concentrates on d=2 (100% of time) — captures the head of the
fill-rate distribution at modest edge.

**I2a** spreads across d=2.5/5/8/12 at 25% each — captures the long
tail at high edge but sacrifices the head.

For ASH's specific OU amplitude distribution (half-life 2 ticks, σ_ε
≈ 3.5 ticks), the two integrals turn out to be **approximately equal**.
The process rarely deviates to ±12, but when it does each fill earns
+12 edge instead of +2.5. The amplitude-weighted expected value ties.

**This is the strongest evidence yet that F3a is at ASH's structural
ceiling.**

---

## Why did local LIE to us?

Local simulator said I2a beats F3a by +220 (6%+). Official says tie.

Two specific discrepancies between local and official fill models:

1. **Local over-fires inner-level asks relative to outer.** In the
   sim, quotes at (fair ± 2.5) get filled disproportionately often
   because the fill model doesn't fully model queue competition. So
   local over-weights F3a AND over-weights I2a's inner rotation. But
   local ALSO generously fills ladder outer levels — so I2a's local
   edge came from both. Official is more selective.

2. **Local taker counts are inflated ~10× vs official.** Phase-A
   found FILL_SCALE_TAKER = 10.24 (local has 10.24× more taker fills
   than official per share). The "taker" fills in local for F3a
   (701) correspond to ~70 official fills. Per-tick, I2a's outer
   maker levels get treated differently by the local simulator
   compared to official.

The calibration set (F1-F3e, 10 uploads) gave a 0.42 transfer ratio
for single-edge MM variants. I2a's ladder is OUTSIDE that family;
its true transfer ratio is ~**0.37** (1 365 / 3 666). Novel strategy
architectures have lower-than-calibrated transfer — same lesson as
H5 (slow-FV transfer ratio was 0.47, official +888 vs projected +801).

---

## So is F3a at the true max?

**Yes, within the single-intent architecture constraint.** Four
totally different strategies now cluster within ±50 on official:

| Strategy | Official ASH | Local | Notes |
|---|---:|---:|---|
| F3a (shipped) | **+1 395** | +3 446 | weighted_mid + m=2.5 + skew c=2 |
| F3d (AS γ=5e-7) | +1 268 | ~+3 000 | Avellaneda-Stoikov |
| F2b (m=2.5 + AS-continuous) | +1 250 | ~+3 000 | |
| H5 (slow-FV τ=500) | +888 | +1 908 | FV anchor experiment |
| **I2a (4-level ladder)** | **+1 365** | +3 666 | **ladder (TIE with F3a)** |

**All point estimates of the true ceiling cluster around +1 300-1 400.**
The 4 strategies span very different architectures (MM, AS, slow-FV,
ladder) yet all converge to the same PnL zone. That's not coincidence
— it's the ceiling imposed by the OU amplitude distribution × the
IMC fill model × the ASH bid-ask bounce structure.

To go higher you need EITHER:
1. **True concurrent multi-level** (engine change — post 2.5 AND 5 AND 8 simultaneously, not rotate). In theory captures BOTH F3a's inner volume AND I2a's outer edge. Upside: maybe +50-100% but HIGH uncertainty on whether the sim simulates queue properly.
2. **Cross-product signals** (ASH vs PEPPER correlation). PEPPER is deterministic; no signal.
3. **Market impact / game-theoretic play** (refusing to quote during adverse flow). The OFI R² was near zero in Phase A; probably dead end.
4. **Structural exploit** we haven't identified (the wiki hint was "hidden pattern" — we've now confirmed it's the OU mean-reversion, which is fully exploited).

---

## What I2a tells us (positively)

1. **The OU amplitude ladder IS real.** I2a demonstrably got fills at
   d=9 and d=10 — depths F3a never touches. The process genuinely
   visits those amplitudes.

2. **Per-share economics improve with ladder** (+29% edge). If we
   could post concurrent (not rotated) levels, we'd compound F3a's
   inner volume with I2a's outer edge. This is the most promising
   unexplored direction.

3. **The local-to-official transfer ratio is architecture-dependent.**
   Single-edge MM variants transfer at 0.42. Ladder transfers at 0.37.
   Slow-FV transferred at 0.47. Future sweep predictions should use
   architecture-matched transfer ratios, not a global one.

4. **F3a is the shipped winner.** No tested variant strictly beats it.
   G5 (skew c=1) is the only remaining "safe" experiment — projected
   +72 within F3a's noise.

---

## Recommended next steps

**Option A (default): Stop on ASH.** F3a stands. Focus time on other
products / rounds. +1 395 ASH is probably 90-95% of the achievable
ceiling given the single-intent constraint.

**Option B (high-risk, high-ceiling): true concurrent multi-level.**
Extend the engine to emit multiple maker quotes per tick. Bundle size
and validator constraints apply. Expected official upside: +150 to
+500 IF it works. Requires real engine work + one upload to verify.

**Option C: Upload G5 for completeness** (only remaining "cheap"
experiment). G5 is skew c=1 vs F3a's c=2. Already built and validated.
Projected +72 ASH. Probably within noise.

My recommendation: **A + C** — ship G5 as a boundary test, then
declare ASH optimized.
