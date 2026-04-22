# Critical Analysis — Why R1/R2 Left 20-25% on the Table

**Compiled:** 2026-04-22. Adversarial diagnostic. No complexity limits.

**The gap:** your R1/R2 algo scored 8.5-9k on the sample data. Top teams scored 11-12k on the same data. Same dataset. Same products. Same physics. **Their extra ~2.5-3k is not a generalization gap — it's in-sample alpha your engine structurally cannot see.**

This document is honest, adversarial, and specific. It names what's wrong and what it would take to close.

---

## 1. The gap is diagnostic, not cosmetic

A 25% in-sample gap on the same replay data comes from one of three places:

1. **Signal you cannot see** (feature / predictor absent from your fair-value pipeline)
2. **Size discipline too conservative** (you see the signal, but won't commit the capacity to exploit it)
3. **Fill assumption too optimistic** (your backtest P&L was inflated, and top teams' backtests were too — they got 11-12k reported; on the real submission it would compress)

You've ruled out (3) by saying the top number is on the "same data set" — presumably sample data from their own backtests. So the gap is **(1) and/or (2)**. That's an architectural diagnosis, not a tuning diagnosis.

---

## 2. Nine critical failure modes (ranked by likelihood in your codebase)

Each has specific evidence from your code. Failure mode severity = (probability × P&L cost).

### F1 — CRITICAL: FlowAnalyzer is observational-only, never wired to decisions

**Evidence** ([src/signals/flow_analyzer.py:2-4](src/signals/flow_analyzer.py)):
> "This module is an **observational** layer. It detects patterns in the market trade tape... It never alters strategy behaviour, fair-value estimates, or execution decisions."

**The cost.** You built a flow-detection system, documented it to not influence trading, and ran it purely for logging. Top teams' flow signals skew quotes, resize positions, and toggle strategies — that's the 100-200 bps of alpha per product per day you're leaking.

**Root cause: philosophical.** "Observational" is a defensible choice for Phase-1 research but becomes the default. No one ever promoted the scanner to a signal.

**What this alone explains.** If your flow analyzer has even a 0.05 IC on next-100-tick returns (standard for OBI-based signals), failing to use it costs ~1-2k P&L per day per product. Across 3 R2 products × days, easily the 2-3k gap.

### F2 — CRITICAL: `ResidualAllocator` ships disabled behind an "enablement gate"

**Evidence** ([src/core/types.py:194-206](src/core/types.py)):
> `class ResidualConfig: enabled: bool = False`
> "Ships disabled (framework-only). Enable only after the enablement gate is passed."

**The cost.** Transcript-1 P3 team: "~$5k/day extra just from residual MM, don't leave money on the table." You built the residual allocator, correctly, then left it off behind a process gate that (per your comment) requires comparing baseline vs baseline+residual on 5 metrics before flipping.

**This is discipline at the wrong level.** The enablement gate exists to prevent untested features shipping. But *not shipping* also has a cost — and that cost is invisible in your metrics because you never measured baseline+residual.

**5k/day × 3 products × ~3 days = 45k missed P&L** (if the P3 claim generalizes). Even at 20% of that it's a sizeable chunk of the gap.

### F3 — HIGH: Trader.py silently swallows exceptions

**Evidence** ([src/trader.py:17-22](src/trader.py)):
> "Safety: `run()` is wrapped in a top-level safety net. If any downstream module raises, the trader returns an empty orders dict and preserves the previous `traderData`."

**The cost.** Safety nets that return empty orders turn bugs into silent no-trading periods. In a 15k-timestep day, if any edge case triggers the safety net for 2000 timesteps, you miss 13% of the day with zero signal. Bugs in production code exist; the question is whether you detect or absorb them.

**Rebuttal:** yes, crashing is worse. But the right design is a crash log with a heartbeat, not silent degradation. Top-team repos generally DO crash — they debug in replay and fix before submission.

### F4 — HIGH: Per-product architecture blocks cross-product alpha

**Evidence** ([src/trader.py:8-10](src/trader.py), [src/strategies/base.py:11-14](src/strategies/base.py)):
> `StrategyContext` has single `snapshot: NormalizedSnapshot`, single `product`.
> `STRATEGY_REGISTRY` is keyed by product.

**The cost.** In R2, if SQUID_INK 1-step returns lead KELP returns by N ticks (hypothesis; not tested), no strategy in your codebase can trade it. You'd need a strategy that reads SQUID_INK and emits KELP orders. Nothing in your architecture supports that.

**Latent factor / pairs alpha is 10-30 bps per correlated pair per day.** If any R2 product pair had 0.15+ correlation on 1-lag returns — realistic for a 3-product round — you left ~1-2k/day there.

### F5 — HIGH: 12 fair-value estimators but all are reactive/structural

**Evidence** ([src/core/fair_value.py:34-448](src/core/fair_value.py)): `MidEstimator`, `MicropriceEstimator`, `RollingMidEstimator`, `WeightedMidEstimator`, `EwmaMidEstimator`, `LinearDriftEstimator`, `DepthMidEstimator`, `WallMidEstimator`, `FilteredWallMidEstimator`, `HybridWallMicroEstimator`, `AnchorEstimator`.

**What they all have in common.** Every estimator is a statistic of the current book and recent mids. None is:
- **Predictive** (OBI + flow + trade-imbalance regressed onto next-100-tick mid movement)
- **Counterparty-conditioned** (if `TradePrint.buyer == informed_id` is hitting the ask, shift fair up)
- **Lead-lag-conditioned** (if correlated product just moved, infer this product will follow)
- **Regime-conditioned** (use microprice in high-vol, wall-mid in low-vol)

**The cost.** Reactive fair values can catch the first move, but they never *anticipate* it. Top teams with OBI-based predictors routinely get 60-120 bp/σ of order-flow edge. On 3 products this is 1-2k/day.

### F6 — MEDIUM: You have three academic MM models; picking one per product is a hyperparameter sweep, not a decision

**Evidence.** 7 Pepper variants (1037 + 641 + 362 + 323 + 305 + 309 + 314 lines), 7 ASH variants (194 + 206 + 187 + 272 + 339 + 300 + 320 lines). Avellaneda-Stoikov, Cartea skew, Guéant — three distinct academic reservation-price models.

**The cost.** Having three models means you tune three and pick the best per-product. That's a standard ML trap: the one you pick is the one that overfit best on your sample. The true edge of the model *relative to a baseline* may be 5-10 bp; you're paying complexity cost for that. Worse: the models all reduce to "skew quotes by inventory × vol × risk-aversion" — they're solving the same problem three ways.

**What you're not doing:** adding signal overlays to ANY of them. A-S + flow-skew + OBI-predictor beats any single reservation-price model alone.

### F7 — MEDIUM: Fill-model assumption is an invisible P&L dial

**Evidence** ([src/backtest/fill_model.py:24-29](src/backtest/fill_model.py)):
> `passive_allocation: float = 0.3`
> "We credit ourselves with a fractional share of the traded quantity (`passive_allocation`, default 0.3)"

**The cost.** 30% is a guess. If the true allocation is 0.15 in submission, your backtest over-reports passive P&L by 2×. Strategies that look +4k in backtest deliver +2k live. You tune on the inflated number, optimizing the wrong objective.

**Diagnostic test:** take any P3 top-team repo, run it on your sample data with your fill model at 0.3, 0.2, 0.15. See which value reproduces their reported P&L. That's your true passive allocation. If it's not 0.3, every backtest number in your history is biased.

### F8 — MEDIUM: Hyperparameter selection biases toward "stable neighborhood"

**Evidence:** Transcript-1 winner explicitly recommends "highest P&L + flat derivative around it" — you have a sweep + plateau-chart infrastructure ([src/backtest/plateau.py](src/backtest/plateau.py)). This IS the winner's methodology.

**The cost — subtle.** In a score-reset tournament you're optimizing for peak, not stability. "Stable neighborhood" is robust-but-second. The top-1 USA (chrispyroberts) explicitly YOLO'd Olivia at R5. You'd never pick that hyperparameter set in a plateau chart — it's a spike, not a plateau.

**Translation:** your selection criterion systematically rejects the hyperparameters that generate the top-team numbers. You're optimizing for a different objective function than the rank leaderboard.

### F9 — LOW: Risk manager has no temporary-aggression mode

**Evidence** ([src/core/risk.py:36-96](src/core/risk.py)): `RiskManager` clips to hard position limits. No concept of "this setup is worth 80% of limit; that setup is worth 20%."

**The cost.** Every setup gets full potential sizing. This is OK defensively, but doesn't provide a mechanism to *save* limit capacity for the rare big setup. Elite teams know to stay near-flat most of the time on volatile products and jump with SIZE when the setup is clear (transcript-2 panel, Squid Ink discussion).

---

## 3. The ranked diagnosis

| Rank | Failure mode | Most-likely P&L cost | Root cause |
|---|---|---|---|
| 1 | F1 FlowAnalyzer observational-only | **1-2k/day** | Design philosophy (observational-first) never transitioned to production-signal |
| 2 | F2 ResidualAllocator disabled by default | **0.5-1.5k/day** | Process gate prevented enablement |
| 3 | F5 All fair values reactive, none predictive | **1-2k/day** | Entire FV abstraction is backward-looking |
| 4 | F4 Per-product architecture blocks cross-product | **0.5-1k/day** | `StrategyContext` signature |
| 5 | F7 Backtest/live gap (fill assumption) | **Variable** | Need to calibrate empirically |
| 6 | F8 Plateau-selection bias toward robust-but-not-peak | **0.5-1k/day** | Selection objective mismatched to scoring |
| 7 | F6 Three MM models = decision cost, no signal overlay | **Small** | Engineering cost, not P&L cost |
| 8 | F3 Silent exception swallow | **Situational** | Disguises bugs |
| 9 | F9 Risk manager has no aggression mode | **Small** | Limit usage flat across setups |

**Aggregate estimated leak:** 3-6k/day in-sample, which closes most of the 2.5-3k gap.

---

## 4. What the gap has in common

Every one of these is the same meta-failure: **defensive engineering beats aggressive alpha capture.**

- Observational-only signal module
- Disabled-by-default residual allocator
- Exception-swallowing safety net
- Reactive fair-value estimators
- Plateau-selection hyperparameters
- Per-product sandbox

Your codebase is **engineered to be correct, robust, and hard to break** — every design choice above is an instance of that. But top-team codebases are engineered to be **aggressive, signal-rich, and edge-capturing.** They accept more bugs, more fragility, more per-product coupling — in exchange for reading signals your architecture cannot even express.

**The gap is not "you need to build more features."** The gap is that your architecture has a philosophy that actively prevents certain alpha types from being captured. Until the philosophy changes, more features won't close it.

---

## 5. Blue-sky build plan for R3-5 — no complexity limits

Given no limit on technical complexity, here is the aggressive build I'd do. I'll mark which items are contingent on diagnostic verification (§6).

### Tier X — architectural inversion (must be done before any feature)

**X.1 — Promote signals from "observational" to "causal."** Explicit. Rename `FlowAnalyzer` to `FlowSignalEngine`. Its output feeds into a new `SignalBus` that `FairValueEngine` reads. Any signal with realized IC > 0.03 over 20k ticks in backtest gets wired into quote-skew by default.

**X.2 — Introduce `PortfolioContext` to the strategy contract.** `StrategyContext` becomes:
```python
@dataclass(frozen=True)
class StrategyContext:
    product: str
    snapshot: NormalizedSnapshot
    portfolio: PortfolioSnapshot  # NEW — all products, all counterparty state
    memory: ProductMemory
    config: ProductConfig
```
Any existing strategy ignores the new field; new strategies can read across products. No breaking change, full cross-product alpha unblocked.

**X.3 — Convert `FairValueEngine` from "pick one estimator" to "Bayesian ensemble with online-calibrated weights."** Every estimator outputs `(price, confidence)`. The engine maintains per-estimator realized edge (via trade P&L attribution) and weights them dynamically. Bad estimators die; good ones dominate. No manual selection.

**X.4 — Flip the default on residual allocator.** `enabled=True`. The "enablement gate" becomes a regression test, not a deployment step. If the test fails, the CI blocks the commit — but shipping disabled is no longer the default.

**X.5 — Replace exception-swallow with crash-telemetry.** `run()` wraps in try/except, but on catch: (a) log to stderr with full traceback, (b) surface a `error: 1` counter in `traderData` that's read at next tick, (c) if 3+ errors in 100 ticks, halt the strategy and flatten — the kill-switch. Don't silently emit empty orders indefinitely.

### Tier Y — new alpha primitives (built on Tier X foundation)

**Y.1 — OBI-based predictive fair-value estimator.** New `Estimator` impl. Features: `book_imbalance`, `microprice - mid`, `recent_trade_imbalance` (signed volume last N trades / total). Target: mid at t+50 / mid at t+200. Train offline via linear regression (no scipy — np.linalg.lstsq inline). Ship weights as config constants. Realized IC probably 0.05-0.12 on 3 tested products.

**Y.2 — Counterparty state-space model.** Per-counterparty-id rolling features → HMM with 3 states {informed, MM, noise} → per-counterparty posterior updated every trade. Fair-value tilt: `tilt = Σ_i P(informed_i) × sign(recent_trade_i)`. This is F5 closing and hidden-alpha A1 in one engine.

**Y.3 — Lead-lag cross-product predictor.** Compute 5k-tick cross-correlation of 1-step returns for every pair. For pairs with |ρ| > 0.15: the lagging product gets a new fair-value component = `ρ · σ_lagger · z(leader_return)`. Auto-generated per tick. This closes F4.

**Y.4 — Counterfactual fill-model calibrator.** Take 3 published P3 top-team repos. Run their code through your backtest at `passive_allocation ∈ {0.05, 0.10, 0.15, 0.20, 0.30, 0.50}`. Find the value that reproduces their published P&L. That's your true fill rate. Update `fill_model.py`. All historical tuning gets re-validated under the real fill number. Closes F7.

**Y.5 — Regime-gated estimator selection.** Detect regime via (rolling σ, rolling trade-size std, book-depth-ratio). Bayesian ensemble weights different estimators per regime. In low-vol regime: wall-mid + anchor. In high-vol regime: microprice + OBI-predictor + flow-tilt. Closes F5 more deeply.

**Y.6 — Non-parametric regime HMM on bot order-book behavior.** Log per-bot quote-update cadence and size distribution. Run a Chow-test / CUSUM online. When structural break detected, flag regime change. Feeds Y.5 regime gate. This is the bot-fingerprint regime detection (A21) from the hidden-alpha atlas.

### Tier Z — the big bets (offline-trained, deployed as static artifacts)

**Z.1 — Neural order-flow predictor, exported as a 1KB matrix.** Train a 3-layer MLP offline on your replay data: input = 20 per-tick features (OBI, microprice-delta, trade flow, book-depth imbalance, recent-return at 5 lags, time-of-day, counterparty-mix vector), output = next-100-tick return. Export final weights as Python literals in a config module. Inference at run time is 2 matrix muls — no scipy, no sklearn at runtime. Target IC: 0.15-0.25.

**Z.2 — Contextual-bandit strategy selection.** For each (product, regime), maintain Thompson-sampled posterior over {Avellaneda-Stoikov, Cartea, Guéant, Pepper-v6, raw flow-predictor, OBI-ladder}. Pick the strategy whose posterior mean Sharpe is highest per tick. Online-updates from realized P&L per tick. Collapses F6 into a principled mechanism.

**Z.3 — Self-play adversarial backtester.** Simulate 5-10 top-team strategies (re-implemented from P3 public code) as competing agents. Run your strategy against them. Find the strategies that beat your current setup 60%+ of the time — those reveal edges your current code cannot see.

**Z.4 — Kyle's-lambda per counterparty + optimal execution.** For each counterparty, estimate permanent vs transient impact of their orders. Use to (a) predict their next trade's price impact, (b) size your own orders to minimize YOUR market impact. Real-world MM infra; zero P3 repo has it.

**Z.5 — Cross-edition regression harness + DP optimal execution.** Already in the catalog. Fires on R5 open. Linear Utility generated 2.1M shells from this in P2. Zero-cost if it doesn't work; asymmetric upside if it does.

### Tier Ω — the philosophy changes

**Ω.1 — Replace "plateau selection" with "max-rank-P&L selection."** New sweep objective: simulate rank under assumed field distribution (fit from P3 leaderboard), pick hyperparameters that maximize **expected rank payoff**, not Sharpe. This rewards the YOLO-Olivia-style tail alpha.

**Ω.2 — Budget a "research-vs-infra" split per round.** Your codebase is ~37k lines; probably 70-80% infra. Top-team codebases are 70-80% alpha research (ugly + fragile but full of signal exploration). Reverse the ratio starting R3. Every new Tier Y / Z item competes for priority against infra improvements.

**Ω.3 — Every alpha needs a kill-switch and a counterfactual, not a test.** Tests prove correctness. But an alpha's job is to produce P&L; the check is *realized Sharpe vs counterfactual (no alpha)*. Ship A/B telemetry per alpha from day 1. Disable an alpha that's -2σ below its backtest prediction for 5k ticks.

---

## 6. What I want to verify empirically — not speculate

Before committing the Tier X/Y/Z build, run these diagnostics:

1. **F7 calibration.** Run top-team P3 code through your backtest. Find the fill-allocation that reproduces their published P&L. If it's not 0.3, all historical numbers are biased.
2. **F1 IC test.** On R1/R2 replay, compute per-tick `flow_score` (already persisted). Regress realized next-100-tick returns. Report IC. If > 0.03, **F1 is a confirmed 1-2k/day leak**.
3. **F4 pair test.** On R1/R2 replay, compute 1-lag cross-correlation matrix on all product pairs. Any |ρ| > 0.15 confirms F4 is real. Report.
4. **F2 A/B.** Flip `ResidualConfig.enabled=True` for R1/R2 replay. Compare baseline vs with-residual P&L across the 5 metrics your enablement gate requires. If green, F2 was a lockup.
5. **F5 counterfactual.** Add a *toy* predictor (`next_mid_pred = mid + 0.3 × book_imbalance`) to `FairValueEngine`, skew quotes by the delta, re-run R1/R2 replay. If P&L rises, F5 is a confirmed absence-of-signal leak.
6. **F8 selection bias.** Re-run R1/R2 sweep. Report: (a) hyperparameter at plateau-center, (b) hyperparameter at peak P&L. P&L gap between them. If > 500 shells, F8 cost you that.

**Budget: 1 day of diagnostics. Payoff: you know which failure modes are real vs speculative, and you can prioritize the Tier X/Y/Z build against evidence.**

---

## 7. Revised R3-5 build plan (contingent on diagnostics)

Assuming diagnostics confirm F1, F2, F4, F5 as the dominant leaks (most likely outcome):

**Week 1 (before R3):**
- Day 1: Run the 6 diagnostics. Lock in the failure-mode ranking.
- Day 2: Tier X.1 (SignalBus) + X.4 (residual flip) + X.5 (crash-telemetry). ~12h.
- Day 3: Tier X.2 (PortfolioContext extension) + X.3 (Bayesian ensemble). ~12h.
- Day 4: Tier Y.1 OBI predictor + Y.4 fill-model calibration. ~8h.
- Day 5-6: Tier Y.2 counterparty state-space + Y.3 lead-lag. ~16h.
- Day 7: Tier Y.5 regime-gated + Y.6 bot-fingerprint HMM. ~8h.
- **Plus the original Tier A engines** (basket, options, stat-arb) now built ON TOP of the inverted architecture, which means they pick up the new signals automatically.

**During R3-R5:**
- Tier Z built as dormant infra.
- Observe field behavior; flip Z.1 (neural predictor) on in R4 if trained on R3 live data.
- Tier Ω running from the first round — every alpha has A/B telemetry.

---

## 8. The honest bottom line

Your R1/R2 codebase is well-engineered. **That is part of the problem.** Well-engineered defensive systems protect you from downside; they don't capture upside. You built a Toyota. Top teams built Formula 1 cars — fragile, ugly, and on pole position.

Closing a 25% gap requires inverting several architectural defaults:
1. Signals must be causal, not observational.
2. Residual allocators must be on, not off.
3. Exceptions must crash, not hide.
4. Fair values must predict, not average.
5. Hyperparameters must maximize rank payoff, not stability.
6. Architecture must allow cross-product signals, not just per-product.

Do all six, plus the Tier A/B engines from the catalog, and you have a credible shot at closing the gap. Do only the Tier A/B engines and keep the Toyota architecture, and you'll build three sophisticated new features that your signals-to-decisions plumbing cannot fully exploit.

---

*Next action I recommend: **1-day diagnostic sprint (§6)** before any Tier X/Y/Z coding. The diagnostics are cheap, and the priorities they produce are load-bearing for everything else. Want me to draft the diagnostic harness?*
