# IMC Prosperity Trading Bot

## Project Structure

- `src/core/` — engine modules (signals, risk, fair_value, config, execution)
- `src/backtest/` — replay, simulator, metrics, sweeps, comparison
- `src/scripts/` — runners for review, sweeps, comparisons
- `tests/` — pytest suite (unit + integration)
- `data/raw/tutorial_round_1/` — replay data
- `outputs/` — review packs, sweep results, comparison reports

## Running

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/ -v
PYTHONPATH=. .venv/bin/python -m src.scripts.run_review --label baseline
```

## Evaluation Rules

### Evidence calibration

- Do not make categorical claims from local replay when fill behavior
  or simulator behavior may differ from the official environment.
- Phrase conclusions proportionally to the evidence:
  - "under the current local replay / tested range"
  - not "inherent" or "cannot be fixed" unless truly proven.

### Large-jump sanity checks

- When a new estimator or config shows a large aggregate improvement,
  run a quick cross-slice sanity check and a lightweight visual /
  timestamp review before spending more tuning budget around it.
- Do not assume a large aggregate gain is automatically robust.

### Redundant estimator handling

- If two estimators behave identically on the current dataset, keep
  both implementations if strategically useful, but treat one as
  redundant for the current sweep budget.
- Do not waste sweep capacity on estimator duplicates.

### Evaluation priority

In trading strategy evaluation, prioritize:

1. realized PnL
2. entry edge / markouts
3. inventory behavior
4. cross-slice robustness

Do not over-weight pure forecast-style metrics like MAE when trading
outcomes disagree.

## Manual-round strategy lessons (from P4-R2 "Invest & Expand" post-mortem)

**Context** (revised after full field-CDF reconstruction from 6 screenshots):
We picked (13, 37, v=50) and scored 194,779. Top 3 teams tied at 217,869
with **(15, 43, v=42)** — NOT (14, 40, v=46) as initially reconstructed.
Field size was 4,304 submitters. **We overshot by 8 integers, losing
~23,210 (~11% of top PnL).** Full post-mortem + reconstructed field CDF
in `docs/manual_round_2/LESSONS_LEARNED.md` (branch `round2-manual-challenge`).

### Mechanical lessons (always true in rank-based tournament games)

**M1 — μ-ceiling sanity check.**
For a rank-based multiplier capped at μ_max, compute the μ your pick
REQUIRES to match the target PnL. If required μ > μ_max, you've
structurally overshot — drop v until feasible. For us, (13, 37, 50)
required μ=0.905 > 0.9. Instant disqualification signal we missed.

**M2 — At the top of the payoff surface, R×S dominates μ.**
Near the optimum in a multiplicative game (gross = R·S·μ), each ±1 in v
moves μ by ~0.015-0.025 but R×S by ~8-33k. R×S loss typically exceeds
μ gain × gross beyond the cluster edge. Explicit check: `ΔR×S > Δμ ×
current_gross` ⟹ you've overshot.

**M3 — Tie-share-best creates gravitational wells.**
In any ranking game where ties share the best rank of their block:
- Being IN a cluster is neutral-to-positive (you share block's best rank)
- Being one integer BELOW a cluster is catastrophic (you sit at cluster's
  bottom)
- Being one integer ABOVE a cluster gains only the mass exactly at that
  integer — usually small
- The right play is: land AT the TOP integer of the densest cluster,
  not above, not below.

**M4 — Multiple (r, s, v) tuples produce the same net PnL.**
When reconstructing opponents' picks from a target score, ENUMERATE all
feasible v values — don't commit to one based on prior belief. Different
(r, s, v) on the same R·S·μ = const isoquant look identical from score
alone. Only field-CDF data distinguishes them.

### Field-estimation lessons (empirically calibrated from P4-R2)

**F1 — AI analyses exhibit upward bias vs real field.**
Our 4 external AI analyses gave v ∈ {30, 44, 44, 46, 50} — mean 42.8,
median 44. Real field peak: v=42. **AI consensus overshoots real field
peak by 2-4 points** because:
  - AIs assume other teams are similarly sophisticated (over-models elite)
  - AIs apply "overshoot the consensus" reasoning (double-counts at scale)
  - AIs undersample naive mass (63% of real field bid v≤36)
Rule: when aggregating external AI analyses, pick the **LOW end** of
the range, not the high end or even the mean. A-priori adjust the
aggregated picks down by 2-4 integers.

**F2 — Look for the DENSITY BAND, not the point cluster.**
The real field didn't peak at a single v. Teams clustered in a BAND
(v=37-42 held ~120 teams/integer vs ~58 outside). The optimum was the
TOP of this band (v=42 = the last integer before density drops by 2×).
Identifying the BAND edge is more robust than guessing the exact peak.

**F3 — Fields are typically bimodal: naive-low + smart-band + tail.**
P4-R2 actual: 63.5% at v≤36 (naive) + 16.6% at v=37-42 (smart band) +
10.7% at v=43-50 + 6.5% at v≥53 (tail). We (and most analyses)
over-weighted the smart band and tail. Most mass is always LOW.

**F4 — Community signals are reference-only, and typically exaggerated.**
Discord poll for P4-R2 said 21% at v=90-100. Real field had 6.5% at
v≥53. Community samples are self-selected, troll-contaminated, and
over-represent extremes. Cap community-poll weight at ≤15% in any prior.

**F5 — Don't conflate R1 and R2 populations.**
R1 "73% got 0" is about non-submitters (excluded from R2 rank pool).
Population statistics from a different round/context apply to a
different population. Always check population overlap before using.

### Process lessons (meta)

**P1 — When sub-models disagree, regress to the mean DOWNWARD.**
If your framework yields multiple defensible picks within ~10%, bias
toward the LOWER end of the range, not the higher. Reasons:
  - R×S collapses rapidly with v; being low-biased preserves optionality
  - Field almost always has more low-v mass than modeled
  - A low-biased pick is robust to naive-heavy scenarios that a
    high-biased pick cannot recover from

**P2 — Neither Bayesian-weighted EV nor minimax-regret alone is enough.**
Our Bayesian weighting overshot (v=50). Analysis 1's minimax-regret
also overshot (v=46). Minimax is marginally better but both can miss
the actual cluster by 4+ integers. **Cross-check both criteria AND
bias toward the lower candidate when they disagree by >2 integers.**

**P3 — Reconstruct before declaring.**
If you have any post-round data (even a single team's screenshot), run
the reconstruction: solve for their implied (r, s, v) and back out the
field CDF. Two data points can often uniquely identify N and the
density structure. Do this BEFORE writing final lessons — initial
reconstructions are often wrong.

### Tooling / workflow lessons

**W1 — Git worktrees for parallel branch work.**
When multiple Claude sessions share a repo with different branches,
use `git worktree add ../<name> <branch>` to get an isolated working
directory. Prevents branch-switching from one session stomping
another's edits. Applied successfully in P4-R2 to isolate manual-round
edits from parallel algo-branch activity.

**W2 — Framework survives; calibration errors are local.**
The `src/manual_rounds/invest_expand*.py` solver architecture
(priors, regret table, μ closed-form, MC validation) worked correctly.
The error was entirely in which PRIOR SHAPE to weight highest. Framework
is reusable; calibration needs fresh empirical priors per round.

### The overriding meta-rule

**When analytical rigor produces a candidate, sanity-check by asking:**

1. *"Does this pick require μ > μ_max?"* If yes, overshot — drop v.
2. *"What would need to be true about the field for this to be right?"*
   Is that scenario realistic?
3. *"Is this at the HIGH or LOW end of my candidate band?"*
   If HIGH, step down 2-3 integers and recheck. Most field errors come
   from overshoot, not undershoot.
4. *"What fraction of the field am I assuming is sophisticated?"*
   If >40%, cut it in half and re-run. Real fields are mostly naive.

### Manual-round solver framework (reusable)

`src/manual_rounds/invest_expand*.py` on branch `round2-manual-challenge`:
- Pure-stdlib solver for allocate-across-pillars-with-rank-based-pillar games
- Extends the `nash_crowd` Family 3 pattern with rank-auction support
- 52 passing unit tests, 8 commits including external-input archive +
  full post-mortem + reconstructed field CDF
- To reuse for future rounds: copy core math, build NEW priors calibrated
  to that round's field using F1-F4 adjustments, re-run regret + VoI.
