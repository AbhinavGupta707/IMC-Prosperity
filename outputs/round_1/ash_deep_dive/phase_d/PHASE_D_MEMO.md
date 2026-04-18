# Phase D — hybrids, interpretation memo

**Inputs:** `results_all.csv`, per-lever CSVs, `summary.json`.
**Author-date:** 2026-04-16.
**Status:** Phase D complete (4 cells, 19 s of sim). Confirms the
Phase-F upload cohort and seeds the Phase-E stress tape design.

---

## 1. Headline ranking

4 hybrids compared against the best prior winners:

| rank | cell | local mean | maker | taker | **exp-off** | Δ vs shipped |
|---:|---|---:|---:|---:|---:|---:|
| 1 (prior) | **C1_as_g2e-06** | +2 937 | 19 | 770 | **+2 244** | **+1 361** |
| 2 | D6 m2.5 + AS-continuous | +3 053 | 16 | 771 | **+2 016** | +1 133 |
| 3 (prior) | B1 weighted_mid | +3 332 | 14 | 713 | +2 102 | +1 219 |
| 4 (prior) | B2 m2.5_t0.5 | +2 815 | 18 | 771 | +2 053 | +1 170 |
| 5 | D8 m2.5 + mild Cartea β=0.1 | +2 861 | 16 | 812 | +1 809 | +926 |
| 6 | D7 weighted_mid + AS quotes | +3 278 | 10 | 705 | +1 589 | +706 |
| 7 | D5 weighted_mid + m=2.5 + c=2 | **+3 446** | 5 | 701 | +1 012 | +129 |

**Key fact: D5 set the all-time local-PnL record** (+3 446 mean
across 85 cells tested to date), but has the **lowest expected-
official among the D-hybrids** (+1 012) because its 5 maker / 701
taker mix is almost pure-taker. This is the sharpest case in the
whole study where the local-vs-rescaled verdict diverges.

**No D-hybrid beats C1_as_g2e-06 on expected-official.** The
academic composite remains the Phase-A-to-D overall winner.

## 2. Per-hybrid verdicts

### D5 — empirical stack (weighted_mid + m=2.5 + linear skew c=2)

- Local mean: **+3 446** (all-time record)
- Expected-official: +1 012 (worst of the D-hybrids)

**Hypothesis vs result:** I expected D5 to stack the two best Phase-
B wins. Local PnL did confirm that — it is the highest local number
we've seen. But the maker fill count *collapsed* from 14 (B1_weighted_
mid) to 5. Widening maker from 1.5 → 2.5 moved the maker quotes to
prices where the weighted_mid FV no longer lined up with counterparty
flow, so the passive fills didn't materialize.

**Read:** stacking wins doesn't always compound — the FV choice and
the edge width are coupled. On *this* simulator D5 succeeds by
trading actively (701 taker fills). On the official environment
that over-fires makers 28× and under-fires takers 10×, the rescale
projects a net loss of most of the local PnL.

**Decision:** D5 is still worth an official upload (local PnL is
record-high — if local-to-official transfer is better than our
linear rescale model, D5 could beat all others). But flag it as
the "high-variance" candidate.

### D6 — AS-continuous flatten at m=2.5 (γ=5e-7)

- Local mean: +3 053
- Expected-official: **+2 016** (best D-hybrid)

**This is the cleanest D-hybrid result.** Combines:
- Phase-B B4 surprise (AS-continuous flatten instead of hard)
- Phase-B B2 winner (m=2.5 edges)
- Phase-B B1-default (wall_mid FV)

The 16 maker / 771 taker mix is almost identical to Phase-B's B2_m2.5
winner (18/771), so rescaled to similar expected-official. The
additional AS-continuous flatten term contributes the small local
PnL gain (+238 over B2_m2.5). Per §6 of Phase-B memo, AS-continuous
gave +289 on its own — here compounding on top of m=2.5 adds ~half
that.

**Decision:** Advance to Phase-F upload. This is the most
production-ready of the D-hybrids — the mechanism is simple, each
component is independently validated.

### D7 — weighted_mid FV + AS quote formula (γ=2e-6)

- Local mean: +3 278
- Expected-official: +1 589

**Hypothesis:** combining Phase-B's FV winner (weighted_mid) with
Phase-C's quote winner (AS-γ2e-6) should compound. D7 tests this.

**Result:** does not compound. D7 sits *between* its components on
expected-official: above B1_weighted_mid (+2 102) on local mean,
below C1_as_g2e-06 (+2 244) on expected-official. The weighted_mid
FV shifts the AS reservation price into places where the AS half-
spread formula produces quotes that catch fewer maker trades than
the wall_mid baseline C1 achieves.

**Interpretation:** the AS formula was tuned to the fair-value
landscape wall_mid produces; swapping to weighted_mid changes the
fair-value dynamics in ways the AS half-spread doesn't compensate
for. This is exactly the coupling we discussed — FV and edge widths
aren't independent.

**Decision:** D7 goes to Phase-F (it's still a plausible candidate
that could surprise on official), but C1_as_g2e-06 is the stronger
bet.

### D8 — mild Cartea β=0.1 on top of m=2.5 baseline

- Local mean: +2 861
- Expected-official: +1 809

**Hypothesis:** β=0.1 is an order of magnitude smaller than the
smallest β tested in Phase C (0.3). If the Cartea mechanism is
*directionally right* but β=0.3 is too aggressive, β=0.1 should
land above the baseline.

**Result:** D8 at +1 809 exp-off is +926 over shipped C_h1_alt.
This is better than any C3 cell (best was β=0.3 at +1 107). So the
hypothesis holds directionally: smaller β gives a net gain. But D8
still falls short of the non-Cartea baselines (B2_m2.5 at +2 053,
C1_as_g2e-06 at +2 244). The Cartea term adds a small cost on
average — it shifts quotes occasionally in ways that the AS formula
+ wall_mid combination doesn't need.

**Decision:** D8 is marginal. Upload-worthy *if* we have Phase-F
budget but a less strong bet than D6 or C1. List after the stronger
candidates.

## 3. Cross-phase meta-read

After B / C / D we have a clear hierarchy on this simulator:

| Tier | Cells | Exp-off range | Mechanism |
|---|---|---:|---|
| S (winner) | C1_as_g2e-06 | +2 244 | AS closed-form at tuned γ |
| A | D6, B1_weighted_mid, B2_m2.5 | +2 000 to +2 100 | Phase-B empirical + C1-adjacent |
| B | D7, D8, C1_as_g1e-7, C2_gueant_* | +1 590 to +1 810 | Variants that almost compound but don't quite |
| C | Soft-skew / flatten variants | +1 100 to +1 380 | Phase-B B3/B4 mid-tier |
| D | C3_cartea_b0.3, D5 | +1 010 to +1 110 | Cartea at the weakest β, or high-local-taker hybrid |
| Baseline | Phase-10 / shipped C_h1_alt | +883 | — |
| Below baseline | C3_cartea b≥0.6, C5 | +193 to +671 | Cartea too aggressive; target-v2 on ASH |

The **S-tier single cell and A-tier of three** — plus one or two
"surprise candidates" like D5 — constitute the Phase-F upload list.

## 4. Scope deltas vs PLAN.md after Phase D

| Item | Previously planned | Revised after D |
|---|---|---|
| Phase-D hybrid count | 4 (D5, D6, D7, D8) | 4, all ran, none dominate C1 |
| Phase-F tier-1 (confident uploads) | 3 (C_h1_alt refresh + B-winners) | **4** (+ C1_as_g2e-06 and D6) |
| Phase-F tier-2 (plausible) | 5 | **4** (D5, D7, D8, C3_b0.3) |
| Total Phase-F uploads | ~12 | **~10** (trimmed 2 near-duplicates) |

## 5. Phase-F upload cohort (finalized)

| batch | candidate | source | exp-off | upload rationale |
|---|---|---|---:|---|
| F1 control | shipped `C_h1_alt` on buy_hold pepper | — | +883 | anchor the ASH-with-buy_hold PEPPER reference |
| F2a | **C1_as_g2e-06** | Phase-C top | **+2 244** | overall winner across 85 cells |
| F2b | **D6_m25_as_continuous** | Phase-D | +2 016 | robust AS + empirical stack |
| F2c | **B1_weighted_mid** | Phase-B | +2 102 | FV winner; simplest win |
| F2d | **B2_m2.5_t0.5** | Phase-B | +2 053 | edge winner; most similar to shipped |
| F3a | D5 (record local mean) | Phase-D | +1 012 | tests "is the linear rescale too harsh?" |
| F3b | D7 weighted_mid + AS | Phase-D | +1 589 | FV × AS combination probe |
| F3c | D8 m=2.5 + Cartea β=0.1 | Phase-D | +1 809 | tests mild alpha-skew |
| F3d | C1_as_g5e-7 | Phase-C (alt) | +1 974 | safer γ than F2a |
| F3e | C3_cartea_b0.3 | Phase-C | +1 107 | only cartea cell above baseline |

**10 uploads.** Tier F2 (4 strongest, should all beat shipped) +
Tier F3 (5 plausible candidates testing different mechanisms) + F1
control refresh. All within the original budget.

## 6. What Phase D did NOT test (feeds Phase E)

1. **Non-parametric fair-value tuning.** Every hybrid uses a
   parametric FV (weighted_mid, wall_mid). A blended FV
   (e.g. 0.5 × weighted_mid + 0.5 × ewma_mid) might outperform both.
   Not in scope here.
2. **Hybrids that include the `quad_c4` skew (Phase-B B3 runner-up).**
   D5 used linear_c2 because it was B3's outright winner. Quadratic
   might behave differently on mixed-regime tapes.
3. **Stress-test robustness.** D5's record local-PnL and low
   expected-official depends strongly on the local fill-model. A
   harder tape (narrow spread, high vol) may invert this. **Phase
   E must hit D5 hard with all 6 ASH stress tapes.**

## 7. Files

```
outputs/round_1/ash_deep_dive/phase_d/
  PHASE_D_MEMO.md                 (this file)
  summary.json
  results_all.csv                 (4 rows)
  D5/results.csv, D6/results.csv, D7/results.csv, D8/results.csv
```
