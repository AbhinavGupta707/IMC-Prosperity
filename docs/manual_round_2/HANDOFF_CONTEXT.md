# P4-R2 Manual Challenge — "Invest & Expand" — Handoff Context

Last updated: 2026-04-19. Authored during the algo-side session; this
document is structured so another session can pick up the manual-strategy
work with full context.

## 1. Problem restatement (source of truth)

Allocate integer percentages `(r, s, v)` for Research / Scale / Speed.
Constraints: `0 <= r, s, v <= 100`, `r + s + v <= 100`. Budget
`50 000 XIREC`; cost `500 * (r + s + v)`.

- `research(r) = 200_000 * ln(1+r) / ln(101)`   (concave log, 0 → 200k)
- `scale(s)   = 7 * s / 100`                     (linear, 0 → 7)
- `speed(v)`  is a **rank-based multiplier** across all submitting
  teams, linear from 0.9 (rank 1, highest v) to 0.1 (rank N, lowest
  v). **Ties share the BEST rank in the tied block**. Official
  examples:
  - `70,70,70,50,40,40,30 → ranks 1,1,1,4,5,5,7`
  - `95,20,10 → ranks 1,2,3 → mu 0.9, 0.5, 0.1`
- Non-submitters are excluded from the rank pool.
- Only the last submission before round close is counted.
- Internal scoring uses full decimals though UI and inputs are integer %.

```
gross = research(r) * scale(s) * mu
net   = gross - 500 * (r + s + v)
```

## 2. Classification

**Two-level decomposition** (proved independently in xpablolo's and
rjav1's writeups):

1. **Inner (deterministic, concave)**: for any fixed `v`, optimising
   `(r, s)` under the budget `r + s = 100 - v` has a unique first-order
   condition `s = (1 + r) * ln(1 + r)`. Always spend the full 100%
   (marginal return on both r and s exceeds the 500 cost per pct).
   At `v=0`: `(r, s) ≈ (23, 77)`. At `v=50`: `(r, s) ≈ (13, 37)`.

2. **Outer (game-theoretic, rank auction)**: `v` is a **rank-ordered
   prize contest** embedded in a log-linear investment game. Not a
   pure all-pay auction — the prize is bounded (`mu in [0.1, 0.9]`)
   and continuous in rank. It's a **Tullock-style contest with
   multiplicative externalities on concave research and linear scale**.

Under the tie rule + large N, expected `mu` collapses to a percentile
expression::

    E[mu | v_you, F_opp] ≈ 0.9 - 0.8 * P(v_opp > v_you)

with `P(v_opp > v_you)` under whatever prior you assume over the
opposing field. Because PnL is linear in `mu`,
`E[PnL] = R(r) * S(s) * E[mu] - costs` — no nested MC required.

## 3. What has been built in this repo

All under `src/manual_rounds/`:

| Module | Purpose |
|---|---|
| `invest_expand.py` | Primitives, PnL, rank computation, `(r, s)` optimiser given `mu`, prior-based `expected_mu`, `best_allocation_under_prior`. Pure stdlib. |
| `invest_expand_priors.py` | Library of opponent v-distributions: naive spikes (0, 33, 50), uniform, bimodal, trimodal, nice-number, truncated-geometric, `optimising_at_mu(mu_belief)` spike, `quant_cluster` mixture, `empirical_from_samples`. |
| `invest_expand_equilibrium.py` | Logit QRE fixed point (`symmetric_qre`), regret table (`regret_table`), candidate-grid generator (`generate_candidate_grid`). |
| `tests/test_manual_invest_expand.py` | 35 unit tests, all passing. Hard-codes the official rank examples as regression anchors. |
| `src/scripts/run_manual_invest_expand.py` | Primary runner. Prints per-prior best, top-5 by regret, top-5 by mean, QRE top-5, public-benchmark comparison. JSON output optional. |
| `src/scripts/run_manual_invest_expand_sensitivity.py` | N-sensitivity, QRE temperature sweep, benchmark head-to-head, focal-cluster stress test. |

Run with:
```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.run_manual_invest_expand --n-opponents 4500
PYTHONPATH=. .venv/bin/python -m src.scripts.run_manual_invest_expand_sensitivity
PYTHONPATH=. .venv/bin/python -m pytest tests/test_manual_invest_expand.py -v
```

## 4. External research distillation

Sources (see `/tmp/imc_research/` during this session):

- `xpablolo/imc-prosperity-4` — full minimax-regret analysis, 8k sim MC,
  `r* ≈ 23% of (100-v), s* ≈ 77%` structural law. Pick: **(16, 50, 34)**.
- `rjav1/prosperity4` (team foodio) — live leaderboard scrape + 16-agent
  ensemble. Pick: **(13, 37, 50)**. Rationale: leapfrog into the v=50
  tie cluster.
- `noelkei/simplex-imc-prosperity-26` — canonical wiki capture.
- `s-h-a-n-i-l/imc-prosperity` — interactive sim with `MAX_SPEED_INVESTMENT=88`.
- `v-x-zhang/imc-prosperity-4-quantsc` — 6 070-row R1 leaderboard scrape.
- KengLL/Prosperity-3-Neko — P3 problems only, not this game. Their
  container-picks method (power-law crowding vs Nash, safety-margin
  bias) is conceptually relevant but not directly applicable.

**Field size estimate**: 3 500 – 5 500 submitters (triangulated from
22 130 registered × 27.8% active × ~80% manual-participation). Default
to **N = 4 500**.

**Published picks (collated)**:

| Source | (r, s, v) | Rationale |
|---|---|---|
| xpablolo minimax | (16, 50, 34) | Min max-regret across 6 MC scenarios |
| xpablolo alt | (16, 48, 36) | Slight overshoot if field mean ≥ 30 |
| rjav1 foodio | (13, 37, 50) | Leapfrog v=40 Nash cluster, tie v=50 |
| ensemble bayesian | (15, 45, 40) | Balanced prior, E[μ] ≈ 0.75 |
| behavioral | (14, 42, 44) | Keynesian beauty contest |
| level-k L0=33 | v ≈ 40s | Convergence from UI default v=33 |
| user seed (flagged) | (23, 77, 0) | **Dominated** — only wins if >80% field coasts |

## 5. This session's analysis output

Run against **N=4500** with the `rjav1_blend` prior (20% coasters, 45%
naive anchors at 25/33/40/50, 10% quants, 5% aggressive):

**Top 5 by ascending max-regret (robustness)**:
1. `(17, 50, 33)` — mean 215 584, worst −6 160, max regret 273 539
2. `(16, 50, 34)` — mean 216 695, worst −7 027, max regret 281 341 ← **matches xpablolo**
3. `(16, 49, 35)` — mean 212 387
4. `(16, 48, 36)` — mean 208 012
5. `(16, 47, 37)` — mean 203 572

**Top 5 by mean PnL**: nearly identical set, reordered.

**Best under rjav1_blend single prior**: `(15, 45, 40)` at 234 137
(matches the ensemble "bayesian" pick).

**QRE pure-NE behaviour**: no pure-strategy NE (oscillates at low T —
classic all-pay). Soft-QRE at T=500k lands at v ≈ 35–39, T=100k at
v ≈ 43–47, T=30k at v ≈ 58–62. These do *not* correspond to the
actual field — they describe "what would happen if every team
rationally best-responded under a common prior", which is likely
far more aggressive on v than the actual field.

**Focal-cluster stress test — critical swing**:

If the field concentrates 60% at v=50:
- `(13, 37, 50)` scores **169 663**
- `(16, 50, 34)` scores **40 626**

If the field concentrates 60% at v=33–40:
- `(16, 50, 34)` scores **233 621–246 896**
- `(13, 37, 50)` scores **169 663**

**This is the genuine decision**: where does the focal mass live?

## 6. Strategic framing — the real choice

The geometry of plausible allocations lives on a 1-D manifold: always
spend 100%, always `r ≈ 23%·(100-v)` and `s ≈ 77%·(100-v)`. The only
live lever is **v**. Every serious public analysis sits in
**v ∈ {33, 34, 36, 40, 44, 45, 50}**.

Three archetypes:

| Archetype | (r, s, v) | Bet | Upside | Downside |
|---|---|---|---|---|
| **Tie v=33** | (17, 50, 33) | Field naive-thirds | Ties to rank 1 if field clusters at 33 | Crushed if field clusters at ≥40 |
| **Leapfrog 33** | (16, 50, 34) | Field skewed low | Sole rank-1 over 33 cluster; robust mean | Collapses vs v=50 cluster |
| **Tie v=50** | (13, 37, 50) | Focal mass at 50 | Ties to rank 1 if field clusters at 50; highest worst-case | Pays 50×500 cost if field is below 50 |

My current recommendation, absent a strong belief about focal
location: **(r=16, s=50, v=34)** as the highest-mean and
"second-most-robust" pick. If the parallel session wants a pure
downside-protection play, switch to **(r=13, s=37, v=50)** — worst
case in my head-to-head is +50k, strictly positive across every
prior tested.

**Never submit the user's seed `(23, 77, 0)`.** It's dominated on
every realistic prior; wins only if >80% of the field coasts.

## 7. Open questions for the parallel session

The next session should investigate:

1. **Discord / leaderboard scraping**. rjav1 pulled R1 manual
   leaderboard data live. Can we scrape anything during R2 for
   early signal? `https://prosperity.imc.com/results/round/3/manual/data`
   returns 401 mid-round per rjav1; leaderboard pagination still
   exposes partial state.
2. **Field behaviour prior calibration**. The default `rjav1_blend`
   prior in `invest_expand_priors.py` is a guess. Empirical calibration
   ideas:
   - Query the P4-R1 manual perfect-score rate as a proxy for "quant
     fraction" (rjav1 found 37.3%).
   - Inspect v-xzhang leaderboard CSV for R1 score variance as a
     proxy for field sophistication heterogeneity.
   - Ask about our own team's past Prosperity placements — if we
     typically finish top-5%, assume the field is more sophisticated
     than average.
3. **Cluster-at-50 probability**. Key deciding factor between
   `(16, 50, 34)` and `(13, 37, 50)`. Inspect whether the official
   UI default-renders any single pillar at a particular value (v=50
   might be the UI slider midpoint, causing a cluster). rjav1's scrape
   could confirm.
4. **Late-submission ladder**. Since resubmission is free, the
   parallel session can stage submissions:
   - T−24h: submit `(16, 50, 34)` to signal intent.
   - T−6h: check leaderboard drift if any signal leaks.
   - T−1h: final pick based on any updated prior.
   Confirm whether intermediate submissions are visible to others.
5. **Submit-note automation**. Add `SubmissionNote` artefact in
   `src/manual_rounds/submission_note.py` style to render a final
   decision document at commit-time.
6. **Sensitivity to `MAX_SPEED_INVESTMENT` constraint**. s-h-a-n-i-l's
   sim used `MAX_SPEED_INVESTMENT = 88`. Cross-check whether the
   official rules cap v somewhere below 100 in practice.
7. **Non-integer handling edge case**. The UI rounds multipliers to
   1 decimal; internal scoring uses full decimals. Confirm this
   doesn't alter rank computations (it shouldn't — rank is computed
   on raw integer v inputs).

## 8. Parallel-session starting point

```bash
cd /Users/abhinavgupta/Desktop/IMC
git status                                    # verify branch
PYTHONPATH=. .venv/bin/python -m pytest tests/test_manual_invest_expand.py -v
PYTHONPATH=. .venv/bin/python -m src.scripts.run_manual_invest_expand --n-opponents 4500
PYTHONPATH=. .venv/bin/python -m src.scripts.run_manual_invest_expand_sensitivity
```

Then read:
- `src/manual_rounds/invest_expand.py` (300 LOC, pure stdlib) — the math
- `src/manual_rounds/invest_expand_priors.py` (180 LOC) — prior library
- `docs/manual_round_2/HANDOFF_CONTEXT.md` (this file)
- Optionally fetch the xpablolo/rjav1 repos cited in §4 for the full
  external analyses.

Current best candidates (in priority order for the parallel session):

1. `(r=16, s=50, v=34)` — **tentative lead pick** if we don't see a
   v=50 cluster signal.
2. `(r=13, s=37, v=50)` — **backup** with best worst-case PnL (+50k
   floor). Switch here if the field signals a v=50 focal point.
3. `(r=17, s=50, v=33)` — **most-robust** under current prior library,
   but slightly lower mean. Only pick if you specifically believe the
   field is naive-thirds dominated.

**Do not submit `(23, 77, 0)`.** It's the default textbook FOC answer
at μ=0.9 and it will lose to anyone playing a non-zero v if the field
is not dominated by coasters.
