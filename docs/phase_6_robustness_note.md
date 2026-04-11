# Phase 6 — Parameter sweeps and robustness testing

Phase 6 of the implementation plan
(`Tutorial/Implementation Plan.md:649`) is "Parameter sweeps and
robustness testing", with the explicit rule: **prefer stable
parameter regions, not the single highest backtest peak**. The
"done when" criteria are a recommended baseline config for both
products, plus documented robustness notes.

This note is the Phase 6 completion record.

## Completion summary

Phase 6 ran four sweeps total — one on EMERALDS and three on
TOMATOES — across three tutorial slices each (`day_-2`, `day_-1`,
combined). Every sweep was run through a single shared plateau
rule (within 10% of post-filter peak) and a six-part promotion
gate. **Both products retain their incumbent baselines.** No
edits to `default_engine_config()`. The robustness evidence,
heatmaps, and per-slice incumbent baseline blocks are archived
under `outputs/sweeps/<run_id>_phase6_<product>/`.

The Phase 6 cross-day analysis surfaced three findings worth
flagging beyond the verdict:

1. **EMERALDS execution axes are degenerate on the tutorial tape
   except for `maker_edge`.** The other three axes (`taker_edge`,
   `inventory_skew`, `flatten_threshold`) average to identical
   per-axis aggregates because none of them affect anything that
   actually fires on this tape.
2. **The `maker_edge=8` cliff phase 2C flagged is real and Phase 6
   correctly rejects it.** The plateau intersection contains 32
   rows; every single one sits at `maker_edge=8`. Gate check 4
   (regime shift) catches the 0%→100% maker share flip and
   downgrades the verdict to `retain`.
3. **The current TOMATOES `weighted_mid` baseline loses money on
   `day_-1` alone (-56 PnL) even though it earns +276 on the
   combined tape.** No alternative survives cross-day intersection
   either, so the verdict is still `retain`, but this is the first
   time we have a per-day decomposition of the incumbent and it's
   not flattering. Future rounds with more replay data should
   re-run Phase 6 against the new days.

## What Phase 6 added to the engine

- `src/backtest/plateau.py` — cross-slice plateau helper. Frozen
  dataclasses (`SlicePlateau`, `Phase6CrossSliceReport`,
  `ProductComparison`), ordered helpers
  (`filter_inventory_discipline`, `post_filter_peak`,
  `plateau_band`), categorical-safe `medoid`, sub-sweep
  `intersect_plateaus`, product-level `compare_subsweep_winners`,
  and writers that drop the cross-slice JSON / text artifacts
  alongside per-slice sweep summaries.
- `src/backtest/plateau_charts.py` — non-blocking 2D heatmap
  renderer. Reuses the lazy `_plt()` pattern from
  `src/backtest/charts.py` so the live trading path stays
  matplotlib-free. Failures degrade to an empty list and never
  block the plateau artifacts.
- `src/scripts/run_phase6_emeralds_sweep.py` — three-slice EMERALDS
  sweep entry point.
- `src/scripts/run_phase6_tomatoes_sweep.py` — three-slice
  TOMATOES sweep entry point. Drives three sub-sweeps and the
  product-level comparison step.
- `tests/test_plateau.py` — 25 unit tests covering filters, peak
  detection, plateau band, medoid, full intersection state
  machine (retain / narrow / promotion_candidate / diagnostic),
  gate failures (trade_count, regime), and the
  `compare_subsweep_winners` tie-break chain.

`src/core/config.py`, `src/strategies/`, `src/core/execution.py`,
and the live trader path were **not modified**. Phase 6 is a
research-and-decision phase; the only code change to the engine
was the new plateau module.

## Methodology (one rule, everywhere)

1. **Inventory-discipline filter.** Drop sweep rows with
   `steps_near_limit > 0`. The doctrine treats sitting at the
   position limit as a strategy failure regardless of headline
   PnL — Phase 5 used this same rule on `rolling_mid`, and Phase 6
   makes it the first thing every plateau computation does.
2. **Post-filter peak.** Compute `peak_pnl = max(pnl)` among
   surviving rows. Returns `None` if every row failed the filter
   (this happens once in Phase 6, on TOMATOES `rolling_mid`
   `day_-1` — flagged below).
3. **Plateau band.** Keep rows with `pnl >= 0.9 * peak_pnl`. This
   is the only plateau rule used anywhere in Phase 6 — there is
   no separate "top-10%" or "top-K" framing. The literal phrase
   "within 10% of post-filter peak" is the rule.
4. **Cross-slice intersection.** A config is in the Phase 6
   robust plateau iff its params key sits in the plateau band on
   `day_-2`, `day_-1`, **and** `combined`. The intersection rows
   are the combined-slice copies so downstream gate checks read
   combined-slice pnl / trade_count / maker_share.
5. **Medoid center (categorical-safe).** Pick the intersection
   member with the smallest sum of normalised distances to all
   others. Numeric axes contribute `|a - b| / axis_range`;
   categorical axes contribute 0 if equal, 1 otherwise. Tie-break
   by combined-slice pnl, then by `steps_near_limit`, then by
   sorted params key. **No coordinate-wise mean is taken
   anywhere**, because the TOMATOES grid contains a categorical
   axis (`fair_value_method`) that makes arithmetic means
   undefined.

### Promotion gate (six checks)

A plateau center may promote to `default_engine_config()` only
when **all six** checks pass. The first four are enforced
automatically by the sweep; the last two are a manual review-pack
step that must be completed before any edit to `src/core/config.py`.

| # | Check | Source | Threshold |
|---|-------|--------|-----------|
| 1 | PnL lift on combined slice | sweep | `center.pnl >= 1.10 * baseline.pnl` |
| 2 | Inventory discipline on every slice | sweep | `steps_near_limit == 0` on `day_-2`, `day_-1`, `combined` |
| 3 | Sane trade count / activity level | sweep | `0.5 * baseline.trade_count <= center.trade_count <= 3 * baseline.trade_count` on combined; `> 0` on each per-day slice |
| 4 | No unjustified maker/taker regime shift | sweep | `abs(center.maker_share - baseline.maker_share) <= 0.20`. `None` maker_share is treated as `0.0` so a "baseline trades nothing" → "candidate trades a lot" flip is correctly caught as a regime shift. |
| 5 | No markout degradation | manual review pack | `avg_markout_{1,5,20} >= 0.9 * incumbent` on a paired review pack via `run_review.py` |
| 6 | Timestamp drilldown vs incumbent | manual review pack | `run_drilldown.py` on the highest-divergence step confirms the candidate is doctrinally aligned (no unexplained maker/taker flip, no fade-into-adverse-move) |

Verdict mapping:
- Intersection empty → `retain`.
- Intersection 1–2 rows → `narrow` (archived as future-round candidate).
- Intersection ≥ 3 AND all four sweep-level checks pass → `promotion_candidate` (gate checks 5+6 still required).
- Intersection ≥ 3 AND any sweep-level check fails → `retain`.

Sub-sweeps flagged `role="diagnostic"` skip the promotion gate
entirely and are pinned to `verdict="diagnostic"`. They never
promote regardless of cross-day numbers. Phase 6 uses this hook
for the EWMA `α=0.20` validation read so the Phase 5 finding can
be cross-day-tested without reopening the Phase 5 decision.

## EMERALDS results

**Sweep label**: `phase6_emeralds`
**Artifacts**: `outputs/sweeps/20260411T205125Z_phase6_emeralds_emeralds/emeralds/`
**Grid**: 192 configs/slice (576 total runs)

| Axis | Values |
|------|--------|
| `maker_edge` | `{1.0, 2.0, 3.0, 4.0, 6.0, 8.0}` |
| `taker_edge` | `{1.0, 2.0}` |
| `inventory_skew` | `{1.5, 2.0, 2.5, 3.0}` |
| `flatten_threshold` | `{0.65, 0.70, 0.75, 0.80}` |

`maker_edge` was deliberately widened from the Phase 6 plan's
`{1, 2, 3}` up to 8 because `phase 2c` (commit `caa1d96`) reverted
`maker_edge` from 8 → 2 with this rationale, recorded in the
commit message: *"the tutorial trade tape only prints at
9992/10000/10008 so inside-spread maker quotes get zero
passive-fill credit; maker_edge=8 was chasing a simulation
artifact, not capturing edge. Phase 3 and Phase 6 will produce
the real tuned configuration."* Phase 6's job here is to surface
that cliff explicitly so the gate can rule on it.

### Per-slice incumbent baseline

The current EMERALDS default (`maker_edge=2.0, taker_edge=1.0,
inventory_skew=2.0, flatten_threshold=0.75`, `fair_value_method=anchor`,
anchor at 10000) generates **zero trades** on every slice. The
`in_plateau_band` flag is `no` on every slice because the
post-filter peak on each is dominated by `maker_edge=8` rows
(2144 PnL / 202 trades / 100% maker on combined) and the baseline
sits 100% below them.

| slice | baseline pnl | baseline trades | post-filter peak | in plateau band? | rows in band |
|-------|--------------|-----------------|------------------|-------------------|--------------|
| `day_-2` | 0.00 | 0 | 920.00 | no | 32 |
| `day_-1` | 0.00 | 0 | 1200.00 | no | 32 |
| `combined` | 0.00 | 0 | 2144.00 | no | 32 |

### Per-axis aggregates (combined slice)

```
maker_edge=1.0: mean_pnl=0.00, mean_trades=0.0, mean_near_limit=0.0
maker_edge=2.0: mean_pnl=0.00, mean_trades=0.0, mean_near_limit=0.0
maker_edge=3.0: mean_pnl=0.00, mean_trades=0.0, mean_near_limit=0.0
maker_edge=4.0: mean_pnl=0.00, mean_trades=0.0, mean_near_limit=0.0
maker_edge=6.0: mean_pnl=0.00, mean_trades=0.0, mean_near_limit=0.0
maker_edge=8.0: mean_pnl=2144.00, mean_trades=202.0, mean_near_limit=0.0
taker_edge=1.0: mean_pnl=357.33, mean_trades=33.7, mean_near_limit=0.0
taker_edge=2.0: mean_pnl=357.33, mean_trades=33.7, mean_near_limit=0.0
inventory_skew=*: mean_pnl=357.33 (identical across all four values)
flatten_threshold=*: mean_pnl=357.33 (identical across all four values)
```

Read: every cell in the EMERALDS grid where `maker_edge < 8` is a
zero. Every cell where `maker_edge == 8` is exactly 2144. The
other three axes are completely degenerate — `taker_edge`,
`inventory_skew`, and `flatten_threshold` average to identical
numbers because nothing about them changes how the strategy
interacts with the tape. There is no broad plateau anywhere on
the EMERALDS grid; there is one cliff at `maker_edge=8` and a
zero-PnL plain everywhere else.

### Cross-slice intersection and promotion gate

| | value |
|---|---|
| Intersection size | 32 |
| Medoid center | `maker_edge=8.0, taker_edge=1.0, inventory_skew=2.0, flatten_threshold=0.7` |
| Center pnl (combined) | 2144.00 |
| Center trade_count | 202 |
| Center maker_share | 100.0% |
| Center steps_near_limit | 0 |

| Gate check | Result |
|------------|--------|
| 1. PnL lift (≥ 1.10× baseline) | **PASS** (baseline pnl 0; center pnl 2144) |
| 2. Inventory discipline on every slice | **PASS** |
| 3. Sane trade count (0.5–3× baseline; > 0 per day) | **PASS** (special case: baseline trade_count is 0 so the bracket collapses to "center.trade_count > 0", which it is) |
| 4. Maker/taker regime shift ≤ 0.20 | **FAIL** — `\|1.00 - 0.00\| = 1.00` |

Gate check 4 fails by a wide margin. The candidate is a 100%
maker / 202 trade strategy; the incumbent is a no-trade strategy.
That is the largest possible regime shift the gate can catch.

### Verdict: RETAIN

Verdict reason: `gate check(s) failed: regime`.

The medoid center is the maker_edge=8 region phase 2c explicitly
flagged as a tutorial-tape artifact. The regime gate correctly
fires because the candidate is a fundamentally different strategy
(100% passive-credit harvesting at the trade-print prices) than
the incumbent (0% activity, principled tick-margin around the
anchor). Per the Phase 6 plan, gate 4 failure → automatic retain
with no manual review pack required.

The right reading of this verdict is **not** "Phase 6 saved us
from a 2144 PnL upgrade we would otherwise have shipped". The
right reading is "the EMERALDS tutorial tape is too thin to
support a tuned execution baseline, and Phase 6's robustness
gate correctly refuses to chase the only PnL-bearing region of
the grid because it's an artifact mechanism, not edge". A second
day's data — or any tutorial tape that prints at more than three
distinct prices — is the prerequisite for actually tuning
EMERALDS.

The current EMERALDS default (`maker_edge=2`, principled tick
margin) **stays as-is**. It is structurally honest and produces
zero PnL. It will produce real PnL the moment Prosperity ships a
real round tape with real spread structure.

## TOMATOES results

**Sweep label**: `phase6_tomatoes`
**Artifacts**: `outputs/sweeps/20260411T205442Z_phase6_tomatoes_tomatoes/`
**Three sub-sweeps**, one shared per-day baseline.

### How `history_length` affects each TOMATOES estimator family

Recorded in the Phase 6 plan; relevant to the sub-sweep design:

| Estimator | Reads `recent_mids`? | Effect of `history_length` ∈ `{16, 32, 48, 64}` |
|-----------|----------------------|--------------------------------------------------|
| `mid` | No | **No-op.** |
| `microprice` | No | **No-op.** |
| `weighted_mid` | Yes, but hard-capped at `LOOKBACK = 4` (`src/core/fair_value.py:123`) | **No-op for any value ≥ 4.** |
| `rolling_mid` | Yes, consumes the entire ring buffer | **Active.** Longer history → smoother mean, slower reaction. |
| `ewma_mid` | Yes, iterates the entire ring buffer with α decay | **Active but saturates.** At α=0.20 effective memory is ~5 samples; any history_length ≥ 20 is indistinguishable from infinite. |

A single cartesian
`fair_value_method × history_length × exec_axes` would have
produced fake plateau structure on the `history_length` axis for
`weighted_mid` rows, because that estimator does not read the
parameter. Phase 6 fixes this by running three independent
sub-sweeps.

### Sub-sweep A — `weighted_mid` (incumbent family)

Promotion-eligible. Execution-only sweep; `history_length` pinned
at the current default (48) because it's a no-op on this estimator.

Grid: `fair_value_method=weighted_mid`, `history_length=48`,
`maker_edge ∈ {1.0, 2.0}`, `taker_edge ∈ {1.0, 2.0}`,
`inventory_skew ∈ {2.0, 2.5, 3.0, 3.5}` → 16 configs/slice
(48 total runs).

#### Per-slice incumbent baseline

| slice | baseline pnl | baseline trades | maker_share | post-filter peak | in plateau band? | rows in band |
|-------|--------------|-----------------|-------------|------------------|-------------------|--------------|
| `day_-2` | **+225.00** | 6 | 6.2% | 225.00 | **yes** | 2 |
| `day_-1` | **-56.00** | 12 | 4.3% | 45.00 | **no** (-224% from peak) | 4 |
| `combined` | **+276.00** | 16 | 5.7% | 276.00 | **yes** | 1 |

This is the sweep's most surprising finding for the incumbent.
The current TOMATOES default sits **on the per-slice peak** on
`day_-2` and on the combined tape, but is **out of the plateau
band on day_-1** by a wide margin: the day_-1 post-filter peak is
+45 PnL, the incumbent gets -56, and the gap is more than 100%
of the day_-1 peak. The combined tape's +276 hides this entirely:
+225 on day_-2 plus −56 on day_-1 only sums to +169, so the extra
+107 of combined PnL comes from cross-day position carryover and
from markout horizons that span the day boundary. None of that
shows up on a per-day decomposition.

#### Cross-slice intersection

| | value |
|---|---|
| Intersection size | **0** |
| Center | none |
| Verdict | **retain** |
| Reason | "plateau intersection is empty across slices" |

Disjoint plateaus. The combined-slice plateau (1 row, the
incumbent itself) does not intersect with the day_-1 plateau (4
rows, none of which is the incumbent). No promotion candidate
exists.

### Sub-sweep B — `rolling_mid` (history-sensitive)

Promotion-eligible. Adds the `history_length` axis. Grid:
`fair_value_method=rolling_mid`, `history_length ∈ {16, 32, 48, 64}`,
`maker_edge ∈ {1.0, 2.0}`, `taker_edge ∈ {1.0, 2.0}`,
`inventory_skew ∈ {2.0, 2.5, 3.0, 3.5}` → 64 configs/slice
(192 total runs).

#### Per-slice incumbent baseline (same incumbent as sub-sweep A)

| slice | post-filter peak | rows in band | notes |
|-------|------------------|--------------|-------|
| `day_-2` | 827.50 | 1 | incumbent 73% below peak |
| `day_-1` | **n/a** | 0 | **every rolling_mid config fails the inventory filter** |
| `combined` | 914.00 | 1 | incumbent 70% below peak |

The day_-1 row reads "n/a (no inventory-disciplined rows)" because
**every single configuration in the sub-sweep B grid spent at least
65 steps near the position limit on day_-1**. Per-axis day_-1
near-limit averages range from 286 (`history_length=16`) to 1080
(`history_length=64`) — longer history → more inventory stress,
monotonically. This is the cleanest possible corroboration of the
Phase 5 reading that **rolling_mid is the negative control**: it
earns headline PnL by sitting at the position limit, not by making
better decisions.

#### Cross-slice intersection

| | value |
|---|---|
| Intersection size | **0** |
| Verdict | **retain** |
| Reason | "plateau intersection is empty across slices" |

Cannot intersect with an empty day_-1 plateau (every row was
filtered). Phase 6 plateau rule terminates cleanly.

### Sub-sweep C — `ewma_mid` at fixed `α=0.20` (DIAGNOSTIC ONLY)

**Role**: `diagnostic`. Gate not evaluated. Verdict pinned to
`diagnostic`. **Not eligible for promotion regardless of outcome.**

`ewma_alpha=0.20` is a **Phase 5 validation pin**, not a Phase 6
tunable parameter. Phase 5
(`docs/phase_5_tomatoes_baseline_note.md`) found `α=0.20` was a
2-of-8 narrow peak on the combined tape. Phase 6 sub-sweep C
asks the cleaner cross-day question: **does that narrow peak
survive on `day_-2` and `day_-1` in isolation?**

Grid: `fair_value_method=ewma_mid`, `ewma_alpha=0.20`,
`history_length ∈ {16, 32, 48, 64}`, `maker_edge ∈ {1.0, 2.0}`,
`taker_edge ∈ {1.0, 2.0}`, `inventory_skew ∈ {2.0, 2.5, 3.0, 3.5}` →
64 configs/slice (192 total runs).

#### Cross-day plateau read

| slice | post-filter peak | rows in band |
|-------|------------------|--------------|
| `day_-2` | 937.50 | 8 |
| `day_-1` | 632.00 | 3 |
| `combined` | **1301.00** | 3 |

The combined-slice peak of 1301 reproduces the Phase 5 number
exactly (Phase 5 stage 3 reported 1301 PnL at `α=0.20`,
`inventory_skew=3.0`, `maker_edge=1.0`, `taker_edge=1.0`,
`steps_near_limit=0`). That's the Phase 5 narrow peak.

| | value |
|---|---|
| Intersection size | **0** |
| Verdict | **diagnostic** |
| Reason | "sub-sweep is diagnostic-only (no promotion)" |

**Cross-day reading: the Phase 5 narrow peak does NOT survive
cross-day intersection.** No EWMA configuration sits in the
plateau band on `day_-2`, `day_-1`, **and** `combined`
simultaneously. The combined-slice plateau is dominated by 3
rows that all use `inventory_skew=3.0`; the day-level plateaus
contain rows with different inventory skew or maker_edge
combinations. The 10% plateau bands simply do not overlap.

This is the strongest possible corroboration of the Phase 5
"retain incumbent" decision. Phase 5 already rejected EWMA on
markouts (gate check 5) and called the plateau "the weakest of
the six checks". Phase 6 confirms with a different methodology
that the plateau is also unstable cross-day. The two pieces of
evidence point the same direction.

The EWMA per-axis aggregates also show why this was always going
to be brittle: averaged across all configurations the EWMA mean
near-limit is **31 steps**, with `taker_edge=1.0` averaging **62
steps near the limit**. Only `inventory_skew >= 3.0` keeps the
inventory budget clean across the grid. The EWMA family is
inventory-fragile, and the Phase 5 narrow peak survives only
because it sits exactly on the one inventory_skew value where the
fragility doesn't bite on the combined tape. That coincidence
does not hold on day_-2 vs day_-1 individually.

### TOMATOES product-level comparison

Sub-sweep C is excluded from winner selection per its diagnostic
role. The remaining two sub-sweeps (A and B) both verdicted
`retain` with empty intersections.

| | value |
|---|---|
| Considered | `weighted_mid`, `rolling_mid` |
| Excluded | `ewma_mid_alpha_020` (diagnostic) |
| Winner | (none) |
| Verdict | **retain** |
| Reason | "no eligible sub-sweep reached promotion_candidate" |

Manual gate checks 5 and 6 are not exercised because no candidate
is in `promotion_candidate`. `default_engine_config()` for
TOMATOES is unchanged.

## Decision

| Product | Verdict | `default_engine_config()` change |
|---------|---------|-----------------------------------|
| **EMERALDS** | **retain** | none |
| **TOMATOES** | **retain** | none |

`src/core/config.py` is **not modified** in Phase 6. EMERALDS
keeps `anchor` fair value with `maker_edge=2.0, taker_edge=1.0,
inventory_skew=2.0, flatten_threshold=0.75`. TOMATOES keeps
`weighted_mid` fair value with `maker_edge=1.0, taker_edge=1.0,
inventory_skew=3.0, flatten_threshold=0.7, history_length=48`.

`tests/test_config.py` is unchanged. No new locking tests are
added because no defaults moved.

The recommended baseline for both products **is** the current
default. The Phase 6 sweep + plateau + gate evidence is what
justifies that recommendation, archived alongside this note.

TOMATOES retention in particular is a **robustness decision, not
a "best on every slice" decision**: the current `weighted_mid`
default loses -56 PnL on `day_-1` in isolation, but no
cross-slice-stable alternative beats it cleanly across all three
slices, so retaining the incumbent is the most defensible call
the Phase 6 evidence supports.

## Heatmaps (non-blocking diagnostic)

2D `maker_edge × inventory_skew` heatmaps were rendered for every
sub-sweep on every slice via `render_plateau_heatmaps`. They live
under each sub-sweep directory's `heatmaps/` folder, e.g.:

- EMERALDS: `outputs/sweeps/20260411T205125Z_phase6_emeralds_emeralds/emeralds/heatmaps/`
- TOMATOES `weighted_mid`: `outputs/sweeps/20260411T205442Z_phase6_tomatoes_tomatoes/weighted_mid/heatmaps/`
- TOMATOES `rolling_mid`: `outputs/sweeps/20260411T205442Z_phase6_tomatoes_tomatoes/rolling_mid/heatmaps/`
- TOMATOES `ewma_mid_alpha_020`: `outputs/sweeps/20260411T205442Z_phase6_tomatoes_tomatoes/ewma_mid_alpha_020/heatmaps/`

Each heatmap shows mean PnL averaged across the other grid axes,
plateau-band cells outlined in white, and a red marker for the
incumbent baseline cell. The EMERALDS heatmap is the visually
clearest exhibit of the cliff: every cell except the
`maker_edge=8` column is a flat zero plain.

Heatmaps are **non-blocking** for Phase 6 acceptance. They are a
diagnostic layered on top of the core sweep + plateau + gate
artifacts, and the verdict above is decided by the numerical
evidence, not the pictures.

## Reproduce this phase

```bash
source .venv/bin/activate

# 1. Plateau unit tests
PYTHONPATH=. pytest tests/test_plateau.py -q

# 2. Full pytest suite
PYTHONPATH=. pytest -q

# 3. EMERALDS three-slice sweep + heatmaps + verdict
PYTHONPATH=. python -m src.scripts.run_phase6_emeralds_sweep \
  --label phase6_emeralds

# 4. TOMATOES three-slice sweep (three sub-sweeps + product
#    comparison) + heatmaps + verdict
PYTHONPATH=. python -m src.scripts.run_phase6_tomatoes_sweep \
  --label phase6_tomatoes

# 5. Inspect artifacts
ls outputs/sweeps/*_phase6_emeralds_emeralds/
ls outputs/sweeps/*_phase6_tomatoes_tomatoes/
```

Expected artifact tree:

```
outputs/sweeps/<run_id>_phase6_emeralds_emeralds/
  emeralds/
    day_-2/summary.{json,txt}
    day_-1/summary.{json,txt}
    combined/summary.{json,txt}
    plateau_intersection.{json,txt}
    heatmaps/{day_-2,day_-1,combined}_maker_edge_x_inventory_skew.png

outputs/sweeps/<run_id>_phase6_tomatoes_tomatoes/
  weighted_mid/
    day_-2/summary.{json,txt}
    day_-1/summary.{json,txt}
    combined/summary.{json,txt}
    plateau_intersection.{json,txt}
    heatmaps/...
  rolling_mid/                      # same shape
  ewma_mid_alpha_020/                # same shape (diagnostic verdict)
  product_comparison.{json,txt}     # winner: none, verdict: retain
```

If a future round ships new replay days, both Phase 6 entry
scripts can be re-run unchanged. The plateau module, gate, and
diagnostic-only EWMA hook are general — they don't bake in
anything specific to the current tutorial tape.

## Status vs plan

- Phase 1: complete
- Phase 2: complete
- Phase 3: complete
- Phase 4a: complete
- Phase 4b: complete
- Phase 5: complete (`docs/phase_5_tomatoes_baseline_note.md`)
- **Phase 6: complete — three-slice cross-day sweeps run on
  EMERALDS and TOMATOES (three sub-sweeps), plateau module +
  gate + medoid + product comparison shipped, both products
  retained their incumbent baselines with documented evidence,
  and the Phase 5 EWMA narrow-peak finding was cross-day
  validated and corroborated as not surviving.**
- Phase 7 (signal scanner): not started.
- Phase 8 (residual capacity): not started.
- Phase 9 (submission hardening): partially shipped per prior notes.
- Phase 10 (docs + round readiness): not started.
