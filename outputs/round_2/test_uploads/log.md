# Round-2 IMC test-upload log

This is the operator log for the IMC sandbox test phase. Goal: validate
the analytical claims behind the upload decision before the final scored
run. Methodology defined in batch-E review answer; bundles built by
`src/scripts/round_2/export_test_variants.py`.

**Important constraints to remember:**
- Test runs are **100k ticks (1k snapshots) — 10 % of the scored length**.
  Single-test PnLs are noisy; only multi-run means are interpretable.
- The IMC sandbox shows a **randomized 80 % subsample of quotes** per
  upload, so the same `.py` file will produce a different PnL on every
  upload. This is the noise floor we are estimating with the 3 repeated
  `round2_promoted` runs.
- **`bid()` is ignored during testing** — the MAF auction only runs on
  the final scored submission. Do not try to validate the bid value here.

## Bundles to upload

All four files live under
`outputs/submissions/round_2/test_variants/`. SHA256 fingerprints in
`MANIFEST.md` next to them.

| upload order | variant | file | runs needed |
|---:|---|---|---:|
| 1, 2, 3 | `round2_promoted` | `trader_round2_promoted.py` | 3 |
| 4 | `round2_L1_ash` | `trader_round2_L1_ash.py` | 1 |
| 5 | `round2_killswitches_on` | `trader_round2_killswitches_on.py` | 1 |
| 6 | `round1_v5micro_l1` | `trader_round1_v5micro_l1.py` | 1 |

Total: 6 uploads across 4 distinct bundles. ~1-2 hours elapsed time
(mostly waiting on the IMC scorer).

## Recording template

After each upload completes on the IMC platform, fill in this row.
Pull the per-product PnL from the IMC `activitiesLog` cumulative
`profit_and_loss` final value (the same field we used for the R1
official analysis).

| upload # | variant | uploaded at (UTC) | total PnL | ASH PnL | PEPPER PnL | trades (ASH/PEP) | final pos (ASH/PEP) | notes |
|---:|---|---|---:|---:|---:|---|---|---|
| 1 | `round2_promoted` | YYYY-MM-DD HH:MM | ? | ? | ? | ? / ? | ? / ? | first sample |
| 2 | `round2_promoted` | | ? | ? | ? | ? / ? | ? / ? | second sample (same file, different randomized quotes) |
| 3 | `round2_promoted` | | ? | ? | ? | ? / ? | ? / ? | third sample |
| 4 | `round2_L1_ash` | | ? | ? | ? | ? / ? | ? / ? | ablation: L1 ASH ladder |
| 5 | `round2_killswitches_on` | | ? | ? | ? | ? / ? | ? / ? | ablation: batch-B kill thresholds active |
| 6 | `round1_v5micro_l1` | | ? | ? | ? | ? / ? | ? / ? | R1 winner — simulator-consistency anchor |

## Pre-committed decision rules

These are written before any test results come in so the upload
decision is not retroactively rationalised.

### Scale check (uploads 1, 2, 3 — `round2_promoted` × 3)

Compute **mean ± standard error** across the three runs.

| outcome | implication | action |
|---|---|---|
| Mean ≈ +8 000 to +12 000 XIRECs | Local-vs-official compression matches R1 (~3×) | ✅ Ship `round2_promoted` with `bid=2300` |
| Mean materially below +5 000 | Compression is much worse than R1 — simulator change OR ASH regression | ⚠️ Investigate before final upload; do not ship blind |
| Mean above +15 000 | Compression is *better* than expected | ✅ Ship as planned; expect cumulative R2 PnL on the high side |
| σ across 3 runs > 50 % of mean | Noise floor too high for ablation conclusions to be reliable | Run 2 more `round2_promoted` samples before trusting uploads 4-5 |

### Ablation: wide_w113 vs L1 ASH (upload 4 vs uploads 1-3 mean)

| outcome | implication | action |
|---|---|---|
| `round2_L1_ash` < `round2_promoted` mean (by more than 1 σ) | Batch-D1 finding confirmed — wide_w113 is real | ✅ Keep wide_w113 in the upload |
| `round2_L1_ash` ≈ `round2_promoted` mean (within 1 σ) | wide_w113 advantage is below the noise floor on official | Keep wide_w113 (no harm), document as "marginal" |
| `round2_L1_ash` > `round2_promoted` mean (by more than 1 σ) | wide_w113 was an R2-tape overfit | ⚠️ **Switch to L1 ASH for the final upload**; rebuild bundle |

### Ablation: kill switches on vs off (upload 5 vs uploads 1-3 mean)

| outcome | implication | action |
|---|---|---|
| `round2_killswitches_on` ≈ `round2_promoted` mean (within 1 σ) | Batch-D2 finding confirmed — kills are redundant on this stack | ✅ Ship with kills disabled |
| `round2_killswitches_on` > `round2_promoted` mean (materially) | Kill switches DO help on the official fill model | ⚠️ **Enable batch-B kill thresholds for the final upload**; rebuild bundle |
| `round2_killswitches_on` materially below | Kills actively interfere on official too | ✅ Ship with kills disabled (D2 conclusion strengthened) |

### Sanity: R1 carry-over (upload 6)

Reference: R1 final scored `combined_v5micro_l1` = +89 970 over 1 day ×
10k snapshots. Test runs are 1 day × 1k snapshots = 10 % of scored
length, so the expected per-test scaled value is **~+9 000**.

| outcome | implication | action |
|---|---|---|
| `round1_v5micro_l1` ≈ +8 000 to +10 000 | R2 simulator behaves like R1 | ✅ All other findings are reliable |
| `round1_v5micro_l1` materially different | R2 simulator has microstructure changes | ⚠️ Re-evaluate the wide_w113 / kills conclusions; the local sweep may not transfer |

## Things NOT to do

- **Do NOT iterate on bid value via testing.** Bid is ignored. Lock the
  bid decision (`2 300` per batch D3) and do not spend test slots
  trying to validate it.
- **Do NOT keep testing after the decision rules trigger.** Once
  `round2_promoted` is validated within the expected band AND the
  ablations resolve, stop. Extra tests are cost without information.
- **Do NOT change the bundle parameters between uploads in a single
  variant** (e.g. don't tweak `round2_promoted` to a slightly different
  ASH ladder mid-stream). Each variant must be the SAME `.py` file
  across its repeat runs so noise estimation is meaningful.
- **Do NOT re-tune locally on a single official-test data point.** This
  was the explicit anti-pattern from R1 retro. One official test = one
  noisy sample.

## After the test phase

When all 6 uploads are recorded:

1. Fill in the table above completely.
2. Compute mean ± σ for `round2_promoted` and apply the decision rules.
3. If the rules say ship `round2_promoted` as planned: re-export with
   `--bid 2300`, validate, upload as the final scored submission.
4. If the rules say switch to L1 ASH or enable kills: rebuild the
   relevant variant (the test files are with `bid=0`, so we need a
   fresh export with the live bid value).
5. Update `outputs/submissions/round_2/README.md` provenance manifest
   with the chosen variant + decision audit trail.
