# Round 1 Implementation Plan

## Purpose

This document is the controlling plan for Round 1 research, strategy development, testing, and upload selection.

It is designed to be used by Claude Code inside the existing repo and existing engine, not in a separate standalone project.

The goal is not to jump straight to a final bot.
The goal is to:

1. understand the new products deeply
2. identify the dominant edge(s)
3. build the simplest viable strategy family per product
4. test parameters in a disciplined way
5. produce a short official-upload shortlist
6. use IMC official results as the final source of truth

---

## Core principles

### 1. Official IMC results are the source of truth
Local replay, internal backtests, and Monte Carlo are research tools.
They are useful for:
- idea screening
- robustness checks
- debugging
- narrowing candidates

They are not the final ranking authority.

When local and IMC disagree:
- trust IMC
- use local tools only to generate the next better candidate faster

### 2. Find the dominant edge before building complexity
Do not assume the most elegant model is the best model.
For each product, first determine whether the simulator is primarily paying for:
- passive spread capture
- fair-value inference
- trend following
- local mean reversion
- some hybrid of these

### 3. Separate three layers of reasoning
For each product, force the analysis into three layers:

**Mechanism layer**
- what is the asset doing?
- what is the likely fair value?
- what is the spread / book structure?
- what bot behavior may be present?

**Exploitation layer**
- how should a bot monetize this?
- maker, taker, or mixed?
- what thresholds matter?
- how should inventory be handled?

**Validation layer**
- how do we know the edge is real?
- what do the markouts say?
- what do the review packs say?
- what does IMC say?

### 4. Keep strategy families simple until proven otherwise
Do not overcomplicate early.
No baskets/options/trader-ID/etc. unless the round explicitly requires them.

For Round 1, prefer:
- product classification
- fair-value selection
- execution design
- inventory/capacity discipline
- review packs
over exotic modeling.

### 5. Do not self-suppress too early
Inventory control is important, but in simulator environments it can also prematurely kill profitable business.
So all inventory skew / flattening / recovery logic must be reviewed with:
- fill count
- position path
- time near limits
- whether good quoting is being shut off too early

### 6. Phrase conclusions proportionally to evidence
Use language like:
- under the current local replay
- leading hypothesis
- supported by current sample

Avoid:
- inherent
- cannot work
- definitely the mechanism

unless truly proven.

---

## Repo structure for Round 1

Work inside the same repo used for the tutorial engine.

Do not create a separate repo or duplicate the engine.

### Use a new branch
Suggested branch:
- `round1-research`

### Add round-specific structure
Use this structure or the closest clean equivalent:

```text
data/
  raw/
    round_1/
      prices_round_1_day_0.csv
      prices_round_1_day_1.csv
      prices_round_1_day_2.csv
      trades_round_1_day_0.csv
      trades_round_1_day_1.csv
      trades_round_1_day_2.csv

outputs/
  round_1/
    research/
    charts/
    sweeps/
    review_packs/
    notes/

docs/
  round_1/
    implementation_plan.md
    asset_dossiers.md
    strategy_memo.md
    upload_plan.md

src/
  scripts/
    round_1/
      run_round1_dossier.py
      run_round1_fv_compare.py
      run_round1_sweeps.py
      run_round1_review.py
      run_round1_candidates.py
      export_round1_submission.py

  strategies/
    round_1/
      ash_coated_osmium.py
      intarian_pepper_root.py
```

### Shared engine stays shared
Keep using:
- `src/core/`
- `src/backtest/`
- `src/trader.py` orchestration model
- existing export/validation flow
- generic review/sweep tooling where possible

Round-specific work should be separate in:
- data
- outputs
- docs
- strategy modules
- round-1 scripts

---

## Working assumptions to test, not trust blindly

Current leading hypotheses from first-pass analysis:

### ASH_COATED_OSMIUM
Leading hypothesis:
- stable-anchor product
- structural fair near 10000
- likely maker-first / spread-capture product
- local quote-centering may matter, but anchor likely dominates structural fair

### INTARIAN_PEPPER_ROOT
Leading hypothesis:
- deterministic or near-deterministic trend-fair product
- visible prices may be oscillating around a clean linear drift
- likely exploitable through trend-fair tracking plus local reversion

These are leading hypotheses only.
They must be tested through:
- per-day checks
- per-slice checks
- residual analysis
- strategy markouts
- official IMC uploads

---

## Deliverable standards

Every major phase should produce:
- a small markdown summary
- any supporting tables/charts
- a clear conclusion
- a list of what remains uncertain

Do not skip the write-up stage.

---

# Phase 0 — Setup and repo check

## Goal
Make sure the repo, data, outputs, and scripts are correctly organized before research begins.

## Tasks
1. create and switch to the new branch
2. confirm round-1 data locations
3. create round-1 output folders
4. inspect existing scripts that can be reused
5. identify what generic tooling already exists and what round-1-specific wrappers need to be added

## Deliverables
- `outputs/round_1/notes/phase0_setup.md`

## Acceptance criteria
- data paths confirmed
- output structure created
- no code changes yet except minimal setup if needed
- clear list of reusable scripts and modules

---

# Phase 1 — Product dossiers (deep market-structure analysis)

## Goal
For each product, build a deep market-structure dossier before designing strategies.

Products:
- ASH_COATED_OSMIUM
- INTARIAN_PEPPER_ROOT

## For each product, analyze:

### A. Price and spread structure
Produce:
- mid-price plot
- spread plot
- spread histogram
- summary stats:
  - min / max / mean / median / std of mid
  - min / max / mean / median / std of spread
- bid/ask level frequency
- visible depth/volume by level
- day-by-day comparison
- per-time-slice comparison

Questions to answer:
- does this look anchored?
- trending?
- mean-reverting?
- regime-switching?
- one-sided?
- wide spread / easy maker product?
- narrow spread / taker-oriented product?

### B. Fair-value candidates
Compare at minimum:
- anchor (if plausible)
- mid
- microprice
- rolling mid
- weighted mid
- EWMA
- depth mid
- wall mid
- filtered wall mid (if relevant)

For each estimator, compute/report:
- next-mid fit
- short-horizon markout quality
- coverage
- distinctness vs plain mid
- distinctness vs strongest current estimator
- responsiveness / value-change frequency

Important:
Do not rank on fit alone.
Rank using:
1. strategy usefulness
2. markouts
3. coverage
4. only then prediction-style metrics

### C. Residual analysis
For the strongest fair-value candidates:
- plot residuals = mid - fair
- residual mean/std
- histogram
- asymmetry
- rough mean-reversion tendency
- variance by time slice
- whether residual behavior differs by day

Questions:
- does price snap back to fair?
- drift away from fair?
- behave asymmetrically?
- offer cleaner buy-side than sell-side opportunities?

### D. Bot / microstructure behavior inference
Best-effort analysis only.

Inspect:
- persistent large walls
- moving walls
- repeated quote sizes
- one-tick undercutting
- trade clustering by offset from fair
- possible hidden liquidity between touch levels
- whether one side seems more aggressive
- whether maker or taker edge seems dominant

Questions:
- are large walls likely informative?
- is the market paying for inside-touch quoting?
- is there evidence of stale spread capture?
- is one side consistently easier?

## Deliverables
For each product:
- charts
- tables
- one markdown product dossier
- one concise conclusion:
  - what the product appears to be
  - what fair-value family looks strongest
  - whether maker, taker, or mixed edge seems dominant
  - what still needs verification

Suggested files:
- `outputs/round_1/research/ash_coated_osmium_dossier.md`
- `outputs/round_1/research/intarian_pepper_root_dossier.md`

## Acceptance criteria
- each product has a real dossier
- hypotheses are stated clearly
- uncertainty is explicit
- no strategy implementation yet

---

# Phase 2 — Strategy-family proposal

## Goal
Translate the product dossiers into the simplest viable strategy family per product.

## For each product, propose:

### 1. Strategy classification
Examples:
- stable-anchor market maker
- trend-fair with local reversion
- asymmetric taker around hidden fair
- hybrid maker+taker

### 2. Primary fair value
Name the primary estimator and fallback(s).

### 3. Execution style
Specify:
- maker-first, taker-first, or mixed
- initial taker conditions
- initial maker quote logic
- initial inventory skew
- initial flatten/recovery logic

### 4. Risks
Explicitly list:
- what assumption this depends on
- what could break on official IMC
- whether passive fills are crucial
- whether the strategy is highly sensitive to one parameter

## Deliverables
- `outputs/round_1/notes/strategy_family_proposal.md`

## Acceptance criteria
- one simple viable family per product
- plain-English rationale
- clear risks/failure modes
- no final merged bot yet

---

# Phase 3 — Minimum viable round-1 implementation

## Goal
Implement the simplest credible strategy versions inside the existing architecture.

## Rules
- keep changes modular
- use existing engine structure
- avoid hardcoding extreme assumptions unless the dossier strongly justifies them
- preserve fallback behavior
- do not jump to final parameter tuning

## Expected implementation structure
- round-1 product strategy modules if needed
- round-1 runner scripts
- small config additions for round-1 products
- no unnecessary architecture churn

## Deliverables
- working minimum viable round-1 strategy implementation
- short note describing what was implemented and why

## Acceptance criteria
- code builds
- tests pass
- local backtest path runs
- no final promotion decisions yet

---

# Phase 4 — Staged parameter sweeps

## Goal
Explore parameters in a disciplined way without giant brute-force grids.

## General rule
Use staged sweeps, not huge grids.

## 4A. For stable-anchor / maker-first products
Likely applies to ASH_COATED_OSMIUM if Phase 1 confirms.

### Stage A — quote competitiveness
Sweep only:
- maker edge / quote width
- taker threshold

Hold:
- skew
- flatten threshold
- quote size
fixed initially

Rank by:
- PnL
- entry edge / markouts
- trade count
- inventory sanity

### Stage B — inventory refinement
Only on shortlisted Stage A configs, sweep:
- inventory skew
- flatten threshold
- maybe quote size

Do not start here.

## 4B. For trend-fair / local-reversion products
Likely applies to INTARIAN_PEPPER_ROOT if Phase 1 confirms.

### Stage A — fair-value family
Test a small number of fair models:
- linear trend-fair with online base estimate
- maybe a slightly adaptive trend-fair variant
- a simpler rolling/mid fallback baseline

### Stage B — threshold frontier
For the best fair-value family, sweep:
- buy threshold
- sell threshold
- asymmetry between buy and sell
- maker edge if relevant
- taker edge if relevant

### Stage C — inventory refinement
Only after signal quality looks real:
- skew
- flatten threshold
- quote size

## Metrics to record for every tested config
- total PnL
- per-product PnL
- trade count
- maker/taker split
- entry edge
- markouts (+1 / +5 / +20)
- final position
- time near limits
- max drawdown if practical

## Deliverables
- sweep tables
- shortlisted candidates
- notes on which parameters mattered and which did not

## Acceptance criteria
- parameter effects are interpretable
- no meaningless sweeps
- shortlist per product exists

---

# Phase 5 — Review packs and timestamp inspection

## Goal
Validate that the best local candidates are winning for sensible reasons.

## For top candidates, generate review packs showing:
- price vs fair
- trades on chart
- position path
- cumulative PnL
- suspicious timestamps
- concentration of PnL by slice
- whether edge is steady or clustered
- whether inventory is being managed sensibly

## Key review questions
- is the strategy winning because the fair is actually right?
- or because the simulator is gifting certain fills?
- are gains concentrated in one time segment?
- is the strategy too aggressive?
- is recovery suppressing good business too early?
- is one side much better than the other?

## Deliverables
- review packs for each shortlisted candidate
- interpretation notes

## Acceptance criteria
- candidates are evaluated visually and mechanically
- weak/noisy candidates are filtered out
- surviving shortlist is small and explainable

---

# Phase 6 — Official-upload shortlist

## Goal
Prepare a very small official-upload shortlist.

## Required shortlist types
- one clean promoted candidate
- one higher-upside alternate
- optionally one baseline/control

## Important
Do not choose based on local PnL alone.

Use:
1. local PnL
2. markout quality
3. inventory behavior
4. cross-slice robustness
5. simplicity / explainability
6. whether the edge depends heavily on generous local fill assumptions

## Deliverables
- `docs/round_1/upload_plan.md`
- shortlist rationale note

## Acceptance criteria
- shortlist is explicit
- upload order is explicit
- reasons are documented

---

# Phase 7 — Official IMC testing plan

## Goal
Move to IMC upload with a clear comparison framework.

## Upload order
Recommended:
1. baseline/control
2. promoted clean candidate
3. higher-upside alternate

## What to record from IMC
- final official PnL
- per-product PnL if inferable from logs
- cumulative PnL curve shape
- trade count if available
- final position / exposure clues
- obvious instability
- whether ranking is consistent with local research

## Interpretation rule
If local and IMC disagree:
- trust IMC
- use local tools only to explain and improve the next candidate

---

# Phase 8 — Round-1 final memo

## Goal
Produce a final round-1 research memo summarizing everything learned.

## Include:

### A. Product-by-product conclusions
What each asset appears to be and why.

### B. Fair-value conclusions
What fair-value family seems strongest for each product.

### C. Bot behavior inference
Best-effort microstructure interpretation.

### D. Best current strategy per product
With rationale and risks.

### E. Official-upload shortlist
Who gets uploaded and why.

### F. What remains uncertain
State clearly.

## Deliverable
- `docs/round_1/round1_research_memo.md`

---

## Commit hygiene

Use small logical commits.

Suggested commit grouping:
1. setup + folder structure
2. product dossier scripts and outputs
3. strategy-family memo
4. minimum viable implementation
5. staged sweep scripts/results
6. review-pack notes
7. official upload plan

Do not commit bulky generated artifacts unless they are lightweight markdown summaries.
Keep:
- notes
- manifests
- summaries
- shortlist files

Avoid committing:
- huge binary outputs
- bulky chart directories unless essential

---

## What not to do

Do not:
- create a separate repo
- duplicate the engine
- trust one fitted line blindly
- trust one backtest number blindly
- use Monte Carlo as final ranking authority
- let beautiful theory override the actual simulator edge
- promote a final bot without review and official comparison

---

## Final operational note

Claude Code should work in this order:

1. analyst
2. strategy designer
3. implementer
4. sweeper
5. reviewer
6. uploader-preparer

Not the reverse.

The main objective is not find a fancy strategy.
The main objective is:

identify the dominant edge the simulator is paying for, implement it simply, test it carefully, and validate it on IMC.
