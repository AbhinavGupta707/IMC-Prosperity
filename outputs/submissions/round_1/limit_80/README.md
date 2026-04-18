# Round-1 submission bundles — position_limit = 80

Fresh exports of all six Round-1 candidates at IMC's confirmed
per-product limit of **80**. Produced after the
`src/core/config.py` → `default_engine_config()` change from 50 → 80
(commit above the one recorded below).

- **Scope**: limit only. No retuning of `inventory_skew`,
  `flatten_threshold`, `taker_edge`, or any other knob. See
  `outputs/round_1/limit_80/analysis.md` for the pre-change review
  and the explicit list of things we did NOT touch.
- **Old bundles preserved**: the limit=50 bundles in
  `outputs/submissions/round_1/*.py` (one directory up) are
  unchanged. Their SHAs are the authoritative identifiers for what
  was previously uploaded to IMC and produced the recorded Baseline
  (+2 276) / Promoted (+2 518) / Alt (+3 040) / H1 (+2 780) PnL.
- **Test suite**: 458 passed at the change commit.

## Fingerprints

All bundles: datamodel mode = `platform`; banner commit = `7bc6241`.

| Variant | File | Size (bytes) | SHA256 |
|---|---|---:|---|
| baseline | `trader_round1_baseline.py` | 97 060 | `787ac08e8b318d8e8f1b8747a0332661eda37c0af959f03056751a24af71511e` |
| promoted | `trader_round1_promoted.py` | 97 125 | `05238cbfb2c65166f2b1a4f8c59cdd5fab4667d2da5c4976f8c3729265855717` |
| alt      | `trader_round1_alt.py`      | 97 120 | `286804eb9bd1c120fe2ed481ae3a5e8a718ca6320fa85a3966ceabef463a7e06` |
| h1       | `trader_round1_h1.py`       | 97 211 | `bc1be5c8b588029904af19794adb2acf0417e1827d934e2eca3b8c7f2ba198d4` |
| f5       | `trader_round1_f5.py`       | 97 277 | `3b1c485b9b2333d362ecaa3448bfdf0640e15583a45d0ae54131be04f3bc5eee` |
| test     | `trader_round1_test.py`     | 97 201 | `fa1ba4e6576d699db3ab6f17779b6de91a6b8fc0929b3a3c2469dd1ca5a4a3bf` |
| **v2_clean** | `trader_round1_v2_clean.py` | **90 056** | `c59781ec1fcd0b52a1a2f0ea30bee00a6307c271edcd794919a541b7a6e6f5e4` |
| **v3_nearhold** | `trader_round1_v3_nearhold.py` | **90 946** | `73fc0f8e8dbeac7cf3295b860fefb92d2e4a5c7aaecca6ef50f8b004138d695b` |

Every bundle validates with
`src/scripts/validate_submission`: the six pre-V2_clean bundles
each emit the usual `size_approaching_limit` warning (they sit at
~97 KiB under the retuned 96 KiB soft cap); V2_clean passes with 0
errors and 0 warnings at 90 KiB. Validator caps are now tuned to the
real IMC upload limit: soft 96 KiB, hard 100 KiB. The six
pre-V2_clean bundles are unchanged (same SHAs).

The V2_clean and V3_nearhold bundles are produced by separate
export pipelines (`src/scripts/round_1/export_round1_v2_clean.py`
and `export_round1_v3_nearhold.py`) because they inline the
research-only `src/strategies/pepper_core_long.py` and extend both
`KNOWN_STRATEGY_NAMES` and `STRATEGY_REGISTRY` at the bundle tail.
The export script minifies the assembled bundle (strips docstrings
and comment-only lines) before writing so it fits under IMC's 100
KiB upload cap; strategy logic is untouched. See the `.meta.md`
files next to each bundle for full composition, size history, and
runtime smoke-test records.

## Comparison with limit=50 bundles

| Variant | limit=50 SHA | limit=80 SHA |
|---|---|---|
| baseline | `b33913594f…` | `787ac08e8b…` |
| promoted | `d7ed897953…` | `05238cbfb2…` |
| alt      | `18d8088dd2…` | `286804eb9b…` |
| h1       | `47217a37f7…` | `bc1be5c8b5…` |
| f5       | `cdef85dd97…` | `3b1c485b9b…` |
| test     | `41d1c29a49…` | `fa1ba4e657…` |

Every SHA changed (as expected — the embedded `position_limit: 50`
vs `position_limit: 80` byte differs in each bundle, and the trim
of factory docstrings made prior to the test bundle export also
affected all later re-exports).

## What's embedded per variant

| Variant | ASH leg | PEPPER leg | Strategy on PEPPER |
|---|---|---|---|
| baseline | `wall_mid` / t=1.0 / m=1.0 / skew=4.0 / flat=0.7 / h=48 | `linear_drift` h=48 / t=1.0 / m=1.5 / skew=2.0 / flat=0.8 | market_making |
| promoted | `ewma_mid` / t=0.25 / m=1.0 / skew=4.0 / flat=0.7 / h=48 | `linear_drift` h=32 / t=2.0 / m=1.0 / skew=2.0 / flat=0.7 | market_making |
| alt      | `wall_mid` / t=0.5 / m=1.5 / skew=4.0 / flat=0.7 / h=48 | `linear_drift` h=32 / t=2.0 / m=1.0 / skew=1.0 / flat=0.9 | market_making |
| h1       | `wall_mid` / t=0.5 / m=1.5 / skew=4.0 / flat=0.7 / h=48 (= alt) | `linear_drift` h=32 / t=2.0 / m=1.0 / skew=2.0 / flat=0.7 (= promoted) | market_making |
| f5       | `wall_mid` / t=0.5 / m=1.5 / skew=4.0 / flat=0.7 / h=48 (= h1) | `linear_drift` h=32 / t=2.0 / m=1.0 / skew=2.0 / flat=0.7 (= promoted) + **taker_edge_buy=1.5, taker_edge_sell=3.0** | market_making |
| test     | `wall_mid` / t=0.5 / m=1.5 / skew=4.0 / flat=0.7 / h=48 (= h1) | `mid` (unused) — **buy-and-hold**, max_aggressive_size=80 | **buy_and_hold** |

`position_limit = 80` on both products for every variant above.

### Flatten trigger (absolute position) per variant at limit=80

| Variant | flatten_threshold | Recovery trigger (units) |
|---|---:|---:|
| baseline | 0.8 | ±64 |
| promoted | 0.7 | ±56 |
| h1 | 0.7 | ±56 |
| f5 | 0.7 | ±56 |
| alt | 0.9 | ±72 |
| test | n/a (never flattens — just holds +80) | n/a |

At limit=50, Alt's 0.9 triggered at ±45 and spent 22/250 official
snapshots near-limit (threshold ±37.5). At limit=80 Alt can now
ride to ±72 — an extra 27 units of long capacity on the drift day.
This is the single biggest behaviour change across all variants.

## Reproducing

```bash
# From repo root.
for v in baseline promoted alt h1 f5 test; do
  PYTHONPATH=. .venv/bin/python -m src.scripts.round_1.export_round1_submission \
    --variant $v --out-dir outputs/submissions/round_1/limit_80
done
# V2_clean and V3_nearhold use their own export pipelines
# (each inlines the research-only pepper_core_long strategy):
PYTHONPATH=. .venv/bin/python -m src.scripts.round_1.export_round1_v2_clean
PYTHONPATH=. .venv/bin/python -m src.scripts.round_1.export_round1_v3_nearhold
shasum -a 256 outputs/submissions/round_1/limit_80/*.py
```

SHA256s are deterministic **at the recorded commit**; the banner
embeds the commit hash, so re-exports at later commits differ in
the banner bytes.

## Recommended upload order (unchanged from limit=50 planning)

`docs/round_1/upload_plan.md` has the full rationale. The change
here is the WHICH FILE to upload: pull from
`outputs/submissions/round_1/limit_80/` for all future uploads.

The limit=50 bundles in the parent directory are kept as historical
references matching the already-recorded official PnLs
(`outputs/round_1/official_results/`).

## Known un-answered questions

See `outputs/round_1/limit_80/analysis.md` §9 for the full list.
Highlights:

1. The relative ranking between variants is a **limit=50** result.
   Nothing in this pass reran the fastsearch. F5's lead over H1
   may shrink or grow; Alt's lead over everything else almost
   certainly grows on a drift day.
2. Near-limit counts are no longer comparable across the change.
3. Alt's tail-risk on a reversing day scales with its new peak
   capacity (~±72 instead of ±45).
