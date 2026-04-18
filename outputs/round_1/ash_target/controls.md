# Phase A — ASH control legs

Compact reference for the ASH legs already in the repo. These are the
**reference points** the ASH target-position family must beat.

Sources
- Official day (1 sample):
  `outputs/round_1/official_results/analysis/bucket_breakdown.{md,csv}`
- Local replay (3 × 10k steps):
  `outputs/round_1/sweeps/20260414T132740Z_round1_ash_stage_a_wall_mid/`
  and sibling stage-A sweeps for `ewma_mid` / `depth_mid`.
- Engine factories: `src/core/config.py`
  (`round1_baseline_engine_config`, `round1_promoted_engine_config`,
   `round1_alt_engine_config`, `round1_h1_engine_config`,
   `round1_f5_engine_config`).

## Engine summary (ASH leg only)

| Leg id       | Used in                                | FV           | maker_edge | taker_edge | inventory_skew | flatten | history |
|--------------|----------------------------------------|--------------|-----------:|-----------:|---------------:|--------:|--------:|
| C_baseline   | `round1_baseline_engine_config`        | `wall_mid`   | 1.0        | 1.0        | 4.0            | 0.7     | 48      |
| C_promoted   | `round1_promoted_engine_config`        | `ewma_mid`   | 1.0        | 0.25       | 4.0            | 0.7     | 48      |
| C_h1_alt     | `round1_alt_engine_config` & H1 & F5   | `wall_mid`   | 1.5        | 0.5        | 4.0            | 0.7     | 48      |

The F5 upload candidate uses the **same ASH leg as H1/Alt** — only the
PEPPER side differs.  There is therefore **one** wall-based ASH leg
shipped (`C_h1_alt`) and **one** ewma-based ASH leg shipped
(`C_promoted`).

## Official day (2026-04-14) ASH PnL and behavior

| Leg id       | ASH PnL | Bucket 0-25k | 25-50k | 50-75k | 75-100k | Trades | Maker / Taker / Other | Avg size | End pos (last bucket) | Near-limit snapshots | One-sentence diagnosis |
|--------------|--------:|-------------:|-------:|-------:|--------:|-------:|-----------------------|--------:|----------------------:|---------------------:|------------------------|
| C_baseline   | **+832.25** | +175.27 | +160.66 | +290.36 | +205.97 | 90 | 56 / 25 / 9 | 5.2 | −12 | 0 | Wall-based maker workhorse; taker 1.0 fires a bit more than necessary, markouts slightly noisier. |
| C_promoted   | **+720.91** | +159.50 | +171.41 | +310.30 | +79.69 | 81 | 56 / 16 / 9 | 5.0 | −25 | 0 | `ewma_mid` + taker=0.25 under-fires the maker in late bucket; ends short −25 and loses most of the bucket-3 PnL. |
| C_h1_alt     | **+982.81** | +219.66 | +194.25 | +340.92 | +227.98 | 90 | 56 / 25 / 9 | 5.3 | −14 | 0 | Same trade pattern as baseline, but `maker_edge=1.5` and `taker_edge=0.5` widen passive edge → **+150 / +262** vs baseline / promoted with identical trade count and zero near-limit. |

(Trades, maker/taker, and end pos are summed across the four 25k
buckets from `bucket_breakdown.md`; bucket PnL columns are the
per-bucket deltas.)

## Local 3-day replay PnL (sanity check)

Reference from `outputs/round_1/sweeps/20260414T132740Z_round1_ash_stage_a_wall_mid/summary.txt`,
baseline = `wall_mid maker=1.0 taker=1.0 skew=4 flatten=0.7 h=48` on
the 3-day replay. Local numbers are ~10× the official-cadence PnL.

| Leg id       | 3-day local ASH PnL | Trade count | Maker %  | Near-limit (of 30 000 steps) | Last-step pos |
|--------------|--------------------:|------------:|---------:|-----------------------------:|--------------:|
| C_baseline   | +7 301              | 650         | 0.2 %[^1]|                          100 |  −5           |
| C_promoted   | ≈ +6 200 (see note) | ≈ 640       | ~0.2 %   | ~80                          | mixed         |
| C_h1_alt     | **+7 747**          | 766         | 0.3 %    | 110                          | −9            |

[^1]: "Maker %" here is the per-cell maker count divided by 100 000 (ASH
is quoted each step regardless of whether it fills). It is *not* the
maker-vs-taker ratio; for that see the official-day row above, which
shows ~56 maker / ~25 taker fills per day for C_baseline and
C_h1_alt.

**Note on C_promoted 3-day local:** the phase-5 sweep grid did not
evaluate exactly the shipped promoted parameters (`ewma_mid` ×
`taker=0.25`) in the same summary. We read the same quantity from the
sibling `ewma_mid` stage-A sweep as `mean_pnl` near `taker_edge=0.25`;
it lands around **+6 200**. The relative ordering
(`C_h1_alt > C_baseline > C_promoted`) matches the official day, which
is what matters for ranking target-position candidates below.

## Implied "best-in-repo" ASH bar

Any target-position candidate in the next pass has to beat
**+982.81 official-cadence ASH PnL** (C_h1_alt) — or beat **C_promoted
+720.91** while also delivering a robustness story the wall-based leg
cannot. Bucket-3 (+227.98 for C_h1_alt vs +79.69 for C_promoted) is
the single biggest leverage point: a target that manages inventory
better than the +/− skew mechanism in late-day drift shows up there
first.
