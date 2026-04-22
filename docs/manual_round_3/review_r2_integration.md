# R3 Engine Integration Review — Wiring Audit

**Branch:** `round3-engine` @ `4b5b3da`
**Reviewer:** integration-audit pass after Stage E landed
**Scope:** Would the 4 new engines (`BasketArbEngine`, `OptionsEngine`,
`StatArbEngine`, `CounterpartyIntelEngine`) actually run end-to-end in
the Prosperity container against real R3 data?

**TL;DR — no, they would not.** The engines compose primitives cleanly
and import without errors, but there is **zero wiring** from
`src/trader.py` into any engine. The claim "one-time edits needed to
wire them in" in the Stage-E commit message is factually correct but
obscures that **those edits have not been made**. The 4 engines are
library code without a caller. This document inventories every missing
wire and grades severity.

---

## 1. End-to-end trace per engine — what's missing

### BasketArbEngine

- **PortfolioSnapshot source.** `step(portfolio)` takes one as its only
  argument. `build_portfolio_snapshot` exists in
  `src/core/primitives/portfolio_context.py:86` but is **not called
  anywhere in `src/trader.py`**. `grep -r build_portfolio_snapshot src/`
  matches only the definition and one test file. The trader loop at
  `src/trader.py:125-156` iterates `snapshots.items()` per-product and
  builds a single-product `StrategyContext` — it never assembles a
  portfolio view.
- **SignalBus source.** No `SignalBus` instance is constructed anywhere
  under `src/trader.py` or `src/core/`. The engine's `self.bus.emit(...)`
  at basket_arb.py:176 would require the caller to pass a bus it
  doesn't have. No code anywhere calls `bus.clear()`.
- **PortfolioRiskManager source.** The trader holds a plain
  `RiskManager()` (`trader.py:70`), not a `PortfolioRiskManager`. The
  new manager is never instantiated in production code paths.
- **Return path.** `step()` returns `(list[Order], dict[str, ProductTag])`.
  The trader returns `(dict[str, list[Order]], int, str)` — the shapes
  don't line up, and there is no merging code that groups the engine's
  flat list by symbol or reconciles tags with the per-product strategies
  that would also fire on the same symbols.
- **State persistence.** `_WelfordStats` (n, mean, m2) and
  `_current_target_basket` live as plain Python attributes on the engine
  instance. The engine is not recreated per tick (good), but the trader
  is; in live trading `__init__` runs every tick, so the engine instance
  is thrown away. Welford stats reset to n=0 every tick ⇒ the
  `welford_warmup=200` gate never clears ⇒ zero orders, ever.

### OptionsEngine

- All 3 shared dependencies (PortfolioSnapshot / SignalBus / Risk)
  same as above — not built, not passed.
- `SmileFitter._observations` and `_recent_abs_returns` (deque, maxlen=500)
  would reset every tick. Smile warmup threshold is 50 per strike ⇒
  never reached ⇒ `fair_iv` returns `None` ⇒ no quotes.
- `_last_underlying_mid` resets to None every tick ⇒ jump detection
  never triggers (always takes the "first observation" branch).
- **Symbol collision with existing trader.** If `STRATEGY_REGISTRY`
  lists an entry for `VOLCANIC_ROCK`, the trader's per-product loop
  will also call that strategy. Two code paths emit orders for the
  same symbol with no arbitration — the trader's `results[product] = legal_orders`
  (`trader.py:150`) assignment would silently overwrite whichever ran
  last. There is no merge helper.

### StatArbEngine

- `step()` signature: `step(portfolio, *, remote: RemoteQuote,
  external_signal_value: float | None)`. **Where does `remote` come
  from?** Prosperity exposes it through `state.observations.conversionObservations`,
  but `src/core/market_data.py` / `MarketDataAdapter.normalize_state`
  does not extract it. No adapter converts `ConversionObservation` →
  `RemoteQuote`.
- **conversion_qty routing.** The engine returns a signed `int` for
  conversion. `Trader._run_body` at `trader.py:155` hardcodes
  `conversions = 0`. Even if the engine were called, its conversion
  output would be discarded. This is a one-line bug — but it's present.
- **BacktestSimulator.** `src/backtest/simulator.py:164` destructures
  `trader.run()` as `orders_by_product, _, run_state.trader_data` — the
  middle slot (conversions) is thrown away with `_`. Backtests cannot
  evaluate any conversion strategy regardless of trader fix.

### CounterpartyIntelEngine

- Same dependency gaps (Portfolio / Bus).
- Has no return value — `step()` returns `None` and only emits signals
  to the bus. Since no bus is constructed, and no consumer reads from
  a bus, the side effect goes into a black hole.
- `_states`, `_pending_fills`, `_recent_mids` all live as instance
  attributes that would reset per tick. The `forward_horizon_ticks=500`
  classifier never accumulates a resolution because `_pending_fills`
  dies between ticks.

---

## 2. StrategyContext extension — NOT DONE

Docstring in `portfolio_context.py:22` says:

> context.portfolio  # PortfolioSnapshot | None

Reality: `src/strategies/base.py` reads (verbatim, full file):

```python
@dataclass(frozen=True)
class StrategyContext:
    product: str
    snapshot: NormalizedSnapshot
    memory: ProductMemory
    config: ProductConfig
```

No `portfolio` field exists. A `grep -n "portfolio" src/strategies/base.py`
returns nothing. The documented API is aspirational.

**Fix:** add `portfolio: PortfolioSnapshot | None = None` to
`StrategyContext`, populate it in `trader._step_product` by calling
`build_portfolio_snapshot(...)` once at the top of `_run_body` and
passing the same instance to every per-product strategy. ~10 lines.

**Severity: CRITICAL.** Without this, no cross-product strategy can be
dispatched through the existing `generate_intent` hook at all.

---

## 3. CrashTelemetry — defined, tested, unwired

`src/core/primitives/crash_telemetry.py` implements `run_with_telemetry`
and `update_heartbeat`. `grep -r run_with_telemetry src/` matches only
its own definition + tests. **`trader.py:108-114` is unchanged from
pre-Stage-A**: it wraps `_run_body` in a bare `try/except Exception` and
logs with `_LOG.exception(...)`.

Consequences:
- `CrashTelemetryState` is never serialized into `traderData`, so error
  history, kill-switch counter, and heartbeat reset on every
  Prosperity iteration — defeating the whole point of the primitive.
- Kill-switch never fires because the error counter is always 0.
- The "silent hang" detector (`hang_threshold=1000`) is dead code.

**Fix:** in `trader._run_body`, replace the per-product
`strategy.generate_intent(...)` call with a `run_with_telemetry` wrapper
that takes the telemetry state off `engine_state`, and add a
`CrashTelemetryState` field to `EngineState`. ~30 lines including
the state_store schema bump and a migration hook.

**Severity: HIGH.** The legacy try/except at `trader.py:108` already
prevents container crashes (Round-2 killswitch bundle relied on it), so
this is not a liveness regression. But the diagnostic signal the
primitive was built to provide is absent.

---

## 4. SweepSelector — defined, tested, unwired from sweeps

`src/core/primitives/sweep_selector.py` exists (336 lines, full
population-stability pytest). `grep -rn "sweep_selector\|SweepSelector"
src/backtest/` returns **nothing**. `src/backtest/sweep.py` and
`src/backtest/parameter_sweep.py` still select winners via plateau
comparison and eyeballing. The R3 architecture doc claims SweepSelector
is the new tiebreaker — that wiring does not exist.

**Fix:** in `src/scripts/run_sweep.py` (or equivalent), feed per-config
PnL-per-day arrays into `SweepSelector.select()` and print its output.
~20 lines, zero risk.

**Severity: MEDIUM.** Affects tuning discipline only, not production
behavior.

---

## 5. `residual_allowed()` — never called

`PortfolioRiskManager.residual_allowed(tag)` at
`src/core/primitives/portfolio_risk.py:154` is a tag-aware residual gate.
`src/core/residual.py` (the actual `ResidualAllocator` used by the
trader at `trader.py:181`) reads `ResidualConfig.enabled` and ignores
tags entirely. The two code paths do not intersect.

The trader instantiates a single `ResidualAllocator(self.config.residual_config)`
at `trader.py:71` and applies it to every product uniformly. Even if
the R3 architecture plans for arb-tagged basket legs to get
residual=on automatically, nothing invokes `residual_allowed()` to do
that mapping.

**Fix:** when the per-product strategy path is extended to dispatch to
engines, have each engine return tags alongside orders (already
done — see `_build_tags()` in every engine) and have the trader
consult `portfolio_risk_manager.residual_allowed(tag)` before calling
`residual_allocator.augment_orders(...)`. Until then,
`ResidualConfig.enabled=False` remains the authoritative control.

**Severity: MEDIUM.** Engines work without residual; they just leave
capacity on the table.

---

## 6. SignalBus lifecycle — never constructed, never cleared

`grep -rn "SignalBus(" src/` returns only the test file and the bus
module itself. Production code never calls `SignalBus()`. `bus.clear()`
is called by nothing outside tests.

Consequence: if the trader were to wire an engine and create a bus at
`__init__` time, the bus would accumulate signals across ticks (since
`clear()` isn't called per tick) and `last emit wins` would start
reading stale values whenever an emitter short-circuited early (e.g.,
basket engine returning early on missing snapshot leaves last tick's
z-score live). The engines' emit calls are idempotent-by-name so this
isn't catastrophic, but it silently produces misleading metadata.

**Fix:** in `_run_body`, construct a fresh `SignalBus` per tick (or call
`.clear()` on a persistent one before the engine loop starts).

**Severity: HIGH** once wired. Currently moot because nothing reads the
bus in production.

---

## 7. PredictiveEstimator — defined, not registered

`src/core/primitives/predictive_estimator.py` implements the `Estimator`
protocol from `src/core/fair_value.py:34`. The module-level `ESTIMATORS`
map at `fair_value.py:504-517` lists 11 estimators; `PredictiveEstimator`
is absent. `FairValueEngine.register(...)` exists at `fair_value.py:527`
but is never called for a predictive variant in production code.

Even if an engine emits `basket.B1.spread_z`, no fair-value estimator
reads it, so no per-product strategy can consume it.

**Fix:** in whatever product config opts into predictive fair-value
(e.g., a basket component's fair-value method field), instantiate
`PredictiveEstimator(base=..., config=..., bus=shared_bus)` and
register it on `self.fair_value_engine`. ~15 lines.

**Severity: MEDIUM.** Only matters once engines emit validated signals
the single-product strategies want.

---

## 8. Fill-calibration output is informational only

`src/core/primitives/fill_calibration.py` runs a sweep over
`passive_allocation ∈ {0.05, …, 0.5}` and reports the best value.
**Nothing in the codebase consumes that number.**
`FillModelConfig.passive_allocation` at `src/backtest/fill_model.py:49`
defaults to 0.3 and is set via config in a handful of scripts.
`grep -n "passive_allocation" src/` shows all usages are direct — no
read from calibration output, no auto-update.

**Fix:** calibration should write a small JSON (`calibration.json`)
that sweep/backtest entry points read at startup to set
`FillModelConfig.passive_allocation`. Or: calibration just prints its
number and the human updates the default manually. The latter is what
the docstring implies but nothing enforces.

**Severity: LOW.** Calibration is a tool, not a control loop.

---

## 9. Signal validation report — no producer wiring

`src/core/primitives/signal_validation.py:339` defines `validate_signal()`
which produces a report. Engines emit `SignalValue(validated=True, ...)`
with `validated` hardcoded to `True` and no reference to the validator.
No pipeline runs `validate_signal` → sets `validated` based on report
→ returns validated `SignalValue`. The `validated` flag is decorative.

**Fix:** add a thin validator step in engine `__init__` or at the
emit site: run `validate_signal(..., forward_returns=...)` against
recent history, set `validated = report.validated`, and only then call
`bus.emit`. Requires engines to retain forward-return data.

**Severity: HIGH.** Any consumer using `SignalBus.get(trusted_only=True)`
will get data without ever having been validated — directly violating
the D9 rationale in the SignalBus docstring.

---

## 10. Options engine vs per-product dispatcher — conflict unresolved

If the Prosperity state stream includes `VOLCANIC_ROCK` and the
`VOUCHER_*` strikes, and the `STRATEGY_REGISTRY` has any entry for
`VOLCANIC_ROCK` (existing stable-product MM, say), then:

- Per-product loop: computes intent for `VOLCANIC_ROCK`, emits orders,
  writes them to `results["VOLCANIC_ROCK"]`.
- Options engine: emits its hedge order for `VOLCANIC_ROCK` and
  symmetric maker quotes on every voucher.
- The trader return format `dict[str, list[Order]]` has no merge step.
  Whichever code ran last overwrites.

The engine tags its underlying as `strategy_tag="hedger"`, and per-product
strategies do not know tags exist. `RiskManager.clip_orders` at
`trader.py:190` receives a single product's orders and has no visibility
into the engine's contribution.

**Fix:** define merge semantics. Simplest: per-product strategies opt
out of products owned by engines (via `ProductConfig.owned_by_engine =
"options_book"` or similar), and the trader routes accordingly.

**Severity: CRITICAL** once engines fire.

---

## 11. traderData serialization — engines have no persistence hook

- `SmileFitter` exposes no `snapshot()` — checked
  `src/options/smile.py`: no `snapshot`, `save_state`, or `restore_state`
  method. Its `_observations: dict[strike, deque]` and rolling means
  would need a serializer.
- `CounterpartyIntelEngine.summary()` returns debug info, not a
  persistence blob — states (rolling P&L, position, wins, pending
  fills) are not serializable in their current shape (deque of tuples,
  dict nested under object).
- `BasketArbEngine._WelfordStats` is simple (3 floats) — trivially
  serializable, but again, no engine has a `to_dict/from_dict`.
- `StateStore` knows only about `EngineState.products[str] → ProductMemory`.
  Engines don't fit this container.

Size estimate per tick for the counterparty engine: 10-100 active
`CounterpartyState` objects × ~6 fields × ~20 chars of JSON = 1.2 – 12
KB. Plus `_pending_fills` up to 10k tuples of 6 fields = ~1 MB. Way
over the 50k `max_chars` budget. Would need aggressive pruning
(e.g., only persist cp_ids with ≥20 trades + no pending_fills).

Smile: ~3-7 strikes × 200 obs = 1.4 KB; fine.

Welford: 24 bytes per basket; fine.

**Fix:** extend `EngineState` with an `engines: dict[str, Mapping]`
field, define `save/load` methods on each engine, and dispatch at
state_store boundary. This is a schema bump (version 2) requiring
a migration hook. For the counterparty engine, pre-compute summary
stats offline and drop raw history.

**Severity: CRITICAL** for counterparty engine (will not fit budget).
**HIGH** for options (warmup never completes on a new tick batch).
**LOW** for basket (warmup is fast to rebuild — 200 ticks).

---

## 12. Position-limit mismatch — tags do nothing today

Engines build `ProductTag(strategy_tag="arb"|"hedger"|..., arb_group=...)`.
`RiskManager.clip_orders` (the one actually called from `trader.py:190`)
has signature `(product, orders, current_position, limit)` — no tag
parameter. `PortfolioRiskManager.clip_orders` at `portfolio_risk.py:103`
delegates to the base and also ignores tags.

Tags are *only* used by:
- `PortfolioRiskManager.portfolio_capacity` (reads `arb_group`)
- `PortfolioRiskManager.residual_allowed` (reads `strategy_tag`) —
  itself never called (see §5).

In production, tags are structurally decorative. They would matter if
(a) the trader consulted `portfolio_capacity()` to enforce gross/group
caps or (b) `residual_allowed()` were called. Neither happens.

**Severity: MEDIUM.** Doesn't cause incorrect behavior — just means the
gross-exposure cap (`max_gross_exposure`) and per-group cap
(`max_net_exposure_per_group`) in `PortfolioRiskConfig` are unenforced.

---

## 13. BacktestSimulator compatibility — missing adapter

`src/backtest/simulator.py:164` does:

```python
orders_by_product, _, run_state.trader_data = self.trader.run(state)
```

`self.trader` is a `Trader` (line 43), and Trader.run signature is
`(TradingState) → (dict[str, list[Order]], int, str)`. The simulator
never touches `PortfolioSnapshot`, `SignalBus`, or any engine. Even
after the trader is wired, backtests will only exercise the engines
if the engines are invoked via the trader's `_run_body` — they cannot
be tested in isolation through the backtest simulator without a
dedicated harness.

Additionally (repeat of §1-StatArb): the simulator throws away the
`conversions` return, so any stat-arb conversion P&L is invisible
in backtests.

**Fix:** once engines are wired inside `trader._run_body`, the
simulator works by default — but conversion P&L needs the `_` → `conversions`
bind plus downstream accounting in `_ProductAccounting`. ~30 lines.

**Severity: HIGH.** Without this, we cannot replay R3 data against the
options or basket engines to validate calibration before going live.

---

## 14. Import graph — clean

```
$ PYTHONPATH=. .venv/bin/python -c "import src.engines.basket_arb; \
    import src.engines.options_mm; import src.engines.stat_arb; \
    import src.engines.counterparty_intel"
# exit 0, no warnings
```

Full primitive+engine import also OK. No circular imports.
`src.engines.*` depends on `src.core.primitives.*`, `src.options.*`,
`src.conversions.*`, `src.datamodel`. None of those depend back on
`src.engines.*`. Graph is a clean tree.

**Severity: NONE.** This is the one category that works.

---

## What actually happens if you do `engine.step(portfolio)` on real R3 data?

Assume a user has somehow assembled a `PortfolioSnapshot` (they haven't
— no such code exists — but imagine) and calls `engine.step(portfolio)`.

1. **BasketArbEngine.step(portfolio)** — runs; first-tick returns
   `([], {tags…})` because `self._stats.n == 1 < welford_warmup=200`.
   After 200 ticks of steady calls with real data, starts emitting
   orders correctly **iff** the PortfolioSnapshot contains all basket
   constituents. If the caller recreated the engine between ticks
   (any realistic Prosperity usage): Welford resets each time ⇒
   engine returns `[]` **forever**.

2. **OptionsEngine.step(portfolio)** — Requires
   `underlying.mid is not None`. Computes IVs; calls `SmileFitter.observe()`
   for each voucher with a mid. Fairs come back `None` for the first 50
   observations per strike (warmup threshold), so `_step_voucher` returns
   `([], 0.0)` for each. After 50 observations per strike, starts quoting.
   Delta hedge is OFF by default (good), so no Volcanic Rock orders.
   **If engine instance is recreated per tick: smile never warms up, no
   quotes, ever.** Jump detector similarly never trips.

3. **StatArbEngine.step(portfolio, remote=..., external_signal_value=...)**
   — **Will immediately raise** `TypeError: step() missing 1 required
   keyword-only argument: 'remote'` unless the caller manually constructs
   a `RemoteQuote`. There is no extractor that produces one from
   `TradingState.observations.conversionObservations`. If you wire one
   by hand: runs, returns `(orders, conv_qty, tags)`. The caller must
   route `conv_qty` into Prosperity's `conversions` return slot —
   nothing in the repo does that today.

4. **CounterpartyIntelEngine.step(portfolio, current_tick)** — runs;
   silently ingests trades, classifies, emits to a bus. If no one
   holds the `SignalBus` reference, garbage-collected at end of tick.
   If `_pending_fills` isn't kept alive across ticks (because engine
   is recreated), win rate stays at 0.0 forever ⇒ classifier outputs
   `"noise"` or `"unknown"` for every counterparty.

### What breaks, ranked

| # | Gap | Prod fire? | Severity | Fix cost |
|---|-----|------------|----------|----------|
| 1 | `StrategyContext.portfolio` field missing | No (engines unreachable) | CRITICAL | 10 LoC |
| 2 | `build_portfolio_snapshot` never called | No | CRITICAL | 5 LoC |
| 3 | `SignalBus` never instantiated, never cleared | No | HIGH | 5 LoC |
| 4 | `PortfolioRiskManager` never instantiated | No | HIGH | 5 LoC |
| 5 | Engine state not persisted into `traderData` → warmup resets every tick | No | CRITICAL | ~60 LoC + schema bump |
| 6 | Conversion qty discarded (`trader.py:155` hardcoded 0, simulator `_`) | Yes, silently | CRITICAL for stat-arb | 2 LoC trader + 30 sim |
| 7 | Options + per-product strategy dual-ownership of underlying, no merge | Orders overwritten | CRITICAL | config + routing |
| 8 | CounterpartyEngine state too big for 50k budget | Persistence impossible as-is | CRITICAL | pruning + serializer |
| 9 | CrashTelemetry unwired | Legacy try/except still active | HIGH | 30 LoC |
| 10 | `residual_allowed()` never called | Arb doesn't get residual; no *wrong* behavior | MEDIUM | 10 LoC |
| 11 | Tags are decorative (portfolio caps unenforced) | No regression vs today | MEDIUM | 15 LoC |
| 12 | `PredictiveEstimator` not registered | No consumer of engine signals | MEDIUM | 15 LoC |
| 13 | `validate_signal()` not invoked; `validated=True` hardcoded | Trust boundary violated | HIGH | engine-level | 
| 14 | `SweepSelector` not wired into sweep scripts | Tuning only | MEDIUM | 20 LoC |
| 15 | `FillCalibration` output manual | Tuning only | LOW | 10 LoC |
| 16 | Backtest simulator has no engine adapter | Can't backtest engines | HIGH | 40 LoC |
| 17 | Import cycles | Clean | NONE | 0 |

---

## Minimum bring-up order (recommended)

1. **Fix `StrategyContext.portfolio`** (§2). Unblocks everything else.
2. **Build `PortfolioSnapshot` once in `_run_body` and share** (§1).
3. **Construct `SignalBus` per tick, pass to engines** (§6).
4. **Persist engine state** (§11). Without this, engines are stateless
   and warmups never complete.
5. **Route conversions** — replace `conversions = 0` at
   `trader.py:155` with the stat-arb engine output sum. Extend simulator
   to capture and account for it (§1 + §13).
6. **Arbitrate options-vs-per-product** via a `ProductConfig.owner` field
   (§10).
7. **Wire `CrashTelemetry`** (§3) once the dispatcher has engine calls
   to wrap.
8. **Hook `validate_signal`** before any engine `bus.emit(validated=True)`
   (§9).

Items 9-15 can come after the engines demonstrably run end-to-end against
a replay.

---

## Bottom line

The Stage-A→E primitives and engines are well-factored, unit-tested,
and import cleanly. What they are **not** is integrated: `trader.py`
has not gained a single line that references any Stage-B / C / D / E
module. The Stage-E commit message ("E1-E4 engines; one-time edits
needed to wire them in") is literally accurate and strategically
misleading — the wiring is the hard part, and it has not been started.

Before R3 goes live, at minimum items 1, 2, 3, 4, 5, 6, 7, 10 (from the
§ numbering above) must ship. Otherwise the engines are unreachable
library code, and the trader runs the same Round-2 per-product strategies
it already runs today.
