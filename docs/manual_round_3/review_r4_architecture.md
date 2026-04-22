# R3+ Engine Architecture Review

**Branch:** `round3-engine`
**Scope:** Audit of the 10-defect closure claims, the 12 primitives, the 4 engines, and integration readiness.
**Date:** 2026-04-22
**Verdict up front:** The primitive/engine layer is well-written and tested (109 passing tests), but **nothing is wired to production**. `src/trader.py` still runs the old per-product dispatch loop with the old `RiskManager`, the old `FairValueEngine`, the old `ResidualAllocator`, the old silent-swallow `try/except`, and no `PortfolioSnapshot` / `SignalBus` / engines at all. The architecture doc describes a house; the repo has built the bricks and left them stacked in the yard. Most defect-closure claims are half-true: the PRIMITIVE exists and passes its tests, but the RUNTIME CHAIN still has the original defect.

---

## 1. Defect-by-defect closure status

| # | Defect | Primitive built? | Wired into `trader.py`? | Actually closes defect? | Severity of remaining gap |
|---|---|---|---|---|---|
| D1 | Backtest fill miscalibrated | `FillCalibrationHarness` — yes | No calibration has been RUN. `BacktestSimulator` still uses `FillModelConfig(passive_allocation=0.3)` default. | **No.** The harness is machinery for the calibration; the calibration itself is undone. Zero reference datapoints have been processed. | **Critical.** Any sweep done before calibrating ships a biased winner, exactly like R2. |
| D2 | FV estimators all reactive | `PredictiveEstimator` — yes | Not registered in `FairValueEngine.ESTIMATORS`. No `ProductConfig` references it. | **No.** Every strategy still pulls from the 12 reactive estimators. | **Medium** — only matters once we actually have a validated signal worth injecting (basket z, IV residual). Pre-R3 dormant. |
| D3 | Per-product context | `PortfolioSnapshot` — yes | **Never constructed.** `trader._run_body` calls `strategy.generate_intent(StrategyContext(...))` with no `portfolio` field anywhere. `StrategyContext` class in `src/strategies/base.py` has never been extended to carry one. | **No.** Basket-arb engines can be instantiated but cannot be called — there's no call site. | **Critical for R3 if baskets drop.** |
| D4 | Signals observational | `SignalBus` — yes | `FlowAnalyzer` still used in observational mode only (trader.py:171: `flow_report = self.flow_analyzer.scan(...)` → logged, never consumed). No emitter publishes to the bus. No consumer reads from it. | **No.** `FlowAnalyzer` promotion listed in Phase 2 is not done. | **Medium** — matters when a real signal is wired. |
| D5 | Residual off by default | `PortfolioRiskManager.residual_allowed(tag)` — yes | `trader._step_product` still calls the legacy `self.residual_allocator.augment_orders(...)` with the **global** `ResidualConfig`. `PortfolioRiskManager` is never instantiated in production. | **No.** The `residual_default_on_for_arb=True` flag flips nothing because no product is tagged `arb` through the production path. | **Medium** — arb strategies aren't trading yet. Will bite on R3. |
| D6 | Sweep picks noise | `SweepSelector` — yes | Not called from any script in `src/scripts/`. The existing `run_parameter_sweep.py`, `plateau.py`, `sweep.py` still use the old plateau-chart selection. | **No.** The next sweep we run will again pick plateaus, not significance-gated winners. | **Critical** — if we do any R3 prep sweep, we'll ship noise again. |
| D7 | Missing strategy classes | BSM, smile, conversion layer — yes; engines — yes | No engine is registered anywhere `trader.py` can reach. `src/strategies/__init__.py`'s `STRATEGY_REGISTRY` doesn't list them. | Partially. Classes exist and are unit-tested but cannot be dispatched. | **Critical for R3** — if options or macaron-class products drop, we cannot trade them without a trader-wiring session. |
| D8 | Custom per-product code | `take_clear_make`, `VolumeRobustMid`, `HysteresisSizer` — yes | **Zero** of the 17 existing strategy files in `src/strategies/` imports SST. They all still hand-roll quote logic. | **No.** R2's 2,078 lines of custom MM variants remain the production path. | **High** — D8 is "custom per-product code"; primitive is unused by any production strategy. |
| D9 | Signals unvalidated | 4-test validation harness — yes | No signal has been run through the harness yet. The harness is a pure Python utility waiting for callers. | **No** evidence any signal has been validated. `FlowAnalyzer`'s output is not validated. | **Medium** — latent; matters when we wire a signal. |
| D10 | Silent exception swallow | `CrashTelemetry` (log + breadcrumb + kill-switch + heartbeat) — yes | `trader.py:108-114` still has the original `try: ... except: return {}, 0, state.traderData`. `run_with_telemetry` is never invoked. | **No.** The exact code path the defect describes still exists verbatim. | **Critical** — first bug in an engine during R3 will be silently swallowed, producing the exact failure mode D10 was supposed to prevent. |

**Summary:** 0 of 10 defects are actually closed in the runtime path. All 10 have primitives; none of them are called from `trader.py`.

---

## 2. Over-engineering / YAGNI findings

### 2.1 `PredictiveEstimator.require_validated=False`

Field exists (`predictive_estimator.py:55`). No realistic production flow would ever pass `require_validated=False` — the whole point is enforcement. This is an escape hatch with no purpose. It also duplicates `SignalBus.get(..., trusted_only=...)` which already has the same mechanism. Recommendation: drop it and always pass `trusted_only=True`.

### 2.2 `SweepSelector` objective zoo

Three scoring functions (`_score_linear`, `_score_top3`, `_score_top10`) plus a `_score_by_quantiles` with an unused normal approximation. The `top3_only` function is labeled "approximation" and admits it doesn't use field data. For R3 prep we only need the statistical-significance gate and the mean — everything else is unused optionality. Keep `_score_linear` + the significance gate; delete the rest until a real top-N objective is needed.

### 2.3 `CounterpartyIntelligenceEngine` — violates the DO-NOT-BUILD list

From Part 6 of the architecture doc: "Counterparty-informed-flow detection on R1/R2-class products. Olivia only appears on volatile products." The engine's docstring (`counterparty_intel.py:5-7`) says: "Runs across ALL products from R3 tick 0. Hidden-alpha top-1 finding: Olivia-class informed bots are detectable from R1..." **This directly contradicts the locked-in DO-NOT-BUILD item #4.** F4 already told us there is no Olivia to find on stable products. Running this cross-product will fingerprint-hash noise and emit "informed" tags on retail traders — a textbook false-positive generator.

Recommendation: scope the engine down to volatile/option products only, or delete entirely and defer to R5 when names are revealed.

### 2.4 BSM / smile — **appropriately sized**, not over-engineered

Abramowitz-Stegun approximation is correct (scipy unavailable). Quadratic-warmup → EWMA rolling degradation is the right pattern (matches F1 finding on chrispyroberts). The 3x3 Gaussian-elimination solver is fine.  One minor note: `implied_vol` has an auto-widening bracket (lo=0.001, hi=5.0 → 10.0) that's only partially justified; for 5-strike voucher chains the bracket is empirically narrower than this. Keep it — defensive coding here is cheap.

### 2.5 SST `prevent_adverse` branch

`_is_toxic` scans `snapshot.trades` for prints with `quantity <= 2`. This is a micro-feature that adds non-trivial logic to every quote but doesn't appear in any top-team repo the archaeology found. The adjustment is ±1 tick on the quote — probably smaller than the noise floor. If we keep it, it should be `False` by default; if `True` by default, it should be tested against a specific failure mode we actually observe. Right now it's speculative.

### 2.6 `VolumeRobustMid` — three variants, one used

`max_amount_mid`, `filtered_wall_mid`, `walls_and_mid`: the first is what engines consume. `filtered_wall_mid` (the helper) is redundant with the existing `FilteredWallMidEstimator` class in `src/core/fair_value.py:384-426`. `walls_and_mid` is used only in tests (`test_stage_b_primitives.py`) — no production code. Either wire it into SST (to implement the actual "quote inside wall" F2 pattern) or delete it.

### 2.7 `FillCalibrationHarness` taking a closure parameter

`sweep_fill_rate` takes `run_simulation_fn` as a user-supplied closure. This is a reasonable decoupling, but there is also no helper script in `src/scripts/` that actually CONSTRUCTS that closure and runs a real calibration. A harness you never call is not closure on D1.

---

## 3. Missing primitives from top-team archaeology

### 3.1 "Quote inside wall" is missing from SST

The archaeology explicitly documents `bid = max_amt_bid + 1`, `ask = max_amt_ask - 1`. SST instead does:
```python
bid_price = int(math.floor(fair_value - params.default_edge))
if join is not None:
    bid_price = max(bid_price, join.price)  # joins AT the level, not inside
```

That's "join the wall," not "quote inside the wall." The difference is one tick on every quote — in a 1-wide-spread product, that's the entire edge. The `walls_and_mid` helper in `volume_robust_mid.py` exists but is not used by SST. This is the single most-cited pattern in the archaeology (`topteam_mm_archaeology §2`) and it's not in the primitive.

**Fix required** before R3.

### 3.2 `disregard_edge` / `join_edge` / `default_edge` / `prevent_adverse` distinction

All four params exist in `SSTParams`. ✓ Good — no collapse.

### 3.3 `collections.deque(maxlen=...)` consistency

Mostly good. `options/smile.py`, `options_mm.py`, `counterparty_intel.py`, `crash_telemetry.py` all use `deque(maxlen=...)`. But:
- `src/conversions/layer.py:209`: `_history: list[float]` with `self._history.pop(0)` at line 214. **Inconsistent.** Fix to `deque(maxlen=lookback_window)`.
- `src/analysis/calibration/fv_estimator_mae.py:171`: `history.pop(0)` — legacy, arguably out of scope.

### 3.4 No `FilteredWallMidEstimator` wrapper for the SignalBus path

Phase 1 says "P2 `VolumeRobustMid` promoted to primary primitive (wrap our `FilteredWallMidEstimator`)". Actually the new module DUPLICATES the logic rather than wrapping it — both implementations exist and can drift. Either delete one or rewrite the new one as a one-line call to the old one.

---

## 4. Redundancy / duplicate code

1. **`FilteredWallMidEstimator` vs `filtered_wall_mid()`** — same algorithm, two implementations. Delete one.
2. **`PortfolioRiskManager` wraps `RiskManager` by composition** — reasonable (non-breaking), but the wrapper re-exposes `.clip_orders` and `.capacity` as pass-throughs. Could just subclass. Not a bug; minor code smell.
3. **Residual logic lives in two places**: `ResidualAllocator` (the legacy, still wired in trader.py) + `PortfolioRiskManager.residual_allowed()` (the tag-aware gate). The tag-aware gate returns a bool but NOTHING consumes the bool — the legacy allocator still decides on its own. Either delete the new gate (dormant) or wire it.
4. **`SignalBus.empty_signal_bus()` factory** is a 2-line convenience for something the caller can write inline. Minor.

---

## 5. DO-NOT-BUILD violations

| Rule | Status |
|---|---|
| OBI asymmetric quoting on stable products | OK — not built. |
| Directional-taker overlay by OBI | OK. |
| Microprice placement as primary FV | OK — VolumeRobustMid is the primary primitive. |
| **Counterparty detection on R1/R2-class products** | **VIOLATED.** `CounterpartyIntelligenceEngine` is explicitly designed to run across all products from R3 tick 0. See §2.3. |
| Neural predictor | OK. |
| SVI / local-vol surface | OK — quadratic + EWMA. |
| Kalman primary hedge ratio | OK. |
| More MM variants | OK — no new ones. |
| Plateau-chart selection | OK (primitive built; old scripts still use plateau but they're not the sanctioned path). |
| Process-gate residual enablement | Partially violated — the new tag-based gate exists but the legacy process gate is still what production runs. |
| Custom per-product code ≤100 lines | OK in theory — the engines are ≤300 lines — but since no strategy file uses SST, the 2,078 lines of legacy MM variants haven't shrunk by a single line. |

Net: **1 clear violation (counterparty intel) + 1 partial (residual dual-path).**

---

## 6. Doc-vs-code drift

Doc claims vs reality:

- **"Residual-allocator default=on for arb-tagged strategies (D5)"** — reality: the flag exists on `PortfolioRiskConfig.residual_default_on_for_arb=True` but `trader.py` never consults it. The legacy `ResidualAllocator` with `enabled=False` (or whatever it defaults to in `EngineConfig.residual_config`) is what the production path uses.

- **"Shuffle test (randomize t, IC drops to ~0), strict-lag IC, walk-forward OOS, own-quote causality — a signal without all 4 passes is for research logging only"** — reality: the 4-test harness exists as a library. No caller runs the tests against any current signal. No signal is marked `validated=True` anywhere, so any `PredictiveEstimator` hooked up would simply be no-ops (it returns the base unchanged).

- **"Phase 0: at end, our backtest numbers are trustworthy and our error mode is loud"** — neither is true. Backtest is still using `passive_allocation=0.3`; errors are still silently swallowed at the top of `run()`.

- **"Phase 1: at end, we can build cross-product strategies"** — we can INSTANTIATE them but cannot DISPATCH them. `StrategyContext` has no `portfolio` field. No trader-side code builds a `PortfolioSnapshot`.

- **"Phase 2: at end, signals are first-class and validated"** — signals are first-class in the *new* module but invisible to the *old* trader. `FlowAnalyzer → SignalEmitter` promotion listed as a 1-hour task in the doc has not happened.

- **"Phase 4: at end of Phase 4, ready for R3 opening"** — NO. Phase 0's wiring step and Phase 4's trader-integration step are both undone.

- **Part 9's "6 questions we should be able to answer"** — we can answer NONE of them cleanly:
  1. Fill-calibration match ±5%? → no calibration run
  2. Consolidated to 2-3 FV estimators? → all 12 still registered
  3. Validated IC per signal? → no signal validated
  4. Trade basket without trader.py edits? → no, because trader.py has no `portfolio` plumbing
  5. Kill-switch latency? → kill-switch not wired
  6. DO-NOT-BUILD list? → yes (this is the only one cleanly answerable, and the counterparty engine violates it)

---

## 7. Dead code / YAGNI

- `PredictiveEstimatorConfig.require_validated` — never exercised. §2.1.
- `SweepSelector._score_top10`, `_score_by_quantiles`, `RankScoreCurve = "custom"` — unused. §2.2.
- `VolumeRobustMid.walls_and_mid` — used only in tests. §2.6.
- `SignalBus.empty_signal_bus` — unused.
- `CounterpartyIntelEngine.summary()` — unused outside hypothetical debug tooling.
- `HysteresisConfig.scale_exponent` — mathematically correct, but all engine consumers use default `1.0`. Defer the non-linear option until it's actually needed.
- `StockpileConfig.max_inventory_buffer` — never set; always `None` in the codebase.

---

## 8. The "ready for R3" gap list

Before R3 opens, the following wiring steps are required. Each is small, but none has been done:

1. **Extend `StrategyContext`** (in `src/strategies/base.py`) with an optional `portfolio: PortfolioSnapshot | None = None` field. Update constructor in `trader._step_product` to populate it. (30 min)
2. **Build the portfolio once per tick** in `_run_body`, before the per-product loop, so every strategy gets the same frozen snapshot. (30 min)
3. **Register a trader-level `SignalBus`** that is cleared at tick start, populated by emitters during the tick, and passed into strategies that opt in. (1h)
4. **Promote `FlowAnalyzer` to a `SignalEmitter`** writing into the bus (doc claims 1h; never done).
5. **Wire `CrashTelemetry.run_with_telemetry` as the per-product wrapper**, replacing the top-level `try/except` in `run()`. Persist `CrashTelemetryState` into `traderData`. (2h)
6. **Run the `FillCalibrationHarness` once**, actually build the reference closure, pick a `passive_allocation`, commit the calibrated value to `FillModelConfig` as the new default. (4h — the closure needs a real reference strategy to run through the sim)
7. **Register the R3+ engines in a dispatch layer.** Either:
   - Extend `STRATEGY_REGISTRY` to accept cross-product engines (adapter pattern), or
   - Add a parallel `ENGINE_REGISTRY` that `trader._run_body` also dispatches after the single-product loop.
   (3h)
8. **Add the "quote inside wall" primitive path to SST** — either a new `SSTParams.quote_inside_wall: bool = False` with the wall+1/-1 logic, or a separate small function in `volume_robust_mid.py` called `inside_wall_quotes(snapshot, fair, ...) -> tuple[int, int]`. (1h)
9. **Port one production strategy to SST** end-to-end (e.g. take `ash_phase_i.py` and rewrite its quote logic via `take_clear_make`). Measure delta vs legacy on a replay to verify no regression. (3h)
10. **Fix the DO-NOT-BUILD violation**: either restrict `CounterpartyIntelEngine` to a whitelist of volatile products with documented-informed counterparties, or mark it dormant (not registered) until R5 name-reveal. (15 min config change)
11. **Fix `RegimeDetector._history` → `deque(maxlen=)`**. (5 min)
12. **Delete one of `FilteredWallMidEstimator` / `filtered_wall_mid`** to avoid logic drift. (15 min)

Total: ~16 calendar hours of work before any R3 engine can actually run in production.

---

## 9. THE SHORTLIST — top 5 things that must be fixed before R3 opens

Ranked by severity × blast radius:

1. **Rewire `trader.py` to actually use the new primitives.** Nothing else matters — `PortfolioSnapshot`, `SignalBus`, `CrashTelemetry`, engine dispatch, and the `portfolio` field on `StrategyContext` are all currently unreachable. Without this, D3, D4, D5, D7, D8, D10 are all unclosed in the runtime path regardless of how many primitives exist. (Items 1-3, 5, 7 in §8 above.)

2. **Run the FillCalibrationHarness for real and commit a calibrated `passive_allocation`.** Zero reference datapoints have been processed. Until this is done, D1 is wide open and any sweep we run before R3 opens will select noise — exactly like R2. Use our own R2 Promoted variant as the reference (data is available; truth is 7,654 ± 366 over 4 IMC runs).

3. **Delete or gate the `CounterpartyIntelligenceEngine` per the DO-NOT-BUILD list.** Running cross-product fingerprint-hashing on R1/R2-class products where F4 already said no Olivia exists will fabricate "informed" tags on retail traders. The piggyback-sizing consumer will then take size against those false signals. This is a net-negative production path. Either restrict to a small whitelist (volatile products only, when they appear) or don't register it. Low-confidence alpha chasing a ghost.

4. **Port "quote inside wall" into SST and port one real strategy to use it.** The archaeology's single most-convergent pattern (`bid = max_amt_bid + 1`, `ask = max_amt_ask - 1`) is absent from the "take/clear/make" scaffold. A scaffold that doesn't implement the most common top-team quote placement is a scaffold in name only. Without porting at least one legacy strategy to SST, D8 has zero evidence of being closed — the 2,078 lines of custom MM code are still the production path.

5. **Replace the top-level `try/except` in `Trader.run` with `run_with_telemetry`.** The literal code `except Exception: ... return {}, 0, state.traderData` that D10 describes is still in `trader.py:108-114`. During R3, the first bug in a new engine will be silently swallowed. Kill-switch infrastructure is built but inert. This is a 30-minute wiring fix; skipping it re-creates the exact invisible-failure mode the entire architecture was meant to prevent.

**Bottom line:** the brick-making phase (primitives + engines) is in excellent shape — well-tested, well-scoped, well-documented. The house has not started. The doc's Phase 5 "during rounds (reactive)" assumes an integrated foundation; the reality is that Phases 0 Steps, 1's integration work, and Phase 4's engine dispatch wiring are all outstanding. ~16h of concrete wiring stands between "109 passing unit tests" and "engines can trade in R3."
