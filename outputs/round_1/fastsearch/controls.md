# Phase A — Official control table

Compact reference for the four variants that have been tested in the
**official IMC environment**. All figures are lifted straight from the
official JSON / log files (no re-simulation). They are the ground truth
against which any new candidate must be judged.

- Sources:
  - `outputs/round_1/official_results/<variant>/<id>.json`
    (`activitiesLog.profit_and_loss` at bucket boundaries)
  - `outputs/round_1/official_results/analysis/bucket_breakdown.{md,csv}`
    (bucketed PnL, trade, and triggers)
  - `outputs/round_1/official_results/analysis/bucket_memo.md`
    (diagnosis)

| Variant   | Total PnL | ASH PnL | PEPPER PnL | PEP early 25k | PEP early 50k | PEP first-half share | End-of-b0 PEP pos | Near-limit PEP (snapshots of 1000) | Maker/Taker PEP |
|-----------|----------:|--------:|-----------:|--------------:|--------------:|---------------------:|------------------:|-----------------------------------:|-----------------|
| **Baseline**  | **+2 276.15** | +832.25 | **+1 443.90** | **−57.20** | +54.91  | **3.8 %** | **−8** | 0   | 20 mkr / 27 tkr |
| **Promoted**  | **+2 518.11** | +720.91 | +1 797.20 | +30.90 | +437.50 | 24.3 %   | +1 | 0   | 18 mkr / 24 tkr |
| **Alt**       | **+3 040.22** | +982.81 | +2 057.41 | +30.90 | +361.00 | 17.5 %   | +1 | **22** (b2 50-75k) | 19 mkr / 26 tkr |
| **H1 hybrid** | **+2 780.01** | +982.81* | +1 797.20* | (=Promoted) | (=Promoted) | (≈Promoted) | (=Promoted) | 0 | 18 mkr / 24 tkr |

\*H1 composition is mathematically additive: H1 = Alt ASH leg + Promoted
PEPPER leg. The two individual leg PnLs above are therefore the Alt-ASH
row and the Promoted-PEPPER row. H1 has not drifted on inventory or
near-limit behavior since it shares PEPPER identically with Promoted.
Source: `outputs/round_1/phase8_5/h1_bundle_metadata.md`.

## One-sentence diagnosis per variant

- **Baseline** — First-bucket PEPPER is the hole: `linear_drift
  history_length=48` + `taker_edge=1.0` fire **3 sell / 2 buy** triggers
  in 0-25k and leave the book **net short −8** into a continuously
  rising PEPPER. The bot bleeds to cumulative **−114 at t=40 000**
  before inventory flips long and the drift finally helps it. ASH is
  **not** the problem for Baseline — it clocks +832 in line with Alt.
- **Promoted** — `taker_edge=2.0` + `history_length=32` kills the
  spurious sell triggers in bucket 1 (2 / 2 symmetric), ends bucket 1
  at **+1** PEPPER, and picks up +407 in bucket 2 while Baseline is
  still unwinding. The cost is the **ASH** leg: `ewma_mid + taker=0.25`
  under-trades vs `wall_mid`, losing **−112 ASH** vs Baseline and
  **−262 ASH** vs Alt.
- **Alt** — Same PEPPER engine as Promoted plus the **wall_mid ASH**
  leg (`taker=0.5, maker=1.5`) and `flatten_threshold=0.9, skew=1.0`
  on PEPPER. Keeps the bucket-1 win AND the ASH PnL (+982.81) but
  spends **22 of 250 snapshots near the long limit** in bucket 2 — a
  real tail-risk flag on a single data point.
- **H1 hybrid** — Promoted's PEPPER + Alt's ASH. Solves the Promoted
  ASH under-trade (+262 ASH vs Promoted) **without** importing Alt's
  flatten=0.9 near-limit exposure. The residual gap **Alt − H1 =
  +260** is almost exactly Alt's extra PEPPER `flatten=0.9 / skew=1.0`
  upside from riding a bigger long into the drift.

## Where is the remaining money?

The four data points triangulate cleanly:

| Δ                          | Δ total | Attributable to        |
|----------------------------|--------:|-------------------------|
| Promoted − Baseline        | +242    | PEPPER bucket-1 fix (+353); ASH −112 |
| H1 − Promoted              | +262    | ASH leg swap: Alt wall_mid over Promoted ewma_mid |
| Alt − H1                   | +260    | Alt PEPPER's `flatten=0.9` extra MTM in bucket 50-75k |
| Alt − Baseline             | +764    | PEPPER first-half (+113) + PEPPER later (+500) + ASH (+151) |

The **wall-based ASH leg is locked in** (H1 captured it without
breaking PEPPER). The remaining missing money sits in **PEPPER on the
first half of the day** (Baseline's bucket-0 hole) and **PEPPER upside
in buckets 2-3** (Alt's `flatten=0.9` reach). The fastsearch plan
targets both, with a near-limit guard to avoid Alt's tail-risk cost.

## How this table is used downstream

- The **upper bound of interest** is Alt total = **+3 040** on this
  single day. A new candidate that beats Alt on PEPPER PnL WITHOUT
  inheriting the `>22 near-limit snapshots` cost is meaningfully
  better than any existing upload.
- The **unchanged leg** in every PEPPER trial is **Alt-style
  wall_mid ASH** (the H1 ASH leg). ASH search is capped at a
  side-check; see `ash_memo.md`.
- First-half PEPPER PnL is the **single most diagnostic slice** for
  ranking candidates, because every variant's bucket-2 PnL is
  dominated by market drift on inherited inventory — the real
  decision is whether the bot enters bucket-2 already long.
