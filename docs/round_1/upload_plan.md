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
>
> **Phase-8.5 follow-up.** A fourth revised candidate **H1** has
> been exported. H1 = promoted PEPPER leg (validated) + alt ASH leg
> (best official ASH). Prepared but not uploaded. See
> `outputs/round_1/phase8_5/hybrid_memo.md`.
>
> **Phase-9 fastsearch follow-up.** A fifth candidate **F5** has
> been exported. F5 = alt ASH leg (same as H1) + promoted PEPPER
> leg with asymmetric taker edges (buy=1.5, sell=3.0). Prepared
> but not uploaded. This is the sole new candidate identified in
> the Phase-9 PEPPER-first search; it preserves promoted's
> inventory profile while targeting the official-day Baseline
> failure mode (bucket-0 wrong-side PEPPER sells). See
> `outputs/round_1/fastsearch/final_recommendation.md` and
> `outputs/round_1/fastsearch/f5_bundle_metadata.md`.

## Submission files

All three are bundled by
`src/scripts/round_1/export_round1_submission.py` from a single Round-1
config factory each, so the only differences between them are the
embedded `ProductConfig` fields.

| # | Variant | File | Source factory | Local 3-day PnL |
|---|---------|------|----------------|------------------|
| 1 | **Baseline / control** | `outputs/submissions/round_1/trader_round1_baseline.py` | `round1_baseline_engine_config()` | ~+24 k |
| 2 | **Promoted / robust default** | `outputs/submissions/round_1/trader_round1_promoted.py` | `round1_promoted_engine_config()` | ~+60 k |
| 3 | **Higher-upside alternate** | `outputs/submissions/round_1/trader_round1_alt.py` | `round1_alt_engine_config()` | ~+87 k |
| 4 | **H1 (Phase-8.5 hybrid)** — promoted PEPPER + alt ASH | `outputs/submissions/round_1/trader_round1_h1.py` | `round1_h1_engine_config()` | ~+61.8 k |
| 5 | **F5 (Phase-9 asymmetric)** — alt ASH + promoted PEPPER with buy=1.5/sell=3.0 | `outputs/submissions/round_1/trader_round1_f5.py` | `round1_f5_engine_config()` | ~+100.7 k |

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

`quote_size`/`max_aggressive_size` are kept constant across
variants.

**`position_limit` is 80 per product** — IMC-confirmed Round-1 cap.
The engine config was updated from the 50-placeholder in a separate
commit, and every variant has been re-exported under
`outputs/submissions/round_1/limit_80/`. The prior limit=50 bundles
in `outputs/submissions/round_1/*.py` (one directory up) are
preserved as historical references matching the already-recorded
official PnLs in `outputs/round_1/official_results/`. See
`outputs/round_1/limit_80/analysis.md` for the pre-change review
and `outputs/submissions/round_1/limit_80/README.md` for the fresh
fingerprints.

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

### Phase 6 (original — already complete)

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

### Phase 8.5 (revised — post-first-official-run)

Given official results have Alt > Promoted > Baseline and the gap
is dominated by the ASH leg, the **current recommended next upload**
is:

4. **H1 (revised candidate).** Upload exactly once the slot is
   available. H1 isolates the empirically-justified ASH uplift
   (wall_mid + t=0.5) while keeping Promoted's validated PEPPER leg.
   Expected official uplift over Promoted ≈ +260 PnL
   (the known ewma→wall gap on Round-1 data). Promotes H1 to
   default if it beats Promoted; otherwise keep Promoted.

Do **not** re-upload Baseline, Promoted, or Alt. Their official
results are already in. The default shipped bundle stays at
Promoted until H1 validates.

### Phase 9 (fastsearch — the next additive candidate)

Prepared but not uploaded:

5. **F5 (asymmetric-taker PEPPER + alt ASH).** Upload after H1 has
   a data point — or in the same slot cycle if two new slots are
   available — so that the ASH leg (shared with H1) is held fixed
   and the **only observed difference** between F5 and H1 on the
   official site is the PEPPER asymmetric-taker change. That
   isolates the F5 mechanism to a single observable variable.

   Expected official uplift over Promoted (projected, not
   observed): ≈ +200-300 PEPPER PnL on the 1000-cadence ratio,
   landing F5 total near Alt (~+3 040) without importing Alt's
   near-limit tail risk. Projection method and caveats in
   `outputs/round_1/fastsearch/final_recommendation.md` §1.

   Local 3-day total: **+100 685** (vs Promoted +60 462, Alt
   +86 591). The cross-view ranking picture:

   | View | Promoted | Alt | H1 | F5 |
   |---|---:|---:|---:|---:|
   | Official total (measured) | +2 518 | +3 040 | +2 780 | _projected ~+2 700-2 900_ |
   | Local 1000-cadence PEPPER | +16 321 | +21 087 | +16 321 | +18 661 |
   | Local 3-day PEPPER        | +54 015 | +78 844 | +54 015 | +92 938 |
   | Off-day near-limit PEPPER | 0 | 22 | 0 | _projected ~6-10_ |

   Do **not** retune based on F5's projected numbers. Projections
   are from a single-point local-to-official ratio; the IMC run is
   the only ground truth.

Do **not** re-upload Baseline, Promoted, or Alt. Their official
results are already in. The default shipped bundle stays at
Promoted until H1 (and then F5) validates.

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
| `outputs/submissions/round_1/trader_round1_h1.py` | 89 708 | `47217a37f7b7babb077b5e666fcb300e34da3cd93168bf4d2b3a7124fdafacc5` |
| `outputs/submissions/round_1/trader_round1_f5.py` | 96 970 | `cdef85dd97474c84df4af71b3ba662c3107653beb1cad1e02934c6cde987cc9a` |

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

- ~~**Confirm position_limit.**~~ Resolved: 80 per product. Fresh
  limit=80 bundles live under
  `outputs/submissions/round_1/limit_80/` with SHA256 fingerprints
  in that folder's `README.md`. The limit=50 bundles at
  `outputs/submissions/round_1/*.py` remain as the historical
  references matching the recorded official PnL.
- **Record what the official site reports** per the Phase-7 checklist
  in `docs/round_1/imc_testing_plan.md`.
- **Do not re-tune locally on a single official-PnL data point.**
  One run is one sample.
- **New: limit=80 rankings are NOT known.** Everything in this plan's
  "upload order" rationale was derived against limit=50 data. Alt in
  particular gains the most capacity at limit=80 (rides to ±72 now
  vs ±45 before). Do not treat the old ranking as a guarantee that
  carries forward.
