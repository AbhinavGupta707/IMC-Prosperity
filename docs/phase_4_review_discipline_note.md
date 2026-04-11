# Phase 4a Review Discipline Note

Phase 4a (the "data layer + charts" half of doctrine Phase 4) is now
in place. This note describes what each review pack contains, how to
read it, and how to reproduce a run from its manifest.

## How to generate a pack

```bash
source .venv/bin/activate
PYTHONPATH=. python -m src.scripts.run_review --label <short_tag>
```

Add `--no-charts` to skip PNG rendering if you only need the metrics
and manifest. Everything lands under
`outputs/review_packs/<timestamp>_<label>/`.

## Contents of a review pack

```
outputs/review_packs/<run_id>/
  manifest.json       # provenance (see below)
  summary.json        # per-product aggregates including edge/markouts
  summary.txt         # two human-readable tables
  trades.json         # one record per fill, decision + fill context
  series.json         # mid / fair-value / pnl step series
  charts/             # PNG artifacts (see below)
  notes.md            # structured human review template
```

## What the aggregate metrics mean

| Column  | Meaning |
|---------|---------|
| `edge`  | Quantity-weighted average **entry edge** = `sign × (fair_value_at_decision − price)`. Positive = trader believed it had an edge on the favourable side of its own fair value **at the moment it committed to the order**. |
| `edge_n`| Number of fills that contributed to `edge`. Fills where the decision-time fair value was missing are dropped. |
| `mk_1`  | Quantity-weighted average **markout** at +1 step = `sign × (mid[fill_step + 1] − price)`. Positive = trade looked favourable one step after the money moved. Uses **observable** mids only — no carry-forward. |
| `mk_5`, `mk_20` | Same formula at horizons +5 and +20 steps. |
| `mk_*_n`| Sample size for that horizon. Horizons that fall past the end of the replay (or land on a one-sided book) silently drop that record. Always read the count next to the mean. |

Entry edge uses **decision-time** fair value. Markouts use
**fill-time** execution price vs future observable mids. The
distinction matters for passive fills: a maker quote placed at step
T that clears at step T+K should be scored against the fair value we
believed at T, not the fair value we would compute at T+K. The
simulator threads this through via a private
`_PendingMakerOrder` type that bundles decision context with the
resting order.

## What the charts show

Rendered under `charts/` when `--no-charts` is not passed:

- `price_vs_fair_<PRODUCT>.png` — observable mid overlaid with the
  decision-time fair value the trader used each step. Taker fills
  are opaque ▲/▼ markers; maker fills are faded. First thing to
  look at when diagnosing surprising PnL.
- `pnl_over_time_<PRODUCT>.png` — cumulative PnL per step. The
  series is **gap-free**: when the book is one-sided, the last
  observed mid is carried forward for marking purposes. Trade
  effects and unrealised PnL both roll through here.
- `position_over_time_<PRODUCT>.png` — running position path. Look
  for periods stuck near the limit (use with `steps_near_limit`
  from summary).
- `maker_taker_<PRODUCT>.png` — horizontal bar showing buy/sell
  totals split by mode. Useful to spot "I thought I was market
  making but I'm 90% taker" regressions.
- `markouts_<PRODUCT>.png` — three histograms, one per horizon, with
  the mean marked. Most profitable: positive mass at +1 that
  sustains at +20. A strong +1 that reverses by +20 is a
  fast-alpha / stale-fair-value warning.
- `pnl_over_time_total.png` — single-line total PnL across all
  products, step-index aligned. The fastest chart to skim.

## How to fill in `notes.md`

The template has five sections. Phase 4a's whole point is that
**none of them should be left blank** before a change is accepted.

1. **Decision** — one of `keep`, `modify`, `discard`. Only three
   states; if you want to say "keep but tune later", write `modify`
   and put the tuning idea in *Next change to test*.
2. **What looked good** — concrete, chart-referenced observations.
   "TOMATOES price_vs_fair shows fair tracking mid on drift-up
   regime" beats "TOMATOES looks fine".
3. **What looked bad** — same rules. Blank is not an answer.
4. **Most important chart to inspect** — name the file and, when
   applicable, the timestamp window to zoom into. The Phase 4b
   drilldown tool (not yet built) will eventually read this.
5. **Next change to test** — the specific hypothesis for the next
   experiment. "Try `maker_edge=1` on EMERALDS for 1 day of replay"
   is actionable; "tune more" is not.

## Reproducing a pack from `manifest.json`

Every pack records enough state to be re-run bit-for-bit if the
working tree is at the same commit:

```json
{
  "run_id": "<timestamp>_<label>",
  "git_commit": "<short hash>",
  "git_dirty": false,
  "data_files": ["data/raw/..."],
  "engine_config": { "products": { "...": { ... } } },
  "estimators_per_product": { "...": { "primary": "...", "fallbacks": [...] } },
  "markout_horizons": [1, 5, 20]
}
```

To reproduce:

1. `git checkout <git_commit>` (`git_dirty=true` in a saved pack
   means the comparison isn't exactly reproducible — that's ok for
   day-to-day iteration, not ok for anything we're quoting as a
   result).
2. Confirm the CSVs in `data_files` still exist at the listed
   paths.
3. Run `python -m src.scripts.run_review --label <anything>` (or
   construct a custom `Trader` with the snapshot `engine_config`
   and drive `BacktestSimulator` directly).

## Phase 4b — timestamp-level drilldowns

Phase 4b builds **on top of** a Phase 4a review pack without
re-running the simulator. It reads `manifest.json`, `trades.json`
and `series.json`, rebuilds the local book by re-replaying the slice
of CSVs listed in `manifest.data_files`, and writes per-case
artifacts under the source pack's own `drilldowns/` subdirectory so
provenance stays self-contained.

### How to generate drilldowns

```bash
PYTHONPATH=. python -m src.scripts.run_drilldown \
  --pack outputs/review_packs/<run_id> \
  [ --trade-id N
  | --timestamp T --product P
  | --best-trades N
  | --worst-trades N
  | --near-limit [--near-limit-count N] ] \
  [--rank-metric edge|markout_1|markout_5|markout_20]   (default markout_5) \
  [--window 30] \
  [--no-charts]
```

The modes combine freely in one call — `--best-trades 3 --worst-trades 3 --near-limit`
produces up to seven case directories in one run. Cases are de-duplicated by
case id, so passing the same fill via both `--trade-id` and `--best-trades`
only writes it once.

### Case layout

```
outputs/review_packs/<run_id>/drilldowns/<case_id>/
  summary.json       # case metadata + key figures + trades_in_window
  window_series.json # mid / fair / pnl / position slices + book snapshots
  notes.md           # case-specific review template
  charts/
    price_vs_fair_window.png  # zoomed mid + fair with the anchor marked
    book_depth.png            # best bid/ask bars at the anchor step
    pnl_position_window.png   # two-panel pnl + position over the window
```

Case id patterns:

| Selection flag  | Case id |
|-----------------|---------|
| `--trade-id`    | `trade_<idx>_<product>_<fill_ts>` |
| `--timestamp`   | `timestamp_<product>_<timestamp>` |
| `--best-trades` | `best_<rank>_<metric>_<product>_<fill_ts>` |
| `--worst-trades`| `worst_<rank>_<metric>_<product>_<fill_ts>` |
| `--near-limit`  | `near_limit_<rank>_<product>_<timestamp>` |

### Picking a rank metric

| Metric      | Meaning                                               | When to use |
|-------------|-------------------------------------------------------|-------------|
| `edge`      | Decision-time fair value vs fill price, per unit.     | Decide whether *we believed* the fill was on the favourable side of fair. Dropouts for fills with no decision-time fair value. |
| `markout_1` | Realized fill vs mid one step later, per unit.        | Fastest signal — surfaces fills where the next tick instantly disagreed with us. |
| `markout_5` | Realized fill vs mid five steps later, per unit.      | Default. Smooths out 1-step noise without waiting for 20 steps of drift. |
| `markout_20`| Realized fill vs mid twenty steps later, per unit.    | Surfaces slow edge and mean-reversion traps. Dropouts near the end of the replay. |

Scores are **per unit**, not quantity-weighted, so small decisive
fills bubble up alongside bigger ones. The aggregate tables in
`summary.txt` remain quantity-weighted — the two views answer
different questions and should be read together.

### Anchors: decision vs fill timestamp

The drilldown window is always anchored on the **fill** timestamp
because that is where the position actually moved and the book
snapshot is meaningful. For maker fills, `summary.json` preserves
both timestamps under `extra.decision_timestamp` and
`extra.fill_timestamp` so the reviewer can see the gap between when
the trader committed to the quote and when it finally cleared.

### Near-limit drilldowns

Near-limit cases are emitted for steps where
`|position| / position_limit >= 0.75` (matching
`simulator._NEAR_LIMIT_FRACTION`). The tutorial baseline has
**zero** near-limit steps because TOMATOES never accumulates large
inventory, so `--near-limit` on the tutorial pack is a no-op. The
flow is covered by synthetic unit tests (`tests/test_drilldown.py`)
and will exercise real data as soon as a strategy actually parks
itself near the limit.

## Current status vs plan

- Phase 4a (data layer + charts + enriched pack): **complete**
- Phase 4b (timestamp drilldowns for best/worst trades, explicit
  timestamps, and near-limit slices): **complete**
- Phase 5 (TOMATOES dynamic challenger implemented and evaluated):
  **complete** — see `docs/phase_5_tomatoes_baseline_note.md`. A
  principled `ewma_mid` estimator was added to the fair-value engine
  and run through the four-stage evaluation workflow (fit+replay,
  alpha plateau sweep, challenger-vs-incumbent head-to-head,
  timestamp divergence drilldown). The incumbent `weighted_mid`
  baseline was retained; `ewma_mid` ships registered-but-not-default.
- Phase 6 (robustness sweeps) and Phase 7 (signal scanner): not
  started.
