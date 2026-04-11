# Phase 5 — TOMATOES dynamic challenger implemented and evaluated

Phase 5 of the implementation plan is "TOMATOES end-to-end baseline".
Prior phases already shipped a working TOMATOES path on `weighted_mid`
as a side-effect of Phases 2 and 3. Phase 5's real job was to close
the loop: implement a principled dynamic-fair-value challenger,
evaluate it with discipline against the incumbent, and record the
baseline decision.

This note is the Phase 5 completion record.

**Completion summary**

- **Dynamic TOMATOES challenger implemented.** `EwmaMidEstimator` is
  now a registered, tested estimator in the fair-value engine with a
  configurable decay, documented cold-start behaviour, and its own
  plateau-sweep script.
- **Challenger evaluated end-to-end.** The four-stage Phase 5
  workflow (fit+replay, alpha plateau, challenger-vs-incumbent,
  timestamp drilldown) was run against the tutorial replay, all
  artifacts archived under `outputs/`.
- **Incumbent baseline retained.** `weighted_mid` remains the default
  TOMATOES fair-value method. The challenger failed two of the six
  promotion-rule checks the Phase 5 plan committed to, and its
  PnL-improving region was a narrow peak rather than a broad plateau.
  `ewma_mid` stays registered-but-not-default so future rounds can
  re-run the same evaluation against richer data.

## What Phase 5 added to the engine

- `EwmaMidEstimator` in `src/core/fair_value.py`, registered as
  `"ewma_mid"` in `ESTIMATORS`. Reads `memory.recent_mids` + the
  current `snapshot.mid`, applies the exponential recurrence
  `ewma = α · mid + (1 − α) · ewma` oldest-to-newest, and blends in
  the current mid as the final term. Stateless with respect to the
  request: no new persistent fields on `ProductMemory`.
- Explicit cold-start behaviour: empty history + no current mid →
  return `None` and let the fallback chain run; empty history + valid
  mid → bootstrap with the current mid (flagged
  `components.bootstrap=1.0`); `α=1` collapses to the current mid by
  construction.
- `ProductConfig.ewma_alpha: float | None = None` in `src/core/config.py`
  with `0 < α ≤ 1` validation. Unset means "use the module default",
  pinned in `_DEFAULT_EWMA_ALPHA = 0.3` so tests have a fixed anchor.
- `src/scripts/compare_fair_values.py` gained an `--estimators` flag
  so the Phase 5 Stage 1 comparison could drive the four canonical
  estimators without touching `DEFAULT_COMPARISON_ESTIMATORS` (so
  Phase 3 reproductions remain bit-for-bit stable).
- `src/scripts/run_phase5_ewma_sweep.py` — a thin wrapper over the
  existing `parameter_sweep` infrastructure that runs an alpha-only
  sweep on TOMATOES at the Phase 3 tuned execution baseline, with a
  `--grid coarse|fine` switch for plateau checking.
- Unit tests in `tests/test_fair_value.py` and `tests/test_config.py`
  covering the formula, alpha=1, empty history bootstrap,
  one-sample-history blending, no-mid-no-history fallback,
  config-alpha sensitivity, module-default fallback, fallback-chain
  handoff, alpha validation range, `None` default, and boundary
  acceptance at `α=1`.

`src/trader.py`, `src/strategies/market_making.py`,
`src/core/execution.py`, `src/core/risk.py`, `src/core/signals.py`,
`src/backtest/simulator.py`, `src/backtest/metrics.py` were read but
not modified. Phase 5 is a fair-value-layer addition by design, the
doctrine's "single interface for all fair-value estimators" absorbs
this without touching downstream modules.

## Stage 1 — fit + replay head-to-head

Run label `phase5_stage1`, report at
`outputs/fair_value_comparison/20260411T185309Z_phase5_stage1/`.
Estimators compared: `mid, rolling_mid, weighted_mid, ewma_mid`
(the `ewma_mid` row uses the module default `α=0.3`).

```
[TOMATOES] live_method=weighted_mid
estimator      cov%  mae_now   mae_n1     d_n1   mae_n5        pnl  trades    mk%  near
---------------------------------------------------------------------------------------
mid           100.0    0.000    0.790   +0.000    1.231      -9.00       7  100.0     0
rolling_mid   100.0    1.693    1.745   +0.955    1.921    1167.00     400    0.3  1341
weighted_mid  100.0    0.536    0.815   +0.025    1.187     276.00      16    5.7     0
ewma_mid      100.0    0.579    0.828   +0.038    1.189     273.00      34    2.3     0
```

Read: at default `α=0.3`, `ewma_mid` is economically
indistinguishable from the incumbent (PnL 273 over 34 trades vs
PnL 276 over 16 trades) while tracking mid almost as well
(`mae_n1` +1.6%, `mae_n5` +0.17%). `rolling_mid` remains the
negative control — it earns $1167 across 400 trades but sits at
the position limit for 1341 steps, which disqualifies it on
inventory grounds regardless of headline PnL. On default execution,
EWMA at the module default alpha is in the ballpark but not
compelling; Stage 2 is where any interesting region would have to
appear.

## Stage 2 — EWMA alpha plateau sweep

The Phase 5 plateau check ran in two passes so that the decision was
not taken on a single-grid artifact.

**Plateau criterion (committed in the plan).** Promotion rule 4
requires that the winning alpha sit on a plateau of **at least two
contiguous grid points whose PnL is within 10% of the peak, with
zero near-limit steps**. A single isolated PnL spike, or a peak
flanked only by near-limit-disqualified neighbours, counts as a
narrow peak and is rejected.

**Pass 1 — coarse grid.** Run label `phase5_tomatoes_alpha`, sweep
report under `outputs/sweeps/`. Grid
`α ∈ {0.1, 0.2, 0.3, 0.4, 0.5, 0.7, 0.9}`, Phase 3 tuned execution
config held constant, `ewma_alpha` varied only.

**Pass 2 — fine grid around the coarse peak.** Run label
`phase5_tomatoes_alpha_fine`. Grid
`α ∈ {0.12, 0.14, 0.16, 0.18, 0.20, 0.22, 0.25, 0.28}`, same
execution config. This pass exists specifically to distinguish
"narrow peak" from "narrow plateau" around the coarse grid's
apparent winner at `α=0.20`, because the coarse grid jumps from
1301 at `α=0.20` to 273 at `α=0.30` and a coarse grid cannot rule
out a hidden plateau.

```
coarse grid
 alpha        pnl  trades    mk%  near  pos
-------------------------------------------
   n/a     276.00      16    5.7     0    6   <- incumbent (weighted_mid)
   0.1    1072.00     234    0.4   349    5
   0.2    1301.00     115    0.2     0    7
   0.3     273.00      34    2.3     0    6
   0.4    -129.00       9   20.0     0    6
   0.5      49.00       6  100.0     0   -2
   0.7      46.00       4  100.0     0   -2
   0.9       7.00       5  100.0     0   -1

fine grid (around the coarse peak)
 alpha        pnl  trades    mk%  near  pos
-------------------------------------------
  0.12    1059.00     199    0.5   273    2
  0.14    1140.00     177    0.3   163    3
  0.16     940.00     152    0.4   163    3
  0.18    1171.00     124    0.2     0    3
   0.2    1301.00     115    0.2     0    7
  0.22     957.00      93    0.6     0    6
  0.25     417.00      68    0.8     0    6
  0.28     468.00      44    1.3     0    5
```

Read across both passes, the alpha landscape has three regimes on
this tutorial replay.

1. **`α ≤ 0.16` — too responsive.** High PnL but persistent
   near-limit stress (coarse `α=0.10`: 349 near-limit; fine `α=0.12`:
   273; `α=0.14` / `α=0.16`: 163). Disqualified on rule 3 regardless
   of headline PnL.
2. **`α ∈ {0.18, 0.20}` — the only inventory-safe PnL region.**
   `α=0.20` is the peak (1301, zero near-limit). `α=0.18` (1171,
   zero near-limit) is within 10% of that peak. They are contiguous
   fine-grid points, so the plateau criterion is technically met —
   but at a width of exactly two grid points, 0.04 wide on the alpha
   axis.
3. **`α ≥ 0.22` — collapse.** PnL falls sharply and monotonically
   out of the region: 957 at `α=0.22` (-26% from peak), 417 at
   `α=0.25`, 468 at `α=0.28`, 273 at `α=0.30`, -129 at `α=0.40`, and
   essentially zero by `α=0.50`. `α=0.22` alone takes the
   configuration outside the 10% band, and `α=0.30` is already
   statistically indistinguishable from the incumbent.

**Plateau decision (explicit).** The fine grid confirms that there
is no hidden continuity the coarse grid was hiding: the "plateau"
really is two grid points wide, bordered on one side by
inventory-disqualified configurations (`α ≤ 0.16`) and on the other
by a sharp PnL collapse (`α ≥ 0.22`). The 10% rule is met on the
letter — `α=0.18` and `α=0.20` are contiguous and within 10% of the
peak — but the doctrine (`ARCHITECTURE_DOCTRINE.md` §8: "broad
parameter plateaus over peak settings") treats a 2-of-8 point region
surrounded by disqualification and collapse as a narrow peak, not a
plateau worth committing a live baseline to. Promotion rule 4 is
therefore marked **PASS** by the letter and flagged as the weakest
of the six checks in the final decision rationale.

## Stage 3 — challenger-vs-incumbent head-to-head

Two `BacktestSimulator` runs with identical execution parameters:

```
== INCUMBENT weighted_mid (edge=1/1, skew=3.0, flat=0.7) ==
  pnl:                 276.00
  trade_count:             16
  taker_q:                 83
  maker_q:                  5
  steps_near_limit:         0
  final_position:           6
  avg_entry_edge:    +0.683 (n=16)
  avg_markout_1:     +4.057 (n=16)
  avg_markout_5:     +3.625 (n=16)
  avg_markout_20:    +3.227 (n=16)

== CHALLENGER ewma_mid alpha=0.20 (same execution) ==
  pnl:                1301.00
  trade_count:            115
  taker_q:                825
  maker_q:                  2
  steps_near_limit:         0
  final_position:           7
  avg_entry_edge:    +1.002 (n=115)
  avg_markout_1:     +1.772 (n=115)
  avg_markout_5:     +1.856 (n=115)
  avg_markout_20:    +2.219 (n=115)
```

**Trade-count context is the critical read on this table.** The
challenger fires ~7× more trades than the incumbent (115 vs 16) and
moves ~9× more units (825 taker units vs 83 taker + 5 maker = 88
total). Every headline difference flows from that:

- **Total PnL: 1301 vs 276 (4.7×).** Expected when you take 9×
  more directional exposure at still-positive per-unit edge.
- **`avg_entry_edge`: +1.002 vs +0.683.** The challenger's selected
  fills sit further from its fair value *at decision time*, even
  with 7× more decisions. That is consistent with EWMA producing a
  laggier fair-value anchor that is further away from the market
  mid more often, not with the challenger being more selective.
- **`avg_markout_{1,5,20}`: `+1.77 / +1.86 / +2.22` vs
  `+4.06 / +3.63 / +3.23`.** Per-trade realized edge drops by
  roughly half. This is *not* a sign of bad trades — all three
  horizons stay firmly positive — but it is a sign that each
  individual EWMA fill extracts less realized alpha than each
  weighted_mid fill. Rough economic cross-check: incumbent total
  realized edge ≈ `16 × 3.6 ≈ 58`; challenger ≈ `115 × 1.86 ≈ 214`.
  The 4.7× total PnL comes from *volume × smaller-per-trade edge*,
  not from catching larger moves. On the tutorial sample this
  arithmetic works out, but it is a different trading style than
  the market-making doctrine Phase 5 was scoped against.
- **Maker share: 2 of 827 units (0.24%) vs 5 of 88 (5.7%).** The
  challenger is effectively pure-taker. Whatever maker quotes the
  execution engine posted were almost never filled, so any claim
  that EWMA "improves market making" on this replay is
  unsupported.

The challenger is a faster, more aggressive taker style that earns
more headline PnL by generating 7× the trade count at roughly half
the per-trade realized edge, with the same inventory discipline but
none of the maker-share profile the Phase 5 scope committed to.
That is a meaningful product-archetype shift, not a drop-in
upgrade.

## Stage 4 — timestamp divergence drilldown

Top divergence timestamps (per-step `|ewma_mid(α=0.20) − weighted_mid|`):

| timestamp | \|Δ\| | ewma | wm | mid |
|-----------|-------|------|------|------|
| 141800 | 1.695 | 4996.539 | 4998.233 | 5000.000 |
| 579700 | 1.657 | 4974.810 | 4976.467 | 4978.000 |
| 220800 | 1.633 | 4986.299 | 4984.667 | 4982.500 |
| 321500 | 1.614 | 4983.280 | 4981.667 | 4979.000 |
| 432400 | 1.592 | 4997.108 | 4998.700 | 5000.000 |

Drilldowns generated at both
`outputs/review_packs/20260411T185706Z_phase5_ewma/drilldowns/timestamp_TOMATOES_141800/`
and
`outputs/review_packs/20260411T185701Z_phase5_weighted/drilldowns/timestamp_TOMATOES_141800/`.

In the ±40-step window around `ts=141800`:

- **EWMA pack** executed three taker fills:
  1. `ts=140200` **buy 6 @ 4991** (EWMA fair 4992.74, mid 4988.5).
     Fair above mid → saw the ask as cheap, bought.
  2. `ts=140900` **buy 8 @ 5003** (EWMA fair 5005.09, mid 5000.5).
     Same pattern.
  3. `ts=141700` **sell 8 @ 4997** (EWMA fair 4995.67, mid 5000.0).
     Fair below mid → sold into the rally at bid.
- **Incumbent pack** executed zero fills in the same window.

The EWMA is using its smoothed anchor to fade short-term mid
dislocations that the four-sample `weighted_mid` collapses into
current-level noise. That is exactly the behaviour a dynamic fair
value should exhibit, and it is the structural reason the
challenger generates 7× the trade count (and therefore the 4.7×
total PnL) on the tutorial replay: it sees edge in stretches
where the incumbent sees none. What the drilldown does **not**
establish is that individual fades survive the markouts test —
that question is answered by Stage 3, where per-trade realized
markouts are roughly half the incumbent's. Whether the
trade-count advantage survives on a second replay is not
something this tutorial sample can answer.

## Promotion rule check

| # | Rule | Result | Evidence |
|---|------|--------|----------|
| 1 | `mae_n1` and `mae_n5` within 5% of best non-anchor estimator | **FAIL** | `ewma_mid α=0.20` `mae_n1=0.895` vs best `mid=0.790` (+13.3%); vs incumbent `0.815` (+9.8%). Only `mae_n5` (+3.4% vs incumbent) clears the 5% band. |
| 2 | Tuned PnL ≥ 115% of tuned incumbent | **PASS** | 1301 / 276 = 471% |
| 3 | Zero near-limit steps in Stage 3 challenger run | **PASS** | `steps_near_limit=0` at `α=0.20` |
| 4 | Plateau ≥ 2 contiguous grid points within 10% of peak | **PASS (weakest)** | `α=0.18` (1171) and `α=0.20` (1301) are contiguous and within 10%. Width is exactly 2 of 8 fine-grid points, bordered by inventory-disqualified configurations on one side and a sharp collapse (`α=0.22` → 957, -26%) on the other. Passes the letter; reads as a narrow peak under doctrine §8. |
| 5 | Stage 3 `markout_5` and `markout_20` ≥ incumbent | **FAIL** | `+1.856` vs `+3.625` and `+2.219` vs `+3.227`. Per-trade realized edge is roughly half the incumbent's; the 4.7× total PnL comes from 7× the trade count (115 vs 16) at smaller per-unit edges, not from better decisions per trade. |
| 6 | Drilldown does not show adverse systematic pattern | **PASS** | `ts=141800` window shows EWMA fading dislocations back toward a smoothed anchor; aggregate markouts remain positive at all three horizons. |

Two clear failures (rules 1 and 5), one weakest-pass (rule 4), three
clean passes (rules 2, 3, 6). The plateau is technically contiguous
but only 2 of 8 fine-grid points wide, and doctrine §8 explicitly
prefers broad plateaus to peak settings.

## Decision

**Dynamic TOMATOES challenger implemented and evaluated; incumbent
baseline retained.**

`default_engine_config()` is unchanged: TOMATOES still points at
`weighted_mid` with the Phase 3 tuned execution parameters. No
EMERALDS changes, no execution-layer changes, no strategy-logic
changes.

`ewma_mid` is shipped in-engine as a registered, tested,
plateau-swept estimator. The Phase 5 evaluation infrastructure
(Stage 1 comparison flag, `run_phase5_ewma_sweep.py`, paired review
packs, timestamp drilldowns) is archived and reusable — a Phase 6
robustness pass or a future round can re-run exactly the same four
stages against a second day's replay without rewriting any code.

This is the same discipline Phase 3 used to keep `depth_mid` out of
the baseline despite it tracking price better: the challenger was
considered on a full rule set, failed the inventory / decision /
plateau combination, and was preserved as a candidate for a later
round rather than deleted.

## Reproduce this Phase

Given this working tree at commit `<phase5 commit hash>`:

```
# Unit tests
PYTHONPATH=. pytest tests/test_fair_value.py tests/test_config.py -q
PYTHONPATH=. pytest -q

# Stage 1: fit + replay head-to-head
PYTHONPATH=. python -m src.scripts.compare_fair_values \
  --label phase5_stage1 \
  --estimators mid,rolling_mid,weighted_mid,ewma_mid

# Stage 2: alpha plateau (coarse and fine)
PYTHONPATH=. python -m src.scripts.run_phase5_ewma_sweep \
  --label phase5_tomatoes_alpha --grid coarse
PYTHONPATH=. python -m src.scripts.run_phase5_ewma_sweep \
  --label phase5_tomatoes_alpha_fine --grid fine

# Stage 3: head-to-head via ad-hoc Python (see the run captured in
# this note). The challenger is not yet a default config, so the
# head-to-head uses dataclasses.replace() to build a one-off
# EngineConfig with ewma_mid.

# Stage 4: review packs + timestamp drilldowns
# Both packs are produced via an ad-hoc Python call that pairs
# default_engine_config() (incumbent) with a replaced TOMATOES
# product_config (challenger).
PYTHONPATH=. python -m src.scripts.run_drilldown \
  --pack outputs/review_packs/<run_id> \
  --timestamp 141800 --product TOMATOES --window 40
```

## Status vs plan

- Phase 1: complete
- Phase 2: complete
- Phase 3: complete
- Phase 4a: complete
- Phase 4b: complete
- **Phase 5: complete — dynamic TOMATOES challenger (`ewma_mid`)
  implemented and evaluated via the four-stage workflow; incumbent
  `weighted_mid` baseline retained; note and paired review packs
  archived.**
- Phase 6 (robustness sweeps): not started.
- Phase 7 (signal scanner): not started.
- Phase 8 (residual capacity): not started.
- Phase 9 (submission hardening): partially shipped per prior notes.
- Phase 10 (docs + round readiness): not started.
