# P4-R2 Invest & Expand — Post-mortem and Lessons Learned

Dated 2026-04-20 (round-close day). Documents what we picked, what the
top teams picked, why we were wrong, and what to take forward.

## Outcome

**Our submission**: `(r=13, s=37, v=50)` → R2 manual PnL ≈ 194,779
**Top 3 teams' submission**: reconstructed as `(r=14, s=40, v=46)` → R2
manual PnL = 217,870 (3-way tie at rank 1 of combined leaderboard)
**Our gap to top**: ~23,091 XIRECs (~10.6% PnL short)

The three tied top teams: abacus (US), market maxxer (India),
Open for Quant Jobs (Switzerland). Further top-9 teams scored between
217,551 and 217,870 — all within a ~300 XIREC band, strongly suggesting
a tight cluster at v=46.

## Reconstruction (math-verified)

For top-team net = 217,870 assuming R1 perfect score (87,995):
`R(r) × S(s) × μ − 50,000 = 217,870`  ⟹  `R×S·μ = 267,870`

Testing each v with its FOC-optimal (r, s):

| v | (r,s) | R×S | Required μ | Achievable? |
|---|---|---:|---:|---|
| 45 | (14, 41) | 336,806 | 0.795 | ✅ |
| **46** | **(14, 40)** | **328,591** | **0.815** | ✅ most likely |
| 47 | (14, 39) | 320,376 | 0.836 | ✅ |
| 48 | (13, 39) | 312,405 | 0.858 | ✅ |
| 49 | (13, 38) | 304,200 | 0.881 | ✅ |
| **50** | **(13, 37)** | **296,195** | **0.905** | **❌ exceeds μ_max=0.9** |

**v=50 literally cannot produce the top score** — structural proof it
wasn't the optimal pick. The top teams almost certainly picked v=46,
which matches Analysis 1's published recommendation exactly.

## Field structure (inferred from 2 data points)

From top teams' μ=0.815 at v=46:
- **10.6% of field bid strictly above v=46** (~478 teams out of 4500)

From our μ=0.826 at v=50:
- **9.2% of field bid strictly above v=50** (~413 teams)

Difference: ~63 teams (1.4% of field) bid v ∈ {47, 48, 49, 50}.

Upper-tail shape: the field had a meaningful ~9% tail at v > 50,
which gave us some μ lift but not enough to compensate for R×S loss.

## Cost decomposition

| Component | Top (v=46) | Us (v=50) | Delta |
|---|---:|---:|---:|
| R×S | 328,591 | 296,195 | **−32,396** |
| μ | 0.815 | 0.826 | **+0.011** |
| Gross | 267,802 | 244,717 | −23,085 |
| Net PnL | 217,802 | 194,717 | −23,085 |

We traded 32k of R×S for 0.011 of μ. At the relevant gross of ~296k,
the μ gain is worth ~3k. The R×S loss, valued at field-average μ~0.82,
is worth ~26k. **Net loss: ~23k** — arithmetic confirmed.

## What went wrong — root causes

### 1. Over-weighted internal meta-reasoning
- We gave the hand-built `active_submitters_only_blend` prior 40% weight
- That prior modeled a v=50 Schelling cluster (halve-it heuristic) at
  12% field share and sophisticated-team spread across v=36-50
- Reality: v=50 cluster was much smaller (~3-5%), and the sophisticated
  cluster concentrated tightly at v=46 (not spread)

### 2. Under-weighted external AI consensus
- 3 of 4 external AI analyses landed at v=44-46 (A1, A2, A4)
- 1 outlier at v=30 (A3)
- We listed v=46 as Tier 1B but made v=50 primary via meta-game argument
- Should have taken the 3-of-4 convergence as stronger evidence of
  field equilibrium than our internal prior

### 3. Missed the μ-ceiling sanity check
- At v=50 with (13, 37), reaching the top score required μ=0.905
- μ is capped at 0.9 — structurally impossible
- Should have caught this as "your pick cannot win even in the best case"
- Would have forced us one cluster level down to v=46 or v=47

### 4. Mis-calibrated the meta-game recursion
- "Overshoot the AI consensus" heuristic assumes teams will pile onto
  the AI consensus, creating a cluster that penalises pickers-at-consensus
- Reality: only ~11% of field was at v ≥ 47. That's not a "cluster" in
  the pileup sense — the AI consensus WAS the equilibrium, not a crowd-
  magnet requiring escape
- The heuristic was right in principle but wrong for this specific field

### 5. Schelling-at-v=50 hypothesis was too strong
- We assumed the round-number "halve-it" heuristic would create a large
  cluster at v=50, and tying into it would pay off
- Real field had ~9% at v > 50 but a much smaller spike AT v=50 specifically
- Most of the "overshoot mass" was in v=55-100 (genuine speed racers +
  spite voters), not at v=50 (rational overshooters)

## Transferable lessons

### L1 — Trust AI consensus
When 3+ rigorous AI analyses converge on a value, treat it as the
expected equilibrium. Bayesian prior on that cluster ≥ 50%. Don't
overshoot unless you have hard evidence of meta-cascade.

### L2 — Sanity-check the μ-ceiling
For any rank-tournament pick with μ_max cap, verify your pick CAN
achieve the top score at μ_max. If not, you've overshot structurally.
Drop v until feasible.

### L3 — Minimax-regret > Bayesian weighting with uncertain priors
When subjective priors are themselves uncertain, minimax-regret is
more robust. Analysis 1 used it and won. Our weighted-EV framework
landed one cluster level off.

### L4 — R×S dominates μ at the top of the payoff surface
Near the optimum in a multiplicative game, ±1 in v shifts μ by ~0.01
but R×S by ~8k. At field-avg μ, the R×S loss dominates the μ gain.
Check "R×S_loss vs μ_gain × current_gross" explicitly.

### L5 — Tie-share-best = coordination, not crowding
In games where ties share the best rank in their block, the rigorous-
analysis focal point is a gravitational well, not a trap. Land ON the
rigorous consensus. Being one step below is punished (strictly below
cluster); being one step above gains negligibly.

### L6 — Community chatter is reference-only
Discord polls with 42 voters, self-selected samples, trolling, and
posturing are not reliable field estimators. Weight them ≤ 25%. The
poll's 21% at v=90-100 inflated our upper-tail estimate; the real
tail was ~9%, concentrated in the 55-80 range not 90-100.

### L7 — Don't conflate R1 and R2 populations
"73% got 0 in R1" refers to non-submitters, who are excluded from
R2's rank pool. Different populations. Don't apply R1 stats as R2
priors without checking population overlap.

### L8 — Use git worktrees for parallel branch work
When multiple Claude sessions share a repo, branch-switching can
stomp edits. `git worktree add ../name branch` gives you an isolated
working directory tied to a specific branch — bulletproof against
parallel-session interference.

## The meta-rule

**When our analytical framework produces multiple defensible picks
within ~10% of each other, bias toward the pick most widely derived by
independent rigorous external analyses, not the one produced by our
most-confident internal reasoning.**

Internal meta-reasoning (like "overshoot the AI consensus") should
only be the tiebreaker when external consensus is weak or
contradictory. In our case, external consensus was strong (3-of-4 at
v=44-46) and we should have deferred to it.

## What would have won

Had we submitted `(r=14, s=40, v=46)`:
- μ = 0.815 (tied at the v=46 cluster's best rank)
- Net PnL = 217,802
- Rank: tied at #1 with the top 3 teams (3-way tie → 4-way tie)
- Qualified comfortably for next round with ~33k buffer

## Framework validation

Despite the wrong pick, the analytical framework itself worked:
- FOC math: correct
- Tie-share-best analysis: correct
- Schelling-cliff identification: correct
- R×S-vs-μ tradeoff: correctly identified
- v=46 WAS in our Tier 1B

The error was one of **calibration**, not **framework**. The
`src/manual_rounds/invest_expand*.py` solver is sound and reusable
for future rounds of this family.

## Action items for next round

1. **Default to external rigorous consensus** when 3+ independent AI
   analyses agree to within 2 integer points.
2. **Run the μ-ceiling check** before any submission. Our solver
   should print a warning if the pick requires μ > 0.9 to hit a target.
3. **Make minimax-regret the primary selection criterion** in
   `run_manual_invest_expand_final.py`. Weighted EV becomes secondary.
4. **Cap Discord weight at 15%** in the default prior library.
5. **Worktree protocol**: always create a dedicated worktree for
   branch-sensitive work when parallel sessions exist.

## Score outcome

Our rank post-R2: likely between 50-200 (need full leaderboard to
confirm). Still qualifies for Phase 2 given total > common 200k
threshold. Left ~23k on the table vs the achievable top-3 tie.
