# Official Site Upload Guide

## Your three submission files

| # | Variant | File | What it does |
|---|---------|------|--------------|
| 1 | Baseline | `outputs/submissions/trader_baseline.py` | Original config (weighted_mid FV) |
| 2 | C2 | `outputs/submissions/trader_c2_wall_mid.py` | Promoted config (wall_mid FV) |
| 3 | C3 | `outputs/submissions/trader_c3_rolling_mid.py` | Alternate config (rolling_mid, wider edges, shorter history) |

## Config differences

| Parameter | Baseline | C2 | C3 |
|-----------|----------|----|----|
| fair_value_method | weighted_mid | wall_mid | rolling_mid |
| taker_edge | 1.0 | 1.0 | 1.5 |
| maker_edge | 1.0 | 1.0 | 2.0 |
| history_length | 48 | 48 | 32 |
| Everything else | same | same | same |

C2 changes only the fair-value method. C3 changes four parameters.

## Upload order

### Step 1 — Upload baseline first

Upload `outputs/submissions/trader_baseline.py` to the official site.

This is the reference point. Record all results before uploading
anything else so you have a clean comparison.

### Step 2 — Upload C2 second

Upload `outputs/submissions/trader_c2_wall_mid.py`.

This is the promoted default. Compare its results against baseline.

### Step 3 — Upload C3 third

Upload `outputs/submissions/trader_c3_rolling_mid.py`.

This is the higher-risk alternate. Compare against both baseline and C2.

## What to record from the official site

For each submission, write down:

| Field | Where to find it |
|-------|------------------|
| Total PnL | Results page after the round runs |
| Per-product PnL | EMERALDS and TOMATOES separately if shown |
| Trade count | If visible in results or trade log |
| Final position | If reported |
| Any error messages | If the submission fails to run |

## How to compare results

### If C2 > baseline on PnL

The wall_mid promotion is validated. Keep C2 as the default.

### If C2 < baseline on PnL

The local replay fill model may differ from the official site.
Revert the promotion (change config.py back to weighted_mid)
and investigate why.

### If C3 > C2 on PnL

The rolling_mid aggressiveness is rewarded by the official fill
model. Consider promoting C3 in a future optimization pass, but
investigate markout quality first.

### If C3 < C2 on PnL

C2 is the right choice. The markout quality advantage translated
into official performance too.

### If results are very close

The advantage may be noise-level. If possible, run multiple times
and check whether the ranking is consistent.

## How to upload on the Prosperity site

1. Go to the Prosperity trading platform
2. Find the submission / algorithm upload area
3. Upload the `.py` file (the whole file, not a zip)
4. Wait for the round to complete
5. Check results

Each file is self-contained. You upload one file at a time. The
site runs it and shows you the results.

## Important notes

- Upload only ONE file at a time
- Wait for results before uploading the next
- EMERALDS is expected to produce zero or near-zero PnL for all
  three variants (under the current local replay, it produced zero
  fills — official results may differ)
- The main differences will show up in TOMATOES PnL
