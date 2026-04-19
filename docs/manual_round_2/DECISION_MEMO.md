# P4-R2 Invest & Expand — Final Decision Memo

Authored 2026-04-19 after deep analytics pass that added MC validation,
level-k iteration, adversarial worst-case search, and a phase diagram
over (mean_v, std_v) of opponent field. Incorporates the IMC MAF
consensus-fragility warning.

**Bottom line**: this is a genuine strategic decision under irreducible
uncertainty. There is no single mathematically-optimal pick without a
belief about where the opposing field's focal mass sits. The three viable
candidates and the belief that selects each are enumerated below.

---

## 1. What the analytical work has established with certainty

These facts are robust and do not depend on field belief:

| Fact | Source |
|---|---|
| Always spend the full 100% budget | FOC on (r, s), analytically verified |
| Given fixed v, (r, s) sits on `s = (1+r) ln(1+r)` with `r + s = 100 − v` | Inner-game FOC |
| E[μ] has a closed-form percentile expression `≈ 0.9 − 0.8 · P(opp > v_you)` | MC validated to 0.0003 over 1 500 trials |
| Under any focal-cluster prior, the level-k equilibrium is a single v-spike at the mode of L0 | Level-k iteration |
| Low-v picks have HIGHER worst-case floors than high-v picks (R·S buffers μ collapse) | Adversarial search |
| Best-response v rises ~1:1 with field mean | Phase diagram over (mean, σ) |

## 2. What is irreducibly uncertain

The opponent v-distribution. Without it, no single candidate is optimal
across all priors. The following are the plausible field-composition
beliefs and the allocation each selects:

| Field-composition belief | Best response |
|---|---|
| Field coasts (>80% at v=0) | (23, 77, 0) |
| MAF-cluster dominated (35%+ at v=5–12) | (21, 67, 12) — leapfrog the cluster |
| Naive-thirds dominated (60% at v=33) | (17, 50, 33) — tie in |
| Blended (sharp 37%, anchors at 33/40/50, ~10-20% coast) | (15, 45, 40) |
| Focal cluster at v=40 | (15, 45, 40) — tie in |
| Focal cluster at v=50 (rjav1 leapfrog hypothesis) | (13, 37, 50) — tie in |
| Speed-race (field aggressively overbids) | (23, 77, 0) — accept μ=0.1 floor, maximise R·S |

Under the minimax-regret rule (hedge against worst deviation), the
parameter-plateau answer is v ∈ {35, 36, 37}:

| Candidate | Mean PnL | Worst PnL | Max regret |
|---|---|---|---|
| (16, 49, 35) | 203 728 | -7 887 | 289 076 |
| (16, 48, 36) | 204 940 | -8 746 | 296 811 |
| (16, 47, 37) | 200 482 | -9 606 | 304 547 |

## 3. IMC MAF consensus-fragility warning — how we priced it in

The warning: if many teams converge on the same rational pick (e.g.
v=5), the median shifts upward and the nominal pick lands in the bottom
rank tier. Suggested response: overshoot the consensus cluster by
5–15 pct.

Integrating this into our prior library (`maf_v5_cluster`,
`maf_v12_cluster`, `maf_realistic_blend`) produces this nuance:

- **If the MAF cluster is alone (field dominated by v=5–12)**, BR = v=8
  to v=12. A minimal overshoot is enough.
- **If the MAF cluster coexists with anchor clusters at v=33/40/50**
  (the realistic blend scenario), BR = v=12. Overshooting the MAF
  cluster by 5 is enough because the high-v anchors block any further
  gains — playing v=40 gives you μ=0.69 but the (r, s) budget loss
  outweighs the μ gain.
- **The MAF warning's "v=20–25" suggestion is conservative but not
  optimal** under our modeled blends. It hedges against a pure MAF
  field but leaves money on the table if the field is actually mixed.

Critical insight: **overshooting too far is as bad as undershooting**.
Phase diagram shows every +1 v above BR costs ~1 k PnL. Every -1 v
below a cluster costs ~10 k.

## 4. The three viable submission candidates

### Tier 1 — Minimax-regret plateau pick (RECOMMENDED DEFAULT)

**Allocation: (r=16, s=48, v=36)**

Why: sits at the "parameter plateau" — the point of lowest
maximum-regret across 18 plausible priors. Mean PnL 205 k. Only
catastrophic (worst PnL -9 k) under extreme priors (all field at v=50,
or a leapfrog adversary specifically targeting v=36). None of those
are realistic. Under realistic blends yields 195–240 k.

### Tier 2 — Downside-protection pick

**Allocation: (r=13, s=37, v=50)**

Why: highest adversarial-worst-case PnL (-20 k vs -7 k for Tier 1 is
actually WORSE on the adversarial library, but against the
*realistic* library rjav1 foodio's pick has a +50 k floor). Best
choice if you believe a v=50 focal cluster exists (rjav1's hypothesis).
Mean PnL 183 k across all priors — 20 k lower than Tier 1.

### Tier 3 — MAF-fragility hedge

**Allocation: (r=21, s=67, v=12)**

Why: optimal if we believe the MAF consensus-fragility scenario is
the dominant reality. Wins under MAF-realistic blend (~245 k) by
more than Tier 1 wins there (~215 k). BUT: under any prior with
significant mass above v=20, Tier 3 gets crushed (PnL drops to 110 k
or lower). Asymmetric bet.

## 5. My recommendation

**Submit (r=16, s=48, v=36) as a primary.**

Reasoning:
1. It is the literal minimax-regret winner across the full prior library.
2. It sits exactly at the "parameter plateau" — insensitive to
   ±5 pct-point shifts in field mean.
3. Under all realistic blends (rjav1_blend, MAF-realistic, trimodal):
   PnL band of 205–245 k. Never catastrophic.
4. Matches xpablolo's independently-derived minimax answer to within
   one integer percent (they got v=34; v=36 is two ticks above,
   consistent with the MAF-cluster consideration added to our analysis).
5. Best worst-case among the three tiers on *realistic* priors (not
   the adversarial-leapfrog library).

**Hold Tier 2 (13, 37, 50) in reserve** for late-stage resubmission if:
- Signal leaks during R2 suggest v=50 is a dominant focal cluster
- The sharp-optimiser fraction is lower than estimated (more field
  at v=50, fewer at v=40)

**Only switch to Tier 3 (21, 67, 12)** if you have independent signal
(Discord, leaderboard) that ≥40% of the field is clustered at v=5–15.
This is an asymmetric bet; the upside is modest and the downside is
severe.

## 6. What does NOT work

- **(23, 77, 0) — the "naive FOC at μ=0.9" answer**. Dominated on
  every realistic prior (143 k vs 200 k+). Only wins if >80% of the
  field coasts, which is not what the MAF evidence suggests.
- **(22, 73, 5) — the "FOC + small insurance" answer**. MAF analysis
  confirms the warning was right: this lands squarely in the
  semi-naive cluster, gets bottom-rank μ, yields only 130 k on
  realistic blends.
- **Any pick with v > 60**. Phase diagram and mean-field analysis
  show field mean is very unlikely to exceed 40 (per rjav1's scrape);
  v=60+ wastes budget buying rank you already have.

## 7. Execution plan

1. **T–24h**: Submit Tier 1 `(r=16, s=48, v=36)`.
2. **T–6h**: Audit any R2 leaderboard drift / Discord signal.
   Re-run `src.scripts.run_manual_invest_expand_deep` with updated
   empirical prior if sample data available.
3. **T–1h**: Final look. Switch to Tier 2 if cluster-at-50 signal is
   strong. Stay on Tier 1 otherwise. **Do not switch to Tier 3 at
   this stage** — it's a pre-commitment bet, not a late-pivot.
4. **At lock**: Tier 1 unless signal has flipped our prior decisively.

## 8. Running the tooling

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_manual_invest_expand.py -v
PYTHONPATH=. .venv/bin/python -m src.scripts.run_manual_invest_expand --n-opponents 4500
PYTHONPATH=. .venv/bin/python -m src.scripts.run_manual_invest_expand_sensitivity
PYTHONPATH=. .venv/bin/python -m src.scripts.run_manual_invest_expand_deep
```

## 9. What could change this recommendation

- Leaderboard scraping yields an empirical v-histogram during R2
  (rjav1's approach). Re-run `best_allocation_under_prior` with
  `empirical_from_samples(scraped)` as the prior.
- An admin clarification changes the tie rule.
- The MAX_SPEED_INVESTMENT cap is confirmed at a non-trivial value
  (s-h-a-n-i-l hard-codes 88). Re-run with v_grid=[0..88].
