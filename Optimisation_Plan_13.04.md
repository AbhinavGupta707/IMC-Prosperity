# Optimization Pass 1: Master Plan (Final — 13 April 2026)

## Context

Position limits migrated from 20 to 80 with proportional skew scaling (EMERALDS: 2.0->8.0, TOMATOES: 3.0->12.0). Baseline behavior preserved. This pass audits inventory behavior at the new scale, adds wall-based fair-value estimators, runs disciplined sweeps, and promotes at most one combined config if it passes all gates.

**Branch:** `optim-pass-1` (from `codex-phase1-6-cleanup`)

---

## Phase 0 — Baseline Snapshot

**Goal:** Capture current performance as immutable reference.

### Steps

1. Create branch `optim-pass-1` from current HEAD
2. Create `outputs/optim_pass_1_run_manifest.md` — the living reproducibility record. Initialize with branch name, dataset files, and baseline command.
3. Run:
   ```bash
   PYTHONPATH=. python -m src.scripts.run_review --label baseline_optim_pass_1 --no-charts
   ```
4. Extract from output into `outputs/optim_pass_1_baseline.md`:
   - Total PnL, per-product PnL
   - Trade counts (total, maker, taker per product)
   - Final positions per product
   - Steps near limit per product
   - Entry edge and markouts (+1/+5/+20) per product
5. Commit the baseline markdown summary only (not the full review pack directory)

**Files committed:** `outputs/optim_pass_1_baseline.md`

**Acceptance:** Baseline numbers captured. Review pack generated for reference but not committed.

---

## Phase 1 — Legality + Inventory Behavior Tests

**Goal:** Verify arithmetic legality and establish test coverage for inventory-related behavior at limit=80, for both long and short positions. Economic sensibility is NOT concluded here — that is Phase 1.5's job.

### What Phase 1 proves

- **Legality:** Worst-case order sets (taker + maker combined) never exceed remaining capacity at any position level, for both buy and sell sides. Risk clipping catches any overflow.
- **Mechanical correctness:** Skew shifts prices in the right direction for long positions AND reverses correctly for short positions. Flatten threshold triggers recovery mode at the configured ratio on the correct side.

### What Phase 1 does NOT prove

- Whether the economic behavior is sensible at high inventory (that's Phase 1.5)
- Whether flattening activates early enough to avoid dangerous positions in practice
- Whether the inventory skew values (8.0, 12.0) are economically optimal

### Steps

1. Add tests in `tests/test_signals.py` for limit=80 with current EMERALDS params (skew=8.0, flatten=0.75):
   - **Long positions:** 0, 10, 20, 40, 56, 60 (at flatten), 70, 78
   - **Short positions:** -78, -70, -60, -56, -40, -20, -10
   - Assert for long: skew direction correct, flatten triggers at 60+, bid_size=0 and buy_below=None when flattening long, ask pulled toward fair value
   - Assert for short: skew reverses (negative skew -> buy thresholds move UP, sell thresholds move UP), flatten at -60 triggers ask_size=0 and sell_above=None, bid pulled toward fair value
   - **Symmetry check:** For each |position|, verify that the long and short intents are mirror images (mode, suppressed side, active side direction)
   - Same structure for TOMATOES params (skew=12.0, flatten=0.70) at corresponding positions

2. Add tests in `tests/test_risk.py` for worst-case legality at limit=80, both sides:
   - **Long boundary:** At position 65, max buy order set (taker 10 + maker 5 = 15) <= buy capacity (15). Exact boundary.
   - At position 66: buy capacity = 14, verify clipping reduces total buy orders to 14
   - At position 78: buy capacity = 2, verify only 2 units of buy orders survive
   - **Short boundary:** At position -65, max sell order set <= sell capacity (15). Exact boundary.
   - At position -66: sell capacity = 14, verify clipping reduces total sell orders to 14
   - At position -78: sell capacity = 2, verify only 2 units of sell orders survive

3. Run: `PYTHONPATH=. pytest tests/test_signals.py tests/test_risk.py -v`

**Files modified:**
- `tests/test_signals.py` — ~12-16 new tests (long + short + symmetry)
- `tests/test_risk.py` — ~6-8 new tests (long + short boundaries)

**Acceptance:** All tests pass. Legality verified for both long and short. Symmetry confirmed. No claims about economic optimality made.

---

## Phase 1.5 — Synthetic High-Inventory Stress Pass

**Goal:** Verify that the bot's behavior is economically sensible — not just mechanically legal — at elevated inventory positions, for both long and short.

### Motivation

Unit tests confirm the arithmetic. But we need to inspect how the full strategy pipeline responds when starting from high inventory. Does the bot recover efficiently? Does it quote in the correct direction? Is there a dead zone between 20 and 80 where recovery never activates until too late?

### Design

Write a targeted diagnostic test (or small script) that:

1. For each product (EMERALDS, TOMATOES), for each starting position in **[-78, -70, -56, -40, -20, -10, 0, 10, 20, 40, 56, 70, 78]**:
   - Construct a `NormalizedSnapshot` with realistic book data
   - Construct a `ProductMemory` with reasonable history
   - Run `SignalEngine.build_market_making_intent()` to get intent
   - Run `ExecutionEngine.generate_orders()` to get raw orders
   - Run `RiskManager.clip_orders()` to get final orders
   - Record: intent mode, buy/sell thresholds, bid/ask prices and sizes, number of orders per side, total clipped quantity per side

2. For the full pipeline output at each position, verify:
   - **Skew direction:** As position increases (long), buy prices/thresholds decrease and sell thresholds decrease (more permissive for sells, less for buys). As position decreases (short), the reverse.
   - **Skew symmetry:** Behavior at position +N mirrors behavior at position -N on the opposite side.
   - **Monotonicity:** The shift is monotonic across the position range in both directions.
   - **Recovery activation:** At `|position| >= flatten_threshold * limit`, the same-direction (risk-increasing) side is fully suppressed.
   - **Recovery aggressiveness:** The unwind-direction quote in recovery mode is at or inside fair value (actively seeking unwind, not passively waiting).
   - **No dead zone:** There is no gap between the highest non-flattening position and the flattening threshold where the bot is neither effectively skewing nor recovering.
   - **Same-direction suppression under load:** When deeply loaded, the strategy suppresses or reduces same-direction re-entry, not just via risk clipping but via intent-level suppression. The dangerous side does not consume unnecessary capacity.
   - **Unwind direction fully usable:** The unwind direction remains fully usable and sufficiently aggressive. The strategy is not mechanically legal but economically passive in the wrong place (e.g., quoting the unwind side too wide under stress).

3. Produce a simple table (in test output or saved markdown) showing the intent/orders at each position level.

### Implementation

This is a parametric unit test, not a new research engine. Implementation options:

- **Preferred:** `@pytest.mark.parametrize` over the full position set in `tests/test_signals.py`, asserting the behavioral properties above
- **Alternative:** A small diagnostic script that prints the table for manual inspection, plus the parametric test for CI

### Assumption to verify

The inventory skew values (8.0 for EMERALDS, 12.0 for TOMATOES) were chosen to preserve old-limit behavior. At the new limit of 80, these may cause excessive price concessions at moderate positions (e.g., position 40 = 50% utilization already creates skew of 4.0 ticks). Phase 1.5 will surface whether this is a real problem.

**Files modified:**
- `tests/test_signals.py` — add parametric stress tests (~40-50 lines)
- Optionally: `outputs/optim_pass_1_stress_table.md` — diagnostic table (not committed to git)

**Acceptance:**
- All behavioral properties verified across the full position range (long and short)
- Symmetry confirmed
- No dead zones identified
- If excessive skew at moderate positions is found, document it as input to Phase 4/5 sweep design but do NOT fix it here (fixing is a parameter change, not a bug fix)

---

## Phase 2 — New Fair-Value Estimators

**Goal:** Implement `wall_mid`, `filtered_wall_mid`, and `hybrid_wall_micro`.

### Design

**Key files:**
- `src/core/fair_value.py` — add 3 classes, register in `ESTIMATORS`
- `src/core/config.py` — add names to `KNOWN_ESTIMATOR_NAMES`
- `tests/test_fair_value.py` — unit tests

#### 2a. `WallMidEstimator` (`wall_mid`)

Logic:
- Find the bid level with the largest visible volume across all bid levels
- Find the ask level with the largest visible volume across all ask levels
- Fair value = midpoint of those two prices
- Return None if either side is empty
- Components: `wall_bid_price`, `wall_ask_price`, `wall_bid_vol`, `wall_ask_vol`
- Confidence: 0.75 (same as `depth_mid`)

#### 2b. `FilteredWallMidEstimator` (`filtered_wall_mid`)

Logic:
- Consider only the top N visible levels on each side (N=3, matching typical Prosperity book depth)
- Filter out levels with volume < `max_volume_on_side * 0.25` (25% of the side's largest level). This adapts to the book's scale rather than using an arbitrary hardcoded threshold.
- Among surviving levels, pick the largest volume. Break ties by closeness to touch.
- If no levels survive the filter on either side, return None (fall through to next estimator)
- Components: `wall_bid_price`, `wall_ask_price`, `filtered_out_count`
- Confidence: 0.75

The 25% threshold is simple, interpretable, and adapts: a book with max_vol=20 filters out levels < 5; a book with max_vol=4 filters out levels < 1 (only truly empty levels).

#### 2c. `HybridWallMicroEstimator` (`hybrid_wall_micro`)

Logic:
- Compute `wall_mid` estimate and `microprice` estimate
- If both available: blend as `wall_weight * wall_mid + (1 - wall_weight) * microprice`
- If only one available: return that one (re-labeled with this estimator's name)
- If neither available: return None
- `wall_weight` default: 0.5. This is a class attribute, making it easy to override in subclasses or sweep configs if shortlisted later.
- Components: `wall_mid_price`, `microprice`, `wall_weight`
- Confidence: 0.75

**Note:** The `wall_weight` may be swept in Phase 5, but ONLY if `hybrid_wall_micro` is shortlisted in Phase 3. Do not prematurely build sweeping infrastructure for it.

#### Confidence values

The repo's confidence field is carried through `FairValueEstimate` but is not used downstream in any decision logic (signals.py reads `.price` and `.method`, not `.confidence`). Use 0.75 for all three new estimators. If confidence becomes decision-relevant in the future, these can be tuned then.

### Tests

Add to `tests/test_fair_value.py`:
- `wall_mid`: symmetric book (wall_mid = mid), asymmetric book (different), single level per side, empty side returns None
- `filtered_wall_mid`: filters out small levels, returns None when all filtered, correct tie-breaking by proximity to touch
- `hybrid_wall_micro`: correct blend math, fallback to single component, None when both missing
- All three: registered in `ESTIMATORS`, returned by `estimate_all()`

**Files modified:**
- `src/core/fair_value.py` — add 3 classes (~80 lines total), update `ESTIMATORS`
- `src/core/config.py` — add 3 names to `KNOWN_ESTIMATOR_NAMES`
- `tests/test_fair_value.py` — ~10 new tests

**Acceptance:** All new and existing tests pass. `FairValueEngine().estimate_all()` returns the new estimators.

---

## Phase 3 — TOMATOES Fair-Value Comparison + Coverage/Distinctness

**Goal:** Rank all estimators by trading performance with diagnostic context for TOMATOES.

### Estimators to compare (9 total for TOMATOES, which has no anchor):

`mid`, `rolling_mid`, `weighted_mid` (current primary), `ewma_mid`, `depth_mid`, `microprice`, `wall_mid`, `filtered_wall_mid`, `hybrid_wall_micro`

### Steps

1. Create `src/scripts/run_fair_value_compare.py` — a minimal runner that:
   - Calls `build_fair_value_report()` from `src/backtest/fair_value_compare.py`
   - Passes an explicit estimator list (does NOT mutate `DEFAULT_COMPARISON_ESTIMATORS`)
   - Calls `write_fair_value_report()` to persist results
2. The existing `build_fair_value_report()` already produces per-estimator: PnL, trade count, maker share, current/next-mid MAE, steps near limit
3. **Add coverage/distinctness diagnostics** to the comparison output. Extend `EstimatorComparison` dataclass or add post-processing in the runner:

   **Additional metrics per estimator:**
   - **Coverage:** % of timestamps where estimator produced a non-None value (already tracked)
   - **Mean absolute difference vs current primary** (`weighted_mid`): How different is this estimator from what we already use?
   - **Mean absolute difference vs plain `mid`:** Is this estimator just a noisy copy of mid?
   - **Value-change frequency:** Fraction of consecutive timestamps where the estimator's output changed by > 0. Higher = more responsive.

4. Run:
   ```bash
   PYTHONPATH=. python -m src.scripts.run_fair_value_compare --label optim_tomatoes_fv
   ```
5. Save comparison table and diagnostics to `outputs/fair_value_comparison/`

### Shortlisting criteria

**Hard gate (automatic exclusion):**
- Coverage < 90% — unreliable as primary, auto-excluded

**Ranking criteria (used for ordering, not automatic exclusion):**
- PnL vs baseline (primary ranking signal)
- Markout quality (+1, +5, +20)
- Entry edge

**Interpretation diagnostics (inform judgment, NOT hard gates):**
- Mean difference vs `mid` — if very small, the estimator is essentially a copy of mid and unlikely to add value, but this is a warning, not an auto-reject
- Mean difference vs current primary (`weighted_mid`) — if very small, switching to it gains nothing
- Value-change frequency — if very low compared to other estimators, it may be stale/unresponsive, but this is a diagnostic signal, not a rigid cutoff

Select top 3 by PnL among those passing the coverage gate. Annotate each with the diagnostic metrics for human review. If fewer than 3 pass coverage, note which estimators failed and why.

**Files modified:**
- `src/scripts/run_fair_value_compare.py` — new runner (~50 lines)
- `src/backtest/fair_value_compare.py` — add distinctness metrics to `EstimatorComparison` or to `_compare_estimator()` output (small extension, ~20 lines)

**Assumption to verify:** Tutorial book depth may be thin (2-3 levels). Wall-based estimators may collapse to regular mid on thin books. The coverage/distinctness diagnostics will catch this.

**Acceptance:** Comparison table produced with both performance and diagnostic metrics. Top 3 shortlisted with explicit criteria. No promotion.

---

## Phase 4 — EMERALDS Staged Sweep

**Goal:** Diagnose why EMERALDS has weak/zero fills and find better settings through a two-stage sweep.

### Stage A — Quote Competitiveness

**Question:** Are EMERALDS quotes too wide to get filled?

Sweep only:
```python
STAGE_A_GRID = {
    "maker_edge": [0.5, 1.0, 2.0, 3.0, 4.0],  # current=2.0
    "taker_edge": [0.5, 1.0, 1.5, 2.0],          # current=1.0
}
# 5 * 4 = 20 configs
```

Hold `inventory_skew=8.0` and `flatten_threshold=0.75` fixed.

Run via `build_parameter_sweep_report()`.

**Stage A ranking:** Rank by a composite of:
- PnL (primary)
- Trade count (secondary — more fills is good, but not if quality is bad)
- **Average entry edge or markout quality** — a config that trades more but with negative markouts is worse than one that trades less with positive markouts. Do not reward trade volume alone.

Select the top 3-5 Stage A configs.

### Stage B — Inventory/Recovery Refinement

Only on Stage A's top 3-5 configs, sweep:
```python
STAGE_B_GRID = {
    "flatten_threshold": [0.65, 0.70, 0.75, 0.80],
    "inventory_skew": [4.0, 6.0, 8.0, 10.0],
}
# 4 * 4 = 16 configs per Stage A candidate
# 3-5 candidates * 16 = 48-80 total
```

**Output:** Ranked EMERALDS sweep table. Top 3 candidate configs.

### Implementation

To include entry-edge / markout quality in Stage A ranking, extend `SweepRow` or add a richer `_simulate_row()` that captures `avg_entry_edge` from the `ProductResult`. If this requires a small extension to `parameter_sweep.py`, keep it minimal.

Create `src/scripts/run_emeralds_sweep.py` (~70 lines) that:
1. Runs Stage A sweep
2. Ranks by (PnL, entry_edge, trade_count) composite
3. Selects top N candidates from Stage A (configurable, default 3)
4. For each Stage A winner, runs Stage B sweep
5. Merges results and ranks

**Files modified:**
- `src/scripts/run_emeralds_sweep.py` — new staged sweep runner
- `src/backtest/parameter_sweep.py` — small extension to capture entry edge in `SweepRow` (if not already present)

**Acceptance:** Sweep table produced. Top 3 EMERALDS candidates identified with interpretable parameter differences. Diagnosis of whether EMERALDS is dead due to wide quotes, conservative taking, or inherent market structure.

---

## Phase 5 — TOMATOES Estimator-Aware Sweep

**Goal:** Test Phase 3's top 3 estimators with parameters that actually affect each estimator.

### Estimator-aware grid design

For each shortlisted estimator, sweep only the parameters that matter:

**If estimator is `rolling_mid`, `weighted_mid`, or `ewma_mid`** (history-dependent):
```python
HISTORY_GRID = {
    "maker_edge": [0.5, 1.0, 1.5, 2.0],
    "taker_edge": [0.5, 1.0, 1.5],
    "history_length": [16, 32, 48, 64],
}
# 4 * 3 * 4 = 48 configs per estimator
```

**If estimator is `wall_mid` or `filtered_wall_mid`** (no history dependency):
```python
WALL_GRID = {
    "maker_edge": [0.5, 1.0, 1.5, 2.0],
    "taker_edge": [0.5, 1.0, 1.5],
}
# 4 * 3 = 12 configs per estimator
# (history_length is irrelevant for wall-based estimators)
```

**If estimator is `hybrid_wall_micro`** (blend-dependent):
```python
HYBRID_GRID = {
    "maker_edge": [0.5, 1.0, 1.5, 2.0],
    "taker_edge": [0.5, 1.0, 1.5],
}
# 4 * 3 = 12 configs
# wall_weight sweep deferred unless hybrid_wall_micro is clearly the winner
```

**If estimator is `microprice` or `depth_mid`** (stateless):
```python
STATELESS_GRID = {
    "maker_edge": [0.5, 1.0, 1.5, 2.0],
    "taker_edge": [0.5, 1.0, 1.5],
}
# 4 * 3 = 12 configs per estimator
```

Total: 12-48 per estimator, 3 estimators = 36-144 total runs.

Do not sweep parameters for an estimator if they do not meaningfully affect that estimator.

### Implementation

Create `src/scripts/run_tomatoes_fv_sweep.py` (~80 lines) that:
1. Takes the Phase 3 shortlist (hardcoded or passed as args)
2. For each estimator, selects the appropriate grid based on estimator type
3. Creates a modified `ProductConfig` with that estimator as primary
4. Runs `build_parameter_sweep_report()` with the appropriate grid
5. Merges cross-estimator results into a single ranked table

**Files modified:**
- `src/scripts/run_tomatoes_fv_sweep.py` — new estimator-aware sweep runner

**Acceptance:** Ranked TOMATOES sweep table. Top 3 candidates identified (estimator + params).

---

## Phase 6 — Product-Level Shortlists

**Goal:** Consolidate Phase 4 and Phase 5 outputs into clean per-product shortlists.

### Steps

1. From Phase 4: select top 3 EMERALDS configs (or fewer if only 1-2 are clearly better than baseline)
2. From Phase 5: select top 3 TOMATOES configs
3. For each shortlisted config, record:
   - Product PnL vs baseline delta
   - Trade count vs baseline delta
   - Steps near limit
   - Final position
   - Maker/taker split
   - Entry edge and markout quality
   - Key parameter differences from baseline
4. Write to `outputs/optim_pass_1_shortlists.md`

**Acceptance:** Clean shortlist tables for both products. Each candidate has a clear 1-sentence economic rationale (e.g., "tighter maker_edge produces more fills without adverse selection").

---

## Phase 6.5 — Combined Finalist Pairings

**Goal:** The real deployment unit is a combined `EngineConfig` with settings for both products. Test the best pairings.

### Steps

1. Take top 2-3 EMERALDS candidates from Phase 6
2. Take top 2-3 TOMATOES candidates from Phase 6
3. Form combined pairings: up to 3x3 = 9 pairs (or fewer if shortlists are smaller)
4. For each pairing, build a full `EngineConfig` with both product configs and run a complete backtest via `BacktestSimulator`
5. Rank by total PnL, filtered by:
   - No legality violations
   - Reasonable total steps near limit (< 2x baseline total)
   - **Product-level regression tolerance:** No product worse than its own baseline by more than `max(20% of abs(product baseline PnL), fixed absolute tolerance)`, unless the total combined improvement is at least 2x the single-product regression AND the regression has a clear economic explanation. The fixed absolute tolerance exists so products with tiny, zero, or negative baseline PnL do not create pathological pass/fail logic. The exact fixed tolerance should be set before execution based on the baseline numbers observed in Phase 0.
6. Select top 3 combined configs for deep review

### Implementation

Create `src/scripts/run_combined_finalists.py` (~60 lines) that builds combined configs and runs backtests.

**Files modified:**
- `src/scripts/run_combined_finalists.py` — new combined pairing runner

**Acceptance:** Top 3 combined configs identified. Each has total PnL and per-product breakdown vs baseline.

---

## Phase 7 — Review Packs for Best Combined Configs

**Goal:** Generate detailed review artifacts for the top 3 combined finalists.

### Steps

1. For each of the top 3 combined configs:
   - Run full backtest via `BacktestSimulator` with the combined `EngineConfig`
   - Generate review pack via `write_review_pack()` WITH charts
   - Review pack includes: price vs fair value, trades on chart, positions over time, cumulative PnL, markout histograms

2. Write interpretation notes in `outputs/optim_pass_1_review_notes.md` for each finalist:
   - What improved vs baseline (per product and total)
   - What got worse
   - Whether gains come from real edge (positive markouts) or just more risk/inventory
   - Any suspicious timestamps or behavior clusters
   - Cross-product interaction effects (does improving one hurt the other?)

### Implementation

Create `src/scripts/run_candidate_review.py` (~80 lines) that takes candidate config parameters and generates a labeled review pack.

**Files modified:**
- `src/scripts/run_candidate_review.py` — new review runner
- `outputs/optim_pass_1_review_notes.md` — interpretation notes (committed)

**Acceptance:** 3 review packs generated. Interpretation notes written. Review packs NOT committed to git (too bulky); only interpretation notes committed.

---

## Phase 8 — Promotion Gate with Cross-Slice Robustness

**Goal:** Decide which combined config to promote, with explicit criteria.

### Promotion criteria (ALL must pass):

1. **Improved PnL:** Total PnL improved vs baseline
2. **No legality issues:** Verified by Phase 1/1.5 tests
3. **No inventory pathology:** Final position reasonable (<50% of limit), time near limit not excessive (< 2x baseline)
4. **Understandable economic reason:** The improvement has a clear explanation (e.g., "tighter quotes captured more spread" or "better FV estimate reduced adverse selection")
5. **Cross-slice robustness:** If the tutorial data has multiple days/slices:
   - Improvement should be present in at least 2 of the available slices
   - No catastrophic degradation in any single slice (product PnL in any slice should not be worse than baseline by more than 50%)
   - Gains should not be concentrated in a single narrow time window
6. **No obvious overfit:** If a top parameter sits at a grid boundary, treat it as a **warning flag** — interpret cautiously and consider whether the grid should be expanded in a future pass. A boundary winner is NOT an automatic promotion failure on its own, but it should be noted in the promotion notes and weighed alongside other evidence.

For this pass, robustness is evaluated through the explicit cross-slice checks above rather than an undefined variance measure. A future pass may add formal statistical robustness metrics if cross-day data is sufficient.

### Steps

1. For the top finalist from Phase 6.5, run the full promotion checklist
2. If it passes all 6 criteria, promote it by updating `default_engine_config()` in `src/core/config.py`
3. If it fails any criterion, document why and either:
   - Try the next finalist
   - Leave config unchanged and document what was tried

### Cross-slice testing

If the tutorial data has `day_-2` and `day_-1` files:
- Run the finalist config on each day separately (using `filter_replay_to_product()` or per-day file loading)
- Compare per-day results against baseline per-day results
- Reject if any day shows >50% PnL regression for either product

**Files modified:**
- `src/core/config.py` — update `default_engine_config()` ONLY if gate passes
- `outputs/optim_pass_1_promotion.md` — promotion decision, criteria results, reasoning

**Acceptance:** At most one combined config promoted. Clear documentation of pass/fail for each criterion. If no config promoted, explicit statement of why and recommended next steps.

---

## Phase 9 — Commit Hygiene and Final Summary

### Commit plan

Separate logical commits, in order:

| # | Type | Message | Files |
|---|------|---------|-------|
| 1 | chore | `chore: baseline metrics for optimization pass 1` | `outputs/optim_pass_1_baseline.md` |
| 2 | test | `test: inventory legality and behavior tests at limit=80 (long+short)` | `tests/test_signals.py`, `tests/test_risk.py` |
| 3 | test | `test: synthetic high-inventory stress verification (long+short)` | `tests/test_signals.py` |
| 4 | feat | `feat: add wall_mid, filtered_wall_mid, hybrid_wall_micro estimators` | `src/core/fair_value.py`, `src/core/config.py`, `tests/test_fair_value.py` |
| 5 | chore | `chore: fair-value comparison and sweep scripts` | `src/scripts/run_fair_value_compare.py`, `src/scripts/run_emeralds_sweep.py`, `src/scripts/run_tomatoes_fv_sweep.py`, `src/scripts/run_combined_finalists.py`, `src/scripts/run_candidate_review.py`, `src/backtest/parameter_sweep.py` (if extended), `src/backtest/fair_value_compare.py` |
| 6 | chore | `chore: optimization pass 1 shortlists, review notes, and run manifest` | `outputs/optim_pass_1_shortlists.md`, `outputs/optim_pass_1_review_notes.md`, `outputs/optim_pass_1_run_manifest.md` (living record, created in Phase 0, committed here with accumulated history) |
| 7 | feat | `feat: promote optimized config from pass 1` (if applicable) | `src/core/config.py` |
| 8 | chore | `chore: optimization pass 1 promotion decision` | `outputs/optim_pass_1_promotion.md` |

### What NOT to commit

- Full review pack directories (`outputs/review_packs/*/`) — too bulky
- Full sweep output directories (`outputs/sweeps/*/`, `outputs/fair_value_comparison/*/`) — too bulky
- Chart PNGs — ephemeral, regenerated on demand

These remain on disk for reference during the session but stay outside git.

### Reproducibility artifact

Create `outputs/optim_pass_1_run_manifest.md` at the start of the pass (Phase 0) and update it throughout execution. It is a living reproducibility record, not a late afterthought.

It should record:

- Branch name
- Relevant commit hashes (updated as commits are made)
- Exact commands run for each phase (copy-pasteable)
- Labels and output directory paths used
- Dataset files used (glob patterns and file count)
- Config diffs from baseline for shortlisted and finalist runs
- Phase 3 shortlist rationale (which estimators, why)
- Phase 6 shortlist rationale
- Phase 6.5 combined finalist pairings tested

This file is lightweight (markdown, no binary data). It should be committed once it contains meaningful run history, alongside the shortlist/review-notes commit (commit #6), then updated further if promotion occurs (commit #7/#8).

### Final summary deliverable

At completion, produce `outputs/optim_pass_1_promotion.md` containing:

1. **Executive summary** (3-5 sentences)
2. **Exact changes made** (files, line ranges)
3. **Metrics table: before/after** (total PnL, per-product PnL, trade counts, markouts)
4. **Rejected alternatives** (what was tried and why it didn't pass the gate)
5. **Remaining risks** (what we're uncertain about)
6. **Recommended next move** (highest-ROI task for pass 2)
7. **Branch name and commit hashes**

---

## Execution Dependencies

```
Phase 0  (baseline)
  |
Phase 1  (legality tests -- long + short)
  |
Phase 1.5  (stress tests -- long + short)
  |
Phase 2  (new estimators)
  |
  +---> Phase 3 (TOMATOES FV comparison)    Phase 4 (EMERALDS staged sweep)
  |           |                                      |
  |     Phase 5 (TOMATOES estimator sweep)           |
  |           |                                      |
  +---> Phase 6 (product-level shortlists) <---------+
              |
        Phase 6.5 (combined finalist pairings)
              |
        Phase 7 (review packs)
              |
        Phase 8 (promotion gate)
              |
        Phase 9 (commit hygiene + summary)
```

Phase 3 and Phase 4 are independent and could run in parallel.

---

## Unproven Assumptions

1. **Tutorial book depth:** Wall-based estimators assume visible walls. If tutorial books are 2-3 levels thin, wall_mid may collapse to regular mid. Phase 3 diagnostics will catch this.
2. **Inventory skew magnitude:** 8.0 and 12.0 may cause excessive price concessions at moderate positions. Phase 1.5 will surface this; Phases 4/5 can adjust.
3. **Tutorial data representativeness:** All sweeps optimize against one sample. Cross-slice checks in Phase 8 partially mitigate but cannot eliminate this risk.
4. **EMERALDS fill availability:** EMERALDS may have zero-fill outcomes regardless of settings if the tutorial trade tape simply doesn't interact with our quotes. Phase 4 Stage A will reveal this quickly.

---

## File Summary

| File | Phase | Action |
|------|-------|--------|
| `tests/test_signals.py` | 1, 1.5 | Add limit=80 boundary + stress tests (long + short) |
| `tests/test_risk.py` | 1 | Add worst-case legality tests (long + short) |
| `src/core/fair_value.py` | 2 | Add 3 new estimator classes |
| `src/core/config.py` | 2, 8 | Add estimator names; update defaults if promoted |
| `tests/test_fair_value.py` | 2 | Add tests for new estimators |
| `src/backtest/fair_value_compare.py` | 3 | Add distinctness metrics (small extension) |
| `src/backtest/parameter_sweep.py` | 4 | Extend SweepRow with entry edge (if needed) |
| `src/scripts/run_fair_value_compare.py` | 3 | New: FV comparison runner |
| `src/scripts/run_emeralds_sweep.py` | 4 | New: staged EMERALDS sweep |
| `src/scripts/run_tomatoes_fv_sweep.py` | 5 | New: estimator-aware TOMATOES sweep |
| `src/scripts/run_combined_finalists.py` | 6.5 | New: combined pairing runner |
| `src/scripts/run_candidate_review.py` | 7 | New: review pack generator |
| `outputs/optim_pass_1_baseline.md` | 0 | Baseline metrics |
| `outputs/optim_pass_1_shortlists.md` | 6 | Per-product shortlists |
| `outputs/optim_pass_1_review_notes.md` | 7 | Interpretation notes |
| `outputs/optim_pass_1_run_manifest.md` | 0 (created), all (updated), 6+ (committed) | Living reproducibility manifest |
| `outputs/optim_pass_1_promotion.md` | 8, 9 | Promotion decision + final summary |
