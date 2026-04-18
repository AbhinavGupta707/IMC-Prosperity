# Phase G — post-F3a parameter extension sweep

**Inputs:** `results_all.csv`, `summary.json`, Phase-F transfer ratios.
**Author-date:** 2026-04-16.
**Status:** Phase G sweep complete (6 cells, 29 s). 2 upload bundles built (G1, G5).

---

## 1. Why this phase exists

F3a sat at two **corners** of the Phase-B grid (maker_edge=2.5 max
tested, skew_coef=2 min tested). Monotone trends in both axes
suggested room to push further. Phase G probes those directions.

## 2. Sweep results (sorted by projected-official)

Projected official uses Phase-F empirical transfer ratios: 0.46 for
wall_mid family, 0.42 for tuned weighted_mid. Variants with fill-count
anomalies get a haircut.

| Variant | Config | Local 3-day | maker | taker | Ratio | Projected off |
|---|---|---:|---:|---:|---:|---:|
| **G5** | F3a with skew c=1 | **+3 495** | 7 | 695 | 0.42 | **+1 468** (+72 vs F3a) |
| G6 | F3a with skew c=0.5 | +3 481 | 6 | 697 | 0.42 | +1 462 (+66) |
| G7 | F3a with m=3.5 | +3 430 | 6 | 702 | 0.38* | +1 303 (−92) |
| G3 | F3a with m=3.0 | +3 396 | **1** | 699 | 0.30* | +1 019 (−377) |
| G4 | wall_mid + m=3.0 + c=2 | +3 059 | 9 | 772 | 0.46 | +1 407 (+12) |
| G1 | wall_mid + m=2.5 + c=2 | +3 058 | 12 | 770 | 0.46 | +1 407 (+11) |
| F3a ref | weighted_mid + m=2.5 + c=2 | +3 446 | 5 | 701 | 0.41 | +1 396 (0) |

\* penalty applied because the fill count signals a structural
problem (quotes too far from book at m=3.0/3.5 → maker fills collapse).

## 3. Key findings

### 3a. Maker-edge monotone trend **broke** past 2.5

Phase-B showed m=1.0 → 1.5 → 2.0 → 2.5 monotonically gained fills
and PnL. Phase-G shows the trend STOPS there:

- **G3 (m=3.0 on weighted_mid)**: only **1 maker fill** across 3 days.
  Quote price is behind everyone else's wall; no counterparty flow
  reaches us at m=3.0 on weighted_mid.
- **G7 (m=3.5 on weighted_mid)**: 6 maker fills, local mean slightly
  below F3a's. Quote is even further back; local fill model happens
  to still deliver fills but at lower quality.
- **G4 (m=3.0 on wall_mid)**: 9 maker fills — wall_mid tolerates the
  wider edge better than weighted_mid (wall_mid itself sits further
  from touch), but still doesn't improve over G1 (m=2.5 wall_mid).

**Verdict:** m=2.5 is the real optimum on the maker-edge axis for
both FV families. Wider is strictly worse.

### 3b. Skew-coefficient monotone trend CONTINUES past 2

Phase-B: c=8 → c=6 → c=4 → c=2 monotonically improved. Phase-G
extends to c=1 and c=0.5:

- **G5 (c=1)**: local +3 495 — **new all-time local PnL record**
- **G6 (c=0.5)**: local +3 481 — close second
- F3a (c=2) ref: local +3 446

The marginal gain from c=2 → c=1 is +49 local PnL (about +20 projected
official). c=1 → c=0.5 is +14 (within noise). **c=1 is the local
optimum**; c=0.5 could be the real optimum but the flatness between
them means noise likely dominates.

### 3c. FV choice barely matters at tuned edge/skew

Phase-F showed F3a (weighted_mid) won +76 over F2c (weighted_mid
alone at shipped edges) — but that was because weighted_mid ALONE
adds little. With m=2.5 + skew c=2 tuning:

- G1 (wall_mid): local +3 058
- F3a (weighted_mid): local +3 446 ← +388 local advantage

But after transfer-ratio rescale:
- G1 projected: **+1 407** (ratio 0.46)
- F3a observed: **+1 395** (ratio 0.41)

**Near-tie on official.** Wall_mid's higher transfer ratio
compensates for its lower local mean. The FV is almost a wash once
the edge/skew are tuned — this is a big methodological finding
for future rounds.

## 4. Upload decisions

**Build and upload (2 bundles):**

1. **G5** — F3a's engine config + skew c=1. Highest local mean AND
   strongest projected uplift (+72 vs F3a). The test: does the c=2 →
   c=1 move continue the empirical win? If yes, G5 becomes the new
   shipped candidate.
2. **G1** — F3a's tuning on wall_mid FV. Near-tie projected, but
   this upload answers whether FV choice matters at tuned params —
   a load-bearing methodological question for future rounds.

**Skip uploads (but keep the data):**

- G3, G7 (m=3.0, m=3.5 on weighted_mid) — fill counts predict
  official loss.
- G4 (wall_mid + m=3.0) — dominated by G1 at cheaper config.
- G6 (skew c=0.5) — very close to G5; wait for G5 outcome, then
  decide whether to push softer.

## 5. What Phase-G did NOT test

- **Joint optimization of skew + Cartea β**. F3c (β=0.1 + m=2.5) was
  +8 better than pure m=2.5 on official — compounding with skew c=1
  is untested. A G8 = weighted_mid + m=2.5 + skew c=1 + Cartea β=0.1
  is a promising follow-up if G5 wins.
- **Multi-day validation.** Phase-G used the 3-day local CV but the
  day-0 local tape is the same as the official day. Strictly
  out-of-sample (days −2 and −1) haven't been checked for these
  specific variants.
- **Taker-edge sweep at tuned m=2.5 + c=1**. Phase-B tested taker
  ∈ {0.25, 0.5, 1.0, 1.5} at F3a-adjacent configs; never re-tested
  at the tighter G5 tuning.
- **AS strategy with the G5 skew shape**. AS has its own reservation-
  price + half-spread formula, so "skew c=1" doesn't directly apply.
  But could test G-variant of F3d (AS γ=5e-7) with smaller min_half_spread.

## 6. Upload order for this batch

1. **G5** first (strongest hypothesis, highest projected uplift).
2. **G1** second (mechanism validation — informs future rounds).

If G5 beats F3a on official, the followup is G6 (c=0.5) or a
combined G8 (G5 + Cartea β=0.1). If G5 underperforms F3a, the c=2 →
c=1 move was past optimum and F3a stays the best known candidate.

## 7. Open questions after Phase G

1. Does the skew-monotone trend hold on official? G5 answers this.
2. Is FV choice meaningful at tuned edge/skew? G1 answers this.
3. Could we stack G5 + Cartea β=0.1 for +100 more? Untested.
4. Is day-0-only-validation biasing our picks? Multi-day check deferred.
