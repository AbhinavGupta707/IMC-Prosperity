# P4-R2 Invest & Expand — Final Decision Memo (v3)

**Updated 2026-04-19 evening** after critical review challenged v2's
Discord-heavy weighting and v=0 conflation. Supersedes v1 and v2.

## TL;DR

**Primary (narrow winner): `(r=17, s=50, v=33)`** — E[PnL] 187 575
under v3 weights. **But the plateau is FLAT** — v=33..41 picks are
within 1.5k of each other. Essentially a tie.

**Downside-protection pick: `(r=13, s=37, v=50)`** — E[PnL] 182 031
(5k below winner) but worst-case floor is **+99k vs -6k**. The
asymmetric protection may justify switching.

**Decision is now uncertain by design**: active-submitters-only
prior correction reveals we don't know whether the true field mean
sits at v=33 (Schelling anchors) or v=40-50 (middle cluster + half
heuristic).

## What changed between v2 and v3

User flagged two errors in v2:

1. **Discord is reference, not truth.** 42-voter self-selected
   sample with known lying/trolling (people post "100 to grief 0-bidders"
   as strategy, not commitment). v2 weighted Discord family at 55%.
   v3 cuts this to **25%**.
2. **v=0 conflation.** The R1 "73% got 0" statistic refers to
   non-submitters — and **non-submitters are excluded from R2's
   speed rank pool**. Discord's 17% at v=0 is likely inflated by
   poll voters who mean "I won't submit" but voted "0".

v3 additions:
- New prior `active_submitters_only_blend` (3 variants) at **40%**
  cumulative weight — primary belief.
- Discord family at **25%**.
- Conceded: API probing yields zero R2 signal (R1 was a different
  game; R2 endpoint is 401-sealed).

## Top 15 weighted E[PnL] — plateau is flat

| Pick | E[PnL] | Worst | Gap from winner |
|---|---:|---:|---:|
| **(17, 50, 33)** | 187 575 | -6 160 | — |
| (15, 44, 41) | 186 954 | -12 993 | 621 |
| (15, 45, 40) | 186 873 | -12 152 | 702 |
| (16, 49, 35) | 186 353 | -7 887 | 1 222 |
| (16, 48, 36) | 185 653 | -8 746 | 1 922 |
| (15, 43, 42) | 185 270 | -13 834 | 2 305 |
| (16, 47, 37) | 184 780 | -9 606 | 2 795 |
| (16, 50, 34) | 184 132 | -7 027 | 3 443 |
| (16, 46, 38) | 183 736 | -10 465 | 3 839 |
| (15, 42, 43) | 183 413 | -14 675 | 4 162 |
| (15, 46, 39) | 182 601 | -11 311 | 4 974 |
| **(13, 37, 50)** | 182 031 | **+99 277** | 5 544 |
| (14, 42, 44) | 181 511 | -15 497 | 6 064 |

Rows 1–11 within 6k of each other — near-arbitrary ranking.
Row 12 `(13, 37, 50)` has the **only double-digit-positive
worst-case in the top 15**.

## Per-prior best response (with active_submitters added)

| Prior | BR | μ | PnL |
|---|---|---:|---:|
| discord_poll_raw | (18, 58, 24) | 0.46 | 188 305 |
| discord_blend_35pct_engage | (17, 50, 33) | 0.57 | 200 792 |
| **active_submitters_base** | **(13, 37, 50)** | **0.75** | **171 680** |
| **active_submitters_mid_heavy** | **(13, 37, 50)** | **0.77** | **178 789** |
| active_submitters_low_heavy | (16, 47, 37) | 0.61 | 196 446 |
| rjav1_blend_ensemble | (15, 45, 40) | 0.75 | 234 137 |
| maf_cluster_v5_heavy | (22, 70, 8) | 0.55 | 316 656 |
| maf_cluster_v27_meme | (17, 50, 33) | 0.62 | 221 980 |
| all_thirds_schelling | (17, 50, 33) | 0.90 | 344 558 |
| all_half_schelling | (13, 37, 50) | 0.90 | 216 586 |

**Critical signal**: 2 of 3 `active_submitters_*` priors pick
**v=50** as best response. The only variant that picks v=37 is
`low_heavy` (heavy MAF-weighted), which we weight only 6%.

## VoI for committed = (17, 50, 33)

E[VoI] = 28 761 XIREC (15% of E[PnL]) — higher than v2 (22k) because
active_submitters priors have distant alternative BRs.

Biggest VoI contributors:
- `active_submitters_mid_heavy` (w=14.7%) → switch to (13, 37, 50)
  for +41k, weighted VoI +6.1k
- `active_submitters_base` (w=21.1%) → switch to (13, 37, 50)
  for +24k, weighted VoI +5.1k
- `all_coast` (w=3.2%) → switch to (23, 77, 0) for +273k,
  weighted VoI +8.7k (tail scenario)
- `all_half_schelling` (w=2.1%) → switch to (13, 37, 50) for +223k,
  weighted VoI +4.7k

**The VoI is concentrated in priors that select v=50.** If we had
any empirical signal pointing at the active_submitters shape, we
should switch to v=50.

## Recommendation — honest tiered

**Judgment call between two tiers. Both defensible.**

### Tier 1A — Expected-value maximiser (narrow)
**`(r=17, s=50, v=33)`**
- Marginal E[PnL] leader (+600 over tier 1B)
- Downside -6k; not catastrophic but no floor
- Wins under Schelling-anchor priors (Discord blends + thirds)

### Tier 1B — Downside-protection, near-equal E[PnL]
**`(r=13, s=37, v=50)`**
- Only 5k below 1A on E[PnL]
- **Worst-case +99k** — the ONLY top-15 pick with positive floor
- Wins under 2 of 3 active_submitters priors (40% of weight)
- Matches rjav1/foodio's published pick from a different analysis

### Tier 2 — Middle compromise
**`(r=15, s=45, v=40)`**
- 700 below 1A on E[PnL]
- Middle of the road — neither best expected nor best floor

### ❌ Do NOT submit
- `(23, 77, 0)` — dominated on every realistic prior
- `(22, 73, 5)` — MAF-fragility trap (130k weighted mean)
- `v > 60` — wasted budget on rank already won

## The single-question decision

**If I had to pick one submission right now, I would submit
Tier 1B: `(r=13, s=37, v=50)`.**

Reasoning:
- E[PnL] give-up vs 1A is 1.6% (5k). Negligible.
- Downside floor is +99k vs -6k. +105k better in worst case.
- Active-submitters family (40% of my belief) picks v=50.
- Risk-adjusted, 1B dominates 1A unless you care only about
  expected value and zero about variance.

Swap to 1A if you have strong personal belief that field will
cluster at v=33 (Discord "speed=27" + naive-thirds spillover).

## Subjective weights used (v3, 2026-04-19 evening)

```
# Discord family (reference, not truth): 25%
discord_poll_raw                 0.02
discord_poll_mild_discount       0.05
discord_poll_heavy_discount      0.03
discord_blend_35pct_engage       0.08
discord_blend_50pct_engage       0.04
discord_blend_20pct_engage       0.03

# Active-submitters family (primary): 40%
active_submitters_base           0.20
active_submitters_mid_heavy      0.14
active_submitters_low_heavy      0.06

# Legacy ensemble: 10%
rjav1_blend_ensemble             0.10

# Focal-cluster / MAF: 9%
maf_cluster_v5_heavy             0.04
maf_cluster_v27_meme             0.05

# Edge / Schelling: 11%
all_thirds_schelling             0.03
all_half_schelling               0.02
all_coast                        0.03
uniform_flat                     0.03
```

Re-run with different weights to sensitivity-test:
```bash
cd ../IMC-manual && PYTHONPATH=. python -m src.scripts.run_manual_invest_expand_final
```

## What we CANNOT learn (conceded)

- **Live R2 distribution** — sealed until 2026-04-20 10:00 UTC
- **Other teams' picks** — all endpoints team-scoped
- **R1 leaderboard** — was auctions, not rank allocation (zero transfer)
- **Discord** — reference only; manipulation, trolling, small sample
  preclude high-confidence inference

## Files on branch `round2-manual-challenge` (worktree: `../IMC-manual`)

```
src/manual_rounds/
  invest_expand.py                     core math
  invest_expand_priors.py              18 priors incl. active_submitters
  invest_expand_equilibrium.py         QRE + regret table
  invest_expand_deep.py                MC, level-k, adversarial, phase
  invest_expand_decision.py            weighted meta-regret + VoI
src/scripts/
  run_manual_invest_expand.py          base runner
  run_manual_invest_expand_sensitivity.py
  run_manual_invest_expand_deep.py
  run_manual_invest_expand_final.py    v3 runner (source of this memo)
tests/test_manual_invest_expand.py     52 tests, all passing
docs/manual_round_2/
  HANDOFF_CONTEXT.md                   original session brief
  DECISION_MEMO.md                     this file
  API_PROBING_NOTES.md                 API sealed; scope notes
```
