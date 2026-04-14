# Round 1 — Phase 6 Official Upload Plan

This document is the **upload plan**: which files to submit to the
official IMC Prosperity site, in what order, and why. Phase 7
(in `docs/round_1/imc_testing_plan.md`) covers what to record from
the official run.

> **Official results landed.** The three variants ran and ranked
> Alt (+3 040) > Promoted (+2 518) > Baseline (+2 276) — order
> matches local. Full analysis:
> `docs/round_1/official_results_analysis.md`. Promoted still
> stands; the ASH leg is flagged for review.

## Three submission files

All three are bundled by
`src/scripts/round_1/export_round1_submission.py` from a single Round-1
config factory each, so the only differences between them are the
embedded `ProductConfig` fields.

| # | Variant | File | Source factory | Local 3-day PnL |
|---|---------|------|----------------|------------------|
| 1 | **Baseline / control** | `outputs/submissions/round_1/trader_round1_baseline.py` | `round1_baseline_engine_config()` | ~+24 k |
| 2 | **Promoted / robust default** | `outputs/submissions/round_1/trader_round1_promoted.py` | `round1_promoted_engine_config()` | ~+60 k |
| 3 | **Higher-upside alternate** | `outputs/submissions/round_1/trader_round1_alt.py` | `round1_alt_engine_config()` | ~+87 k |

Local PnLs are sums of the per-product Phase-5 review-pack PnLs
(ASH C2 + PEPPER C1b for promoted, ASH C1 + PEPPER C2 for alt; the
baseline figure is from the Phase-3 minimum-viable run).

## Embedded ProductConfigs

| Field | Baseline | Promoted | Alt |
|-------|----------|----------|-----|
| **ASH_COATED_OSMIUM** | | | |
| `fair_value_method` | wall_mid | **ewma_mid** | wall_mid |
| `taker_edge` | 1.0 | **0.25** | **0.5** |
| `maker_edge` | 1.0 | 1.0 | **1.5** |
| `inventory_skew` | 4.0 | 4.0 | 4.0 |
| `flatten_threshold` | 0.7 | 0.7 | 0.7 |
| `history_length` | 48 | 48 | 48 |
| **INTARIAN_PEPPER_ROOT** | | | |
| `fair_value_method` | linear_drift | linear_drift | linear_drift |
| `taker_edge` | 1.0 | **2.0** | **2.0** |
| `maker_edge` | 1.5 | **1.0** | **1.0** |
| `inventory_skew` | 2.0 | 2.0 | **1.0** |
| `flatten_threshold` | 0.8 | **0.7** | **0.9** |
| `history_length` | 48 | **32** | **32** |

`position_limit=50` and `quote_size`/`max_aggressive_size` are kept
constant across variants. `position_limit=50` is the Phase-1
**placeholder** — please confirm the official Round-1 limits and
re-export if they differ.

## Why these three (Phase-6 selection rationale)

The plan says do not select on local PnL alone; rank instead on
markout quality, inventory behaviour, cross-slice robustness,
simplicity, and fill-model dependence. The Phase-5 review-pack
diagnostics scored each candidate on every dimension (see
`outputs/round_1/notes/phase5_pack_stats.md`); the choices below
follow from that table.

1. **Baseline / control.** It is the Phase-3 minimum-viable Round-1
   config. We need a reference point that the promoted and alternate
   variants are measured against on the official site. Without it we
   cannot tell whether a PnL surprise is a config issue or a
   simulator-vs-exchange divergence.

2. **Promoted / robust default.** Pair of Phase-5 winners:
   - **ASH = C-ASH-A** (`ewma_mid`, `taker_edge=0.25`). Cross-day PnL
     variance ±28 (1.3 % of mean) vs C1's ±455. Best markouts at every
     horizon. Zero near-limit steps. Phase-5 verdict: cleanest
     production-ready default; less reliant on local taker fill model
     than the wall_mid alternative.
   - **PEPPER = C-PEP-A (a.k.a. C1b)** (`linear_drift` h=32,
     `taker_edge=2.0`, `flatten_threshold=0.7`). Identical signal
     quality to C1 (same edge, same markouts at every horizon, same
     autocorr) with **57 % less limit pinning** for only −4 % PnL.

3. **Higher-upside alternate.** Pair of higher-upside Phase-5
   candidates:
   - **ASH = C-ASH-B** (`wall_mid`, `taker_edge=0.5`). +20 % more
     local PnL than C-ASH-A but ~99.7 % taker fills, so more
     dependent on the local fill model.
   - **PEPPER = C-PEP-B** (`linear_drift` h=32, `inventory_skew=1.0`,
     `flatten_threshold=0.9`). +40 % more PnL than C-PEP-A on
     identical signal quality, purchased with 4× more near-limit
     exposure (24 % of steps at the long limit). Directional bet on
     drift persisting through the official run.

A potential C-PEP-C ultra-safe variant (`linear_drift` h=32,
`inventory_skew=4.0`, **0 near-limit**) was preserved in the Phase-5
shortlist but is **not** included in the upload set: with only three
slots, two leveraged variants + one baseline beats two leveraged
variants + one ultra-safe. C-PEP-C remains exportable on demand from
the existing factory machinery if the official run shows the
inventory tolerance is the binding constraint.

## Rank against the Phase-6 selection criteria

| Criterion | Baseline | Promoted | Alt |
|-----------|----------|----------|-----|
| Local PnL | +24 k | +60 k | +87 k |
| Markout quality (h=5) | ~+1.95 / +3.50 | ~+1.94 / +3.56 | ~+1.79 / +3.53 |
| Inventory health (near-limit %) | ASH 0.4 % / PEPPER 16 % | ASH 0 % / PEPPER 2.5 % | ASH 0.4 % / PEPPER 24 % |
| Cross-day PnL variance (ASH / PEPPER σ) | 455 / 1 800 | **28** / 1 857 | 455 / 4 400 |
| Simplicity / explainability | Same as Phase-3 | One FV swap on each product | Same FV families as baseline, edge / inventory tuned |
| Local fill-model dependence | Moderate | **Lowest** (ewma_mid markouts hold without aggressive taker) | Highest (taker-heavier ASH; pinned-long PEPPER) |

The promoted variant is the only one where every robustness column
is at least tied for best. The alt trades robustness for upside on
PEPPER specifically; the baseline anchors comparison.

## Upload order

1. **Baseline first.** Establishes the reference. Do not upload
   anything else until the baseline run is complete and PnL is
   recorded.
2. **Promoted second.** Compare against baseline. If promoted
   under-performs baseline, the local fill model is materially
   different from the official exchange; revert and analyse before
   uploading the alt.
3. **Alt third.** Only upload after the promoted result is in.
   Compare against both baseline and promoted. If alt out-performs
   promoted on the official site, the directional bet on PEPPER
   drift paid off.

## Acceptance criteria (plan)

| Criterion | Status |
|-----------|--------|
| One clean promoted candidate | PASS — `trader_round1_promoted.py` |
| One higher-upside alternate | PASS — `trader_round1_alt.py` |
| Optionally one baseline / control | PASS — `trader_round1_baseline.py` |
| Shortlist explicit | PASS — table above |
| Upload order explicit | PASS — section above |
| Reasons documented | PASS — Phase-5 review notes + this memo |

## Reproducing the bundles

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_1.export_round1_submission
# emits all three files under outputs/submissions/round_1/

PYTHONPATH=. .venv/bin/python -m src.scripts.validate_submission \
    outputs/submissions/round_1/trader_round1_promoted.py
# expected: 0 errors, 1 size warning (under hard budget)
```

## Local-reference table (for Phase-7 comparison)

Combined PnLs below come from running each variant's `EngineConfig`
through the full 3-day Round-1 replay with `BacktestSimulator`. Both
products trade independently in the engine, so the total is exactly
the sum of the per-product PnLs.

| Variant | File | Local total PnL | ASH PnL | PEPPER PnL | Key reason for inclusion |
|---------|------|----------------:|--------:|-----------:|--------------------------|
| Baseline | `trader_round1_baseline.py` | **+23 719** | +7 301 | +16 418 | Reference point. Phase-3 minimum-viable defaults. Every other variant should beat this on official PnL. |
| Promoted | `trader_round1_promoted.py` | **+60 462** | +6 447 | +54 015 | Cleanest Phase-5 robustness across ASH and PEPPER: best markouts, tightest cross-day variance, lowest limit pinning. Least dependent on local fill model. |
| Alt | `trader_round1_alt.py` | **+86 591** | +7 747 | +78 844 | Higher-upside variant: taker-heavier ASH + more aggressive PEPPER inventory. Directional bet that the +0.1/step drift and local fill model hold on the official site. |

Phase-7 comparisons should be logged against these local numbers —
anywhere the official result departs materially, treat it as evidence
about the local fill model or the drift persistence, not as a signal
to retune on one data point.

## Submission fingerprints

SHA256 + size per bundle, for tamper-checking and to make sure the
file you upload matches the one documented here.

| File | Size (bytes) | SHA256 |
|------|-------------:|--------|
| `outputs/submissions/round_1/trader_round1_baseline.py` | 88 082 | `b33913594f52a30b45fac7b3db9889e732459e0eec13b9455a07485bbec7bf8f` |
| `outputs/submissions/round_1/trader_round1_promoted.py` | 88 147 | `d7ed8979539b40961cb713d0eefc3efb2524c5ce268a80400dfe08582227aabd` |
| `outputs/submissions/round_1/trader_round1_alt.py` | 88 142 | `18d8088dd23e8f1abf5423392416a84c1756ddfd17698dc9d58643d8ba5aa6e9` |

Regenerate and verify with:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_1.export_round1_submission
shasum -a 256 outputs/submissions/round_1/trader_round1_*.py
```

If the hashes differ after a fresh export, the bundle is sensitive to
the source commit hash embedded in its banner — compare only the body
of the file (everything past the banner) or re-export against the
same commit to produce byte-identical bundles.

## Carry-ins for Phase 7

- **Confirm position_limit.** The Phase-1 placeholder of 50 affects
  every PnL number above. If the official limit is different, every
  upload must be re-exported.
- **Record what the official site reports** per the Phase-7 checklist
  in `docs/round_1/imc_testing_plan.md`.
- **Do not re-tune locally on a single official-PnL data point.**
  One run is one sample.
