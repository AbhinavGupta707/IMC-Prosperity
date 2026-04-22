# R3+ Engine Architecture — Defect-Driven Redesign

**Authoritative doc for Prosperity 4 R3/R4/R5.** Supersedes prior engine blueprints where they conflict.

**How this doc was derived:** R1/R2 diagnostic work produced evidence of 10 structural defects in our existing engine. Prior design docs (engine_etf_basket / engine_options / engine_statarb_signal / hidden_alpha_analysis) proposed R3+ blueprints but did not explicitly tie them to the diagnosed defects. This doc closes that loop: defects → architectural requirements → shared primitives → engines-as-implementations → sequenced build order.

**Evidence pointers** throughout. Every claim traces to a diagnostic file under this directory.

---

## Part 1 — The 10 structural defects (evidence-backed)

Each defect below is a property of our current engine that caused measurable R1/R2 underperformance and will cause 3-10× more damage on R3+ products. Evidence references are to files in `docs/manual_round_3/`.

| # | Defect | Evidence | R1/R2 cost | R3+ cost multiplier |
|---|---|---|---|---|
| D1 | **Backtest fill-model miscalibrated.** `passive_allocation=0.3` is a guess. Selected R2's `wide_w113` as the "winner" when it actually LOST to `Ash L1` on IMC simulator. | DIAGNOSTIC_FINDINGS §2, CRITICAL_EVAL_FINDINGS §2 | 4% vs what we could have shipped | 10× — every R3 product sweep amplifies the bias |
| D2 | **Fair-value estimators are all reactive.** 12 estimators: anchor / mid variants / wall variants. Zero predictive estimators (signal-conditioned, regime-conditioned, or cross-product-conditioned). | CRITICAL_ANALYSIS_R1R2_GAP §F5, forensic_own_logs §3 | Modest on MM products | 5× — baskets / options / macaron-style arb all depend on predictive fair value |
| D3 | **Per-product StrategyContext.** `STRATEGY_REGISTRY[product] -> strategy` sees only one product at a time. No cross-product state possible. | CRITICAL_ANALYSIS §F4 | Zero (R1/R2 products uncorrelated, D2 diagnostic confirms) | 10× — baskets by construction have ρ ≈ 0.7 with constituents; stat-arb needs multi-product views |
| D4 | **Signals are observational.** `FlowAnalyzer` docstring: "never alters strategy behaviour, fair-value estimates, or execution decisions." | CRITICAL_ANALYSIS §F1 | Directly explains ~14% directional-capture rate (forensic_own_logs §2) | 5× — R3+ has more signal sources (news, IV, external indices, counterparty flow) |
| D5 | **Residual allocator defaults disabled.** Behind a process gate that was never flipped. | CRITICAL_ANALYSIS §F2, DIAGNOSTIC_FINDINGS §5 (D3) | Marginal (MM saturates book) | 3× — arb strategies use fractional book capacity, leaving residual room |
| D6 | **Sweep selection picks noise.** v5 vs Promoted ΔASH +75/run decomposed: high-vol contributions −1.2, low-vol +76.6 (forensic_own_logs). Plateau-chart methodology biases toward robust-but-not-peak. | forensic_own_logs §4, CRITICAL_EVAL_FINDINGS §2 | Shipped a config 4% worse than baseline | 10× — R3 has 10-100× more parameter combinations |
| D7 | **Engine breadth is shallow.** 2,078 lines of MM variants (Avellaneda-Stoikov, Cartea, Guéant, 7 Pepper, 7 ASH). Zero BSM. Zero cross-product. Zero conversion tracking. Zero options primitives. | src/strategies/ + src/core/ inspection | N/A for R1/R2 | Infinite — can't build R3 options without BSM; can't build R4 macaron without conversions |
| D8 | **Per-product custom strategy code.** No shared "take/clear/make" primitive; each MM variant re-implements from scratch. Top teams reuse a single SST template across all products. | topteam_mm_archaeology §2 | Time cost during R1/R2 prep | 5× — R3 has 7+ products; custom-per-product doesn't scale to 3-day round |
| D9 | **Signals wired without validation.** We almost built an OBI-based architecture on a +0.52 IC that is likely endogenous (published OBI IC range 0.05-0.15). F2 grep showed zero top teams exploit OBI on stable products. | academic_obi_exploitation §3, topteam_mm_archaeology §1 | ~20h of wasted agent + investigation time | 5× — R3+ has more signal candidates (IV skew, news sentiment, sunlight regime) |
| D10 | **Silent exception swallowing.** `trader.run()` returns empty orders on any downstream raise. Bug becomes a no-trade period, invisible to metrics. | CRITICAL_ANALYSIS §F3 | Unknown (by definition) | High — R3 complex products make bugs more likely; silent failure hides them |

---

## Part 2 — The 10 architectural requirements (1:1 with defects)

Each defect has a corresponding requirement the R3+ engine must satisfy by construction.

**R1 — Fill-model calibration harness.** Before any R3 sweep, port 2-3 top-team P3 repos (chrispyroberts, TimoDiehm, CarterT27) through our `BacktestSimulator`. Sweep `passive_allocation ∈ {0.05…0.50}`. Adopt the value that reproduces their published scored P&L. All subsequent sweeps measured under the calibrated fill model.
→ Fixes D1.

**R2 — Predictive `Estimator` protocol.** New estimator type: `PredictiveEstimator(signal: SignalHandle, base: Estimator) -> FairValueEstimate` — composes a predictive correction onto a reactive base. Coexists with existing reactive estimators. Used for basket spread Z-score, IV smile residual, regime-conditioned mid.
→ Fixes D2.

**R3 — `PortfolioContext` extension to StrategyContext.** Adds `portfolio: PortfolioSnapshot` field carrying all products' snapshots + counterparty state + cross-product signals. Existing single-product strategies unchanged (ignore the field); new multi-product strategies read it. Non-breaking.
→ Fixes D3.

**R4 — `SignalBus` as first-class engine layer.** Every signal (flow score, OBI, IV skew, basket premium, etc.) is produced by a `SignalEmitter`, consumed by a `SignalConsumer`. Each signal carries its own validation metadata (rolling IC, shuffle-test baseline, age). Strategies subscribe; `FlowAnalyzer` promoted from observational to causal.
→ Fixes D4 + D9.

**R5 — Residual allocator default=on for arb strategies.** `ResidualConfig.enabled=True` is the default for strategies tagged `arb_type`. Enablement gate replaced with a pytest regression test that blocks commits if residual hurts on reference replay.
→ Fixes D5.

**R6 — Statistically-significant sweep selection.** Replace plateau-chart selection with: (a) bootstrap-CI on per-day P&L across ≥ 5 replay days, (b) rank-payoff objective (simulate rank distribution under field model), (c) require winner's CI to exclude baseline's upper bound. No more "v5 beat Promoted by +75" non-sig selections.
→ Fixes D6.

**R7 — Fill out the missing strategy classes.** Build BSM + IV solver + smile fitter; conversion layer for cross-exchange arb; cross-product coordinator for basket arb. Not more MM variants.
→ Fixes D7.

**R8 — Shared scaffolds reused across products.** One `TakeClearMake` helper consumed by every strategy. One `VolumeRobustMid` fair-value primitive. One `HysteresisSizer` used for all spread-style entry/exit. Top-team pattern: SST template from Linear Utility ported verbatim by Sylvain.
→ Fixes D8.

**R9 — Mandatory signal validation harness.** Every signal must pass: (a) shuffle test (randomize t, IC drops to ~0), (b) strict-lag IC (feature at t-k predicting mid at t, not t+k), (c) walk-forward OOS on held-out replay days, (d) own-quote causality test (remove ticks where our orders are at top-of-book, IC should survive). A signal without all 4 passes is for research logging only, not trading.
→ Fixes D9.

**R10 — Fail-loudly crash telemetry.** `trader.run()` still wraps in try/except (required — container must not crash) but on catch: (a) append error class + traceback summary to `traderData.errors` deque, (b) expose `recent_errors_count` on every strategy, (c) kill-switch at 3 errors / 100 ticks forces flatten, (d) `summary_table` surfaces error counts alongside P&L.
→ Fixes D10.

---

## Part 3 — Shared primitives (building blocks for all R3+ engines)

Every R3+ engine (basket, options, stat-arb, options-on-basket, whatever IMC drops) is assembled from these primitives. Write once, reuse everywhere. Each primitive satisfies one or more requirements from Part 2.

### P1 — `TakeClearMake` scaffold (R8)
```
def take_clear_make(
    context: StrategyContext,
    fair_value: float,
    take_width: int,       # cross spread if opponent beyond fair ± width
    clear_width: int,      # flatten excess inventory
    default_edge: int,     # maker quote offset from fair
    prevent_adverse: bool, # skew quote away when inventory adverse-selected
) -> list[Order]
```
Ported verbatim from Linear Utility's SST template (`round_1_v6.py:14-310`). Every R3+ strategy wraps this.

### P2 — `VolumeRobustMid` fair-value primitive (R2, R8)
Implements `max_amt_mid` (largest-volume bid/ask midpoint) with a min-volume filter to ignore penny-jumpers. Our existing `FilteredWallMidEstimator` already does this; promote to primary for stable products.

### P3 — `HysteresisSizer` (R8)
Asymmetric entry/exit sizing function used by every spread/arb strategy. Enter `|z|>2`, exit `|z|<0.3`, kill `|z|>4`. Generalizes from basket engine spec.

### P4 — `BSM + IV solver + smile fitter` (R7)
Inline `norm_cdf` (Abramowitz-Stegun), Brent-method IV solver with `[0.001, 1.0]` bounds, hybrid smile fitter (quadratic warmup → rolling mid-IV). Full spec in `engine_options.md`.

### P5 — `ConversionLayer` (R7)
Handles cross-exchange products: signed break-even calculator with symbolic tariffs, conv-cap-aware batched execution, external-signal regime detector (percentile-flag, not linear regression). Full spec in `engine_statarb_signal.md`.

### P6 — `PortfolioContext` (R3)
Extension of `StrategyContext` carrying `{product: NormalizedSnapshot}` dict + shared counterparty state + shared signal bus.

### P7 — `PredictiveEstimator` (R2)
Composes reactive base (e.g., wall-mid) with a signal correction (e.g., z-score on basket premium). Output has explicit confidence derived from signal IC.

### P8 — `SignalBus` (R4, R9)
Pub/sub for signals with lifecycle: `emit(name, value, metadata)`, `subscribe(name, handler)`, `validate(name, replay_data)`. Validation runs the 4-test harness (shuffle, strict-lag, OOS, own-quote-causality) and refuses to promote a signal to trading until all 4 pass.

### P9 — `PortfolioRiskManager` (R3, R5)
Extends `RiskManager` to cross-product: tracks gross/net exposure, delta across options books, basket-vs-constituents hedge ratio. Residual-allocator default=on behind this layer for arb-tagged strategies.

### P10 — `FillCalibrationHarness` (R1)
Standalone tool: load a top-team repo's trader, run through our `BacktestSimulator` at multiple `passive_allocation` values, report the value that reproduces their published P&L. Output is a calibrated `passive_allocation` constant used by all subsequent sweeps.

### P11 — `SweepSelector` (R6)
Replaces our current plateau-chart tooling: bootstrap-CI on per-day P&L, rank-payoff objective with P3-field prior, significance gating.

### P12 — `CrashTelemetry` (R10)
Wraps strategy execution with error counting, traceback summary, kill-switch, heartbeat dashboard.

---

## Part 4 — R3+ engines as implementations of the primitives

Each engine is a composition of primitives + product-specific logic. Product-specific logic is MINIMAL (the top-team pattern). The heavy lifting is in reusable primitives.

### E1 — `BasketArbEngine`

**Uses primitives:** P1 (take/clear/make), P2 (wall-mid), P3 (hysteresis sizing), P6 (PortfolioContext), P7 (predictive estimator on basket spread), P8 (spread Z-score signal), P9 (cross-product risk), P11 (sweep selector).

**Product-specific logic (small):**
- Basket composition weights (static integers per spec)
- Spread definition: `B - Σ wᵢ Cᵢ`
- Welford online stats for mean/std
- Dual-gate entry (abs threshold AND z-threshold), close-at-zero exit, `hedge_factor=0.5`, residual-MM on unused capacity

Full spec in `engine_etf_basket.md`. Defect fixes: D1 (sweep under calibrated fill), D3 (cross-product), D4 (spread signal via SignalBus), D5 (residual=on for arb), D6 (sweep selector), D8 (shared primitives).

### E2 — `OptionsEngine`

**Uses primitives:** P1 (take/clear/make), P4 (BSM/IV/smile), P6 (PortfolioContext), P7 (predictive estimator on IV residual), P8 (IV-residual signal), P9 (aggregate delta hedging via portfolio risk), P12 (crash telemetry for options pricing bugs).

**Product-specific logic (small):**
- Per-strike IV smoothing (EWMA halflife 200-500)
- Smile fit degradation policy (quadratic warmup → rolling mid-IV)
- Whalley-Wilmott band gate for delta hedging (aggregate book, not per-strike)
- Jump-detector halt (`|r|/EWMA(500) > 4`)

Full spec in `engine_options.md`. Defect fixes: D1, D2, D3, D4, D7 (BSM primitive), D8, D9 (jump detector is validated signal), D10 (crash telemetry).

### E3 — `StatArbEngine` (cross-exchange)

**Uses primitives:** P1 (take/clear/make), P5 (conversion layer), P6, P8 (sunlight/external signal), P9, P11.

**Product-specific logic (small):**
- Signed break-even calculator
- Thompson-bandit fill-rate probe (auto-calibrates hidden-taker price)
- Geometric-buffer stockpile optimizer (handles conv-cap batching)

Full spec in `engine_statarb_signal.md`. Defect fixes: D2 (regime-flag signal), D4 (signal wired via bus), D5, D7 (conversion primitive), D8.

### E4 — `CounterpartyIntelligenceEngine`

**Uses primitives:** P6 (PortfolioContext), P8 (SignalBus — emits per-counterparty regime flags), P9.

**Product-specific logic:**
- Rolling 5-feature state per counterparty (cum PnL, trade count, win rate, inventory cycle, entry percentile)
- K-means clustering → {informed, MM, noise}
- Synthetic-ID hashing before R5 reveals names
- Piggyback sizing with collision-skip rule

Full spec in `engine_statarb_signal.md`. Defect fixes: D3 (cross-product state), D4 (signal bus), D9 (counterparty signals mandatorily validated).

### E5 — Composite engines (options on basket, etc.)

The primitive stack naturally supports composites. An "option on basket" engine = `BasketArbEngine` for NAV fair + `OptionsEngine` for pricing + `PortfolioRiskManager` for joint delta. No new architectural work; just compose.

---

## Part 5 — Build order (defects fixed per phase)

Sequenced to maximize "defects fixed" / "hours" early on, so later engine work builds on fixed foundations. Each phase has a completion gate.

### Phase 0 — Foundation (10-12h, fixes D1 / D6 / D10 / D8-partial)

**Gate: no R3 sweep work starts until this is done.**

- P10 `FillCalibrationHarness`: port 1 top-team repo (chrispyroberts R1/R2 code); find our true `passive_allocation`. (4h)
- P11 `SweepSelector`: bootstrap-CI + significance gating. (3h)
- P12 `CrashTelemetry`: error counting + kill-switch + heartbeat. (2h)
- P1 `TakeClearMake`: port Linear Utility SST template as `src/strategies/primitives/sst.py`. (3h)

At end of Phase 0: our backtest numbers are trustworthy and our error mode is loud.

### Phase 1 — Cross-product foundation (8-10h, fixes D3 / D5 / D8-partial)

- P6 `PortfolioContext` extension to `StrategyContext`. Non-breaking; existing single-product strategies ignore the field. (4h)
- P9 `PortfolioRiskManager` with residual-allocator default=on for arb-tagged strategies. (3h)
- P2 `VolumeRobustMid` promoted to primary primitive (wrap our `FilteredWallMidEstimator`). (2h)
- P3 `HysteresisSizer`. (1h)

At end of Phase 1: we can build cross-product strategies; residual-MM is default-on; size discipline is shared.

### Phase 2 — Signal foundation (8-10h, fixes D2 / D4 / D9)

- P8 `SignalBus` with pub/sub + lifecycle. (4h)
- P7 `PredictiveEstimator` composing reactive base + signal correction. (3h)
- Signal validation harness (shuffle, strict-lag, OOS, own-quote causality). (3h)
- Promote existing `FlowAnalyzer` from observational to a SignalEmitter. (1h)

At end of Phase 2: signals are first-class and validated; we can wire any signal to any strategy; zero untested signals can reach production.

### Phase 3 — Product-class primitives (12-15h, fixes D7)

Parallel development:
- P4 BSM + IV solver + smile fitter (6h) → enables options
- P5 Conversion layer (4h) → enables cross-exchange arb
- Shared constants module + symbol fail-fast (2h)
- OOS validation harness (last replay day reserved) (2h)

At end of Phase 3: the missing strategy classes have their primitives.

### Phase 4 — Engine assemblies (20-25h)

Now that all primitives exist, each engine is small:
- E1 BasketArbEngine assembled from primitives (8h)
- E2 OptionsEngine assembled from primitives (10h)
- E3 StatArbEngine + E4 CounterpartyIntelligenceEngine (7h)

At end of Phase 4: ready for R3 opening.

### Phase 5 — During rounds (reactive)

- Live-measure signal IC on live counterparty-ID data (enable FlowAnalyzer-derived signals after validation)
- Fire cross-edition regression + DP execution on R5 open (dormant infra built during Phase 3)
- Composite engines if R3 drops options-on-basket / novel pairings

**Total budget: ~60 hours before R3 opens.** Parallelizable across 2 engineers to ~30 calendar hours.

---

## Part 6 — Explicit DO-NOT-BUILD list (preserved from prior research, re-justified)

Prior docs (hidden_alpha_analysis, academic_obi_exploitation, topteam_mm_archaeology) converged on these anti-patterns. Locked in:

1. **OBI-based asymmetric quoting on stable products.** F2 grepped 8 top-team repos; zero use OBI on stable products. F3 suggests our +0.52 IC is endogenous/inflated.
2. **Directional-taker overlay triggered by OBI.** Same reason.
3. **Microprice placement as primary FV.** Top teams use wall-mid / max-amount-mid, not microprice.
4. **Counterparty-informed-flow detection on R1/R2-class products.** Olivia only appears on volatile products.
5. **Bayesian ensemble FV across all 12 estimators.** Top teams pick one robust estimator and stick with it; we were going to overengineer.
6. **Neural predictor / LSTM / transformer.** Transcript-1 winner: "you don't need crazy ML."
7. **SVI / local-vol surface.** Overkill for 5-strike chain; quadratic + rolling mid-IV dominates.
8. **Kalman primary hedge ratio.** Use static OLS for primary; Kalman for drift monitor only.
9. **Variance swaps / AMMs / perpetuals.** Low probability for P4. Do not pre-build.
10. **More MM variants.** Stop. We have 2,078 lines of MM code. Adding an 8th Pepper variant is not the path.
11. **Plateau-chart hyperparameter selection.** Replaced by statistically-significant sweep selector.
12. **Process-gate enablement for residual allocator.** Replaced by regression test.
13. **Custom per-product code.** Every product-specific path must be ≤100 lines of product-specific logic on top of shared primitives.

---

## Part 7 — Validation protocol

Every engine, every signal, every tuning decision must pass:

### For signals
- [ ] Shuffle test: shuffle feature across time, IC drops to ≈0
- [ ] Strict-lag IC: feature at t-k predicting mid at t (not t+k)
- [ ] Walk-forward OOS on held-out replay days
- [ ] Own-quote causality test: remove ticks where our orders touch top-of-book, IC survives

### For engines
- [ ] Unit tests for every primitive
- [ ] Integration test: engine reproduces a known top-team result within ±5% on their replay data
- [ ] Crash-free on a full 3-day replay
- [ ] Kill-switch triggers on synthetic fault

### For tuning decisions
- [ ] Fill-model calibrated (Phase 0 complete) before any sweep
- [ ] Bootstrap CI excludes baseline upper bound
- [ ] ≥ 5 replay days used for CI (not 3)
- [ ] Rank-payoff objective, not Sharpe-plateau

### For deployment
- [ ] Submission-bundle pre-commit hook: tests pass + config diff human-reviewed + crash-telemetry armed
- [ ] Tag every submission `round-N-final-YYYYMMDD-HHMM`
- [ ] IMC simulator upload results logged per variant (continue the `outputs/round_2/Official Results/` pattern into R3)

---

## Part 8 — Reference map (what each existing doc contributes)

| Doc | Role under this architecture |
|---|---|
| [CRITICAL_ANALYSIS_R1R2_GAP.md](CRITICAL_ANALYSIS_R1R2_GAP.md) | Original 9-failure-mode analysis; some reframed in Part 1 above |
| [DIAGNOSTIC_FINDINGS.md](DIAGNOSTIC_FINDINGS.md) | Empirical evidence for D1, D3, D5 |
| [forensic_own_logs.md](forensic_own_logs.md) | Empirical evidence for D2, D4, D6; missed-directional-window quantification |
| [topteam_mm_archaeology.md](topteam_mm_archaeology.md) | Primitive specifications (SST template, wall-mid, inside-wall placement) |
| [academic_obi_exploitation.md](academic_obi_exploitation.md) | Signal-validation harness design (4 tests); warning on +0.52 IC |
| [hidden_alpha_r1r2_stable_products.md](hidden_alpha_r1r2_stable_products.md) | DO-NOT-BUILD rationales; ranked fix list |
| [engine_etf_basket.md](engine_etf_basket.md) | E1 spec — to be refactored as primitive composition |
| [engine_options.md](engine_options.md) | E2 spec — ditto |
| [engine_statarb_signal.md](engine_statarb_signal.md) | E3+E4 spec — ditto |
| [P4_R3-5_STRATEGIC_BRIEF.md](P4_R3-5_STRATEGIC_BRIEF.md) | Strategic context; round-by-round product forecasts |
| [ENGINE_DESIGN_CATALOG.md](ENGINE_DESIGN_CATALOG.md) | Previous adoption plan; superseded by Part 5 of this doc |
| [hidden_alpha_analysis.md](hidden_alpha_analysis.md) | Tier S/A/B alpha ranking; action items absorbed into Phase 4 |

---

## Part 9 — What success looks like

**At the end of Phase 4 (R3 opening), we should be able to honestly answer:**

1. Does our backtest reproduce a published top-team P&L within ±5%? (Phase 0 gate)
2. Are all 12 existing FV estimators still used, or have we consolidated to the 2-3 that pass validation? (Phase 2)
3. For each signal we use in production, what's its validated IC, shuffle-test baseline, OOS Sharpe? (Phase 2)
4. Can our engine trade a basket-vs-constituents spread without any code in `trader.py`? (Phase 1)
5. If an options strategy crashes mid-round, how long until the kill-switch fires? (Phase 0, Phase 4)
6. What's our DO-NOT-BUILD list and why? (Part 6 of this doc)

If all 6 have clean answers, the R1/R2 defects are structurally fixed. Any remaining alpha gap is product-specific tuning, not architectural.

**If we stop here** (build all 60h of foundation + primitives + engines) and extract even the conservative estimates from the prior docs (+10-30k/round vs baseline architecture), we close the top-10 gap. Any further work is chasing Vibing-tier tail alpha — optional.
