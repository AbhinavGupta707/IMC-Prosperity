# P4-R2 Invest & Expand — Post-mortem and Lessons Learned

Dated 2026-04-20 (round-close day). Revised after full field-CDF
reconstruction from 6 post-round screenshots. Supersedes earlier draft
that misidentified the top pick.

## Outcome

**Our submission**: `(r=13, s=37, v=50)` → R2 manual PnL = 194,779
**Top 3 teams' submission**: reconstructed as **`(r=15, s=43, v=42)`**
(abacus / market maxxer / Open for Quant Jobs tied at 217,869)
**Our gap to top**: ~23,210 XIRECs (~11% of top PnL)
**Verified field size**: N = 4,304 submitters (consistent across 6
independent screenshots)

**Initial reconstruction error**: my earlier post-mortem claimed the top
pick was (14, 40, 46) — structurally feasible but empirically wrong. The
actual μ at v=46 was ~0.784, not the 0.815 needed for (14, 40, 46) to
achieve the top score. The real top was at v=42.

## Reconstructed field CDF (verified from 6 data points)

| v | Rank | CDF(v) | μ(v) = 0.1 + 0.8·CDF |
|---:|---:|---:|---:|
| 36 | 1,573 | 0.635 | 0.608 |
| 37 | 1,455 | 0.662 | 0.630 |
| 41 | 977 | 0.773 | 0.718 |
| **42** | **858** | **0.801** | **0.741** (top teams!) |
| 50 | 397 | 0.908 | 0.826 (our pick) |
| 52 | 279 | 0.935 | 0.848 |

All derive consistent N = 4,304 ± 1, confirming robust reconstruction.

## Field density structure

| v range | # teams | density per integer | role |
|---|---:|---:|---|
| v ≤ 36 | 2,731 (63.5%) | ~74 avg (concentrated low) | naive majority |
| v = 37 | 118 (2.7%) | 118 | smart-band start |
| v = 38–41 | 478 (11.1%) | **~120** | **smart-band core** |
| v = 42 | 119 (2.8%) | **119** | **smart-band top** (the cluster) |
| v = 43–50 | 461 (10.7%) | ~58 | post-cluster taper |
| v = 51–52 | 118 (2.7%) | ~59 | mid-tail |
| v ≥ 53 | 278 (6.5%) | ~6 | extreme tail (much smaller than Discord poll claimed) |

**The cluster was a BAND at v=37-42 with ~120 teams/integer**, twice
the density of v=43-50. v=42 was the TOP EDGE of this band.

## Optimal PnL ranking by v (using actual field CDF)

FOC-optimal (r, s) at each v, real μ from CDF:

| v | (r, s) | Net PnL | Δ vs max | Relative rank |
|---:|---|---:|---:|---:|
| **42** | **(15, 43)** | **217,989** | **0** | **OPTIMAL** |
| 41 | (15, 44) | 215,709 | −2,280 | 2nd |
| 43 | (14, 43) | 215,280 | −2,709 | 3rd |
| 40 | (15, 45) | 213,421 | −4,568 | 4th |
| 44 | (14, 42) | 212,907 | −5,082 | 5th |
| 39 | (15, 46) | 210,763 | −7,226 | 6th |
| 45 | (14, 41) | 210,351 | −7,638 | 7th |
| 38 | (16, 46) | 207,768 | −10,221 | 8th |
| 46 | (14, 40) | 207,616 | −10,373 | 9th (Analysis 1) |
| 47 | (14, 39) | 204,379 | −13,610 | 10th |
| 37 | (16, 47) | 204,486 | −13,503 | 11th |
| 48 | (13, 39) | 201,322 | −16,667 | 12th |
| 36 | (16, 48) | 200,825 | −17,164 | 13th |
| 49 | (13, 38) | 198,224 | −19,765 | 14th |
| **50** | **(13, 37)** | **194,657** | **−23,332** | **15th (us)** |
| 51 | (13, 36) | 191,513 | −26,476 | 16th |
| 52 | (13, 35) | 187,606 | −30,383 | 17th |

**The optimal v was 42 — smack in the middle of where we DIDN'T look.**

## Cost decomposition (v=42 vs v=50)

| Component | Top (v=42) | Us (v=50) | Delta |
|---|---:|---:|---:|
| R×S | 361,658 | 296,195 | **−65,463** |
| μ | 0.7407 | 0.8264 | +0.086 |
| Gross | 267,862 | 244,717 | −23,145 |
| Net PnL | **217,862** | **194,717** | **−23,145** |

We gave up ~65k of R×S for 0.086 of μ. At gross-relevant scales, the
R×S loss (~55k equivalent PnL) massively exceeded the μ gain (~25k PnL).

## Root-cause analysis — what went wrong

### 1. Mis-located the smart cluster (biggest error)
- Believed AI cluster at v=44-46 (based on 3 of 4 external analyses)
- Reality: cluster at v=37-42, peak at v=42
- Mean of our 4 AI samples (30, 44, 44, 46) = 41, median = 44
- Real peak was closer to the MEAN than median, and 2 points BELOW it

### 2. AI-upward-bias unrecognised
- AIs reason about "what smart teams would do" — over-models elite
- Most AIs internalize "overshoot the consensus" — double-counts at scale
- AIs under-sample naive mass (63% of real field bid v≤36)
- Result: AI-consensus is systematically higher than actual field mode

### 3. Over-weighted speculative hedge priors
- We gave the hand-built `active_submitters_only_blend` 40% weight
- That prior assumed 12% at v=50 (halve-it Schelling) and spread
  sophisticated teams across v=36-50
- Reality: v=50 had only ~2% of field; cluster was tight at v=37-42

### 4. Missed the μ-ceiling sanity check
- At v=50 with (13, 37), reaching 217,870 required μ=0.905 > 0.9
- This was an instant "you cannot win with this pick" signal
- Would have forced us one or more cluster levels lower

### 5. "Overshoot the consensus" logic failed
- Assumed the AI cluster would trigger meta-overshoot cascade
- Reality: the AI consensus WAS the local equilibrium, slightly biased high
- The bigger error was picking ABOVE even the AI consensus (v=50 > AI mean 42.8)

## What analyses were closest (ranked by actual R2 PnL)

| Analysis | Pick | Would-have PnL | Rank among v choices |
|---|---|---:|---:|
| A2 (v=44) | (14, 42, 44) | 212,907 | 5th |
| A4 (v=44) | (14, 42, 44) | 212,907 | 5th |
| A1 (v=46) | (14, 40, 46) | 207,616 | 9th |
| Our pick (v=50) | (13, 37, 50) | 194,657 | 15th |
| A3 (v=30) | (17, 53, 30) | ~165,000 | ~22nd |

Analyses 2 and 4 (v=44) were the CLOSEST to optimal (2 points off).
Analysis 1's minimax-regret approach (v=46) was 4 points off. Our meta-game
overshoot (v=50) was 8 points off. Analysis 3 (v=30) was 12 points off.

**The AI consensus MEAN of {30, 44, 44, 46, 50} is 42.8 — almost
exactly optimal.** Had we picked v=43 (rounded from 42.8), we'd have
netted 215,280 — within 3k of top.

## Key realizations

### R1 — The REAL consensus was the MEAN of AI outputs, not the median
- 4 external AIs + us: 30, 44, 44, 46, 50
- Median: 44 (overshoots by 2)
- Mean: 42.8 (almost exact)
- Even: 42 (spot on)

Cultural possibility: "42" as a Hitchhiker's Guide meme may have added
a specific Schelling spike exactly at that integer.

### R2 — Field density structure matches "bimodal" prediction
- 63.5% naive (low v) + 16.6% smart band (v=37-42) + 20% tail
- Similar to our `active_submitters_only_blend` model SHAPE
- But we had the smart-band LOCATION wrong (modelled v=36-50 uniform,
  actual was v=37-42 concentrated)

### R3 — The v=50 Schelling (halve-it) cluster was weaker than modelled
- We assumed 12% at v=50 spike
- Actual: ~2% of field at v=50, mostly spread into v=43-50 taper
- Halve-it heuristic doesn't create a hard spike at exactly 50 — it
  creates a slow taper above v=42

## Transferable lessons (for CLAUDE.md memory)

See `/CLAUDE.md` in this project for the codified memory. Highlights:

**Mechanical (always true)**:
- μ-ceiling sanity check
- R×S dominates μ at the top
- Tie-share-best creates gravitational wells
- Multiple (r, s, v) produce same PnL — enumerate when reconstructing

**Field-estimation (empirically calibrated for P4)**:
- AI consensus has 2-4 point upward bias vs real field peak
- Aggregate AI outputs: use MEAN or LOW END, not median/high
- Fields are bimodal: ~60% naive + ~20% smart band + ~20% tail
- Density band > point cluster — target TOP of density band
- Community polls ≤ 15% weight (self-selection, trolling, exaggeration)

**Process**:
- When sub-models disagree, regress DOWNWARD
- Neither Bayesian-weighted EV nor minimax-regret alone is enough
- Reconstruct before declaring — initial reconstructions often wrong

**Tooling**:
- Git worktrees for parallel branch work
- Framework survives calibration errors; rebuild priors per round

## What we should have submitted

**Given only the pre-round information available to us**, the best-
calibrated pick would have been:

`(r=15, s=44, v=41)` or `(r=15, s=43, v=42)` —
i.e., take the MEAN of the AI candidate outputs (42.8) and round to
the nearest integer. This would have netted 215-218k, putting us in
the top cluster.

**Even dropping from v=50 to v=44** (matching A2/A4) would have saved
~18k of our ~23k loss.

## Score outcome

- R2 manual: 194,779 (rank ~397 of 4,304)
- Combined (R1+R2): 282,774
- Qualified for Phase 2 (comfortably above typical 200k threshold)
- Left ~23k on the table — ~11% of achievable top PnL

## Framework status

- Solver code: **validated** (`src/manual_rounds/invest_expand*.py`)
- Unit tests: **52 passing**
- Reusable: **yes** — for future rank-based manual rounds, clone the
  framework and rebuild priors using F1-F5 adjustments from CLAUDE.md
- Calibration tooling:
  - Reconstruction from leaderboard screenshots → field CDF
  - Regret + Bayesian-weighted + VoI
  - MC validator (verified to 0.0003 μ accuracy)

The framework was correct. Calibration (specifically: which prior shape
to trust) was the single source of error, and it was ~8 integer-v
points off.
