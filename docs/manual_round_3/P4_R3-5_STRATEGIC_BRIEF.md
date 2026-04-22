# Prosperity 4 — R3 / R4 / R5 Strategic Brief

**Compiled:** 2026-04-22 (mid-R2 of P4).
**Sources:** P3 winners panel + P3 8th-place lecture + 7 top open-source repos (P1/P2/P3) + academic quant literature + first-principles forecast. Full research docs at the bottom.

---

## 0. TL;DR — what to do before R3 opens

**If you only read one section, read this.** Ordered by expected P&L impact per hour of prep:

1. **Build generic infrastructure, not product-specific bets.** Every top team won with reusable tooling (BS module, ETF z-score, take/clear/make, kill-switch). Don't over-commit to a single forecast.
2. **Pre-cache Prosperity 3 public data.** Linear Utility won P2-R5 by regressing P1-2023 prices against P2-2024 prices (R²=0.99 on two products). Top P4 candidate alpha: **P3 final-day prices → P4 R5 revealed paths.** Download P3 data now.
3. **Counterparty segmentation from R1 data.** The "Olivia" signal (18/18 perfect tops/bottoms in P3) was visible from R1 via P&L curve + position pattern. **Every team should be segmenting bots by P&L trajectory starting R3.** Top teams had ~200k head start by R5 from this alone.
4. **Do NOT delta-hedge options if spread cost > gamma P&L.** P3 top team paid ~$50k/day in spread cost vs ~$16k unhedged delta exposure — 3× destructive. Drop hedging entirely or use Whalley-Wilmott no-trade band.
5. **Build a production Black-Scholes with inline `norm_cdf`** (Abramowitz-Stegun). scipy is blocked. Do this regardless of whether R3/R4 has options.
6. **Memory discipline in `traderData`.** chrispyroberts (1st USA P3) got wiped from 7th → 241st when Jasper's visualizer ate 100MB and erased his rolling windows. Cap state size explicitly.
7. **Pre-build a news-triage LLM pipeline** — JSON-schema output + rule-based sanity filter + per-event risk cap. R5 manual is guaranteed to be news-driven.

---

## 1. The cross-edition arc (what R3/R4/R5 almost certainly contain)

Three editions of evidence. The skeleton is stable; the novelty-per-edition is grafted on.

| Round | P1 (2023) | P2 (2024) | P3 (2025) | **P4 forecast** |
|---|---|---|---|---|
| **R3** | ETF basket (premium=375) | 1 basket (premium~370) | **2 baskets** + volcanic rock + 5 vouchers | 2-3 baskets, overlapping/nested constituents, OR multi-expiry options |
| **R4** | (R4 was baskets) | Long-dated options (250d) + orchid cross-island arb | Weekly options + macaron cross-island arb (2 things packed) | Either multi-expiry options + stat-arb, OR perp/futures + multi-signal cross-exchange |
| **R5** | Trader Olivia reveal, no new products | Trader IDs inferred, no new products | Trader IDs revealed, no new products, news-sentiment manual | **Trader IDs revealed + news manual + cross-edition regression alpha** |

**Consensus forecast confidence:**
- R3 = basket arbitrage (possibly 3 baskets or nested): **8/10**
- R4 = options (multi-expiry novelty) AND/OR cross-exchange arb: **8/10**
- R5 = no new products + trader IDs + news manual: **9/10**
- R5 cross-edition regression (P3→P4) alpha exists: **6/10** — high EV if it does

See [forecast_creative.md](forecast_creative.md) for LOW-CONFIDENCE creative possibilities (0-DTE, variance swaps, AMMs, perpetuals with funding).

---

## 2. Round-by-round playbook

### 2.1 Round 3 — most likely ETF/basket (with or without options)

**Mechanic (high confidence):**
- 2+ baskets over shared constituents. Spread `B − Σ wᵢ Cᵢ` mean-reverts around a constant premium.
- Possible novelty: a 3rd basket, or overlapping-constituent baskets (rank deficient → SVD to find the real arb axis), or a basket containing an option (P3 winners panel explicitly flagged basket-option combos as a natural next step).

**Winning approach:**
- Spread-arb z-score: entry `|z| > 2.0`, exit `|z| < 0.3`, kill `|z| > 4.0`.
- **Hysteresis sizing.** Enter proportional to spread width, exit asymmetrically (Dave Nandi's "leaf" pattern — P3 panel). Linear exit erodes profit; tight exit preserves it.
- Pick the spread that's cleanest visually AND passes ADF p<0.05 AND has half-life τ < 10% of session.
- **Residual budget (8-10% of book):** market-make the leftover. Transcript 1 speaker got $5k/day extra from this; "don't leave money on the table."
- If 2+ baskets: P3 top teams split — chrispyroberts traded premium-vs-constituents, transcript-1 team traded premium-of-B1 vs premium-of-B2. **Both work, with different position-limit trade-offs.** Check your limits first.
- Frankfurt (P3 top-3) variant: **informed-trader detection.** Track max/min trade sizes; a large print = informed flow, piggyback.

**Pre-built before R3 opens:**
- [ ] Z-score spread trader (take/clear/make template)
- [ ] ADF test helper (import statsmodels or inline an Augmented-DF)
- [ ] Rolling deque-based mean/std (O(1), max-len 1000)
- [ ] Hyperparameter sweep → heatmap → pick (highest PnL + flattest neighborhood)

### 2.2 Round 4 — most likely options OR stat-arb (or both, P3-style)

**Mechanic (options scenario, high confidence):**
- Multi-strike calls (± the ATM). P4's likely twist: **multiple expiries** (P3 was single 7-day expiry → P4 grades term-structure + calendar).
- Expect 3-5 strikes per expiry, 2-3 expiries.

**Winning approach (options):**
- Fit IV smile per expiry: `m = ln(K/S)/√T`, quadratic fit OR rolling mid-IV window. P3 top teams upgraded quadratic → rolling window mid-round when quadratic stopped tracking (80k → 200k/day).
- **Trade IV, not price.** Buy when IV_obs < IV_fit − 1σ_residual; sell when above.
- **Do not delta-hedge** unless spread cost per round-trip < gamma P&L per step. Math: in 1-wide-spread book, hedge bleed ≈ theta earned. Drop it.
- If you must hedge, use Whalley-Wilmott no-trade band: `Δ_band ∝ (λΓ²S²)^(1/3)`. Hedge only at band crossings, not every tick.
- **IV scalping at ATM strike** (P3 TimoDiehm / transcript-1 winner's panel): neg 1-lag autocorr in IV → lightweight mean-reversion with fast EMA. 100-150k/day standalone.
- **Gamma scalping** only works when spread cost < ½·Γ·S²·(σ_RV² − σ_IV²)·dt. Usually doesn't pencil in tight-spread sim. Skip unless your RV/IV ratio > 1.15.

**Mechanic (stat-arb scenario):**
- Cross-exchange product with external signal (sunlight, sugar, or novel: weather + import quota, etc.).
- Hidden aggressive-buyer bot (P3 macaron pattern) often present — yields ~1.4 shells × 100k trades ≈ 146k for free if you find it.

**Winning approach (stat-arb):**
- **First: test the no-arb boundary.** `sell_local_BE = conv_ask + import_tariff + transport`. Arb any local_bid > BE.
- **Batched conversions.** If conv_cap = 10/tick, sell 30/tick to maintain stockpile. Transcript-1 team AND #2 team BOTH missed this in P3 — "doubles your P&L."
- **Probe for hidden liquidity.** Quote at `int(external_mid ± 0.5)` and check fill rate. Empirically calibrate the price level that attracts bot flow.
- External signal (sunlight etc.): treat as a **regime flag, not a linear regressor**. "Low sunlight → squeeze, accumulate." Percentile over 100-day window, <25th pct = squeeze, >75th = glut. A 99% R² linear fit is the sign of overfitting.
- Keep arb P&L and signal P&L as separate streams; blend only at the risk budget.

**Pre-built before R4 opens:**
- [ ] Inline `norm_cdf` (Abramowitz-Stegun) — verified against Python's scipy reference locally
- [ ] IV solver (Brent / bisection) with log-moneyness scaling
- [ ] Rolling smile fitter with graceful degradation to plain mid-IV window
- [ ] Conversion break-even calculator with symbolic tariff handling
- [ ] Jump detector: `|r_t| / EWMA(|r|, 500) > 4.0` → halt short-gamma

### 2.3 Round 5 — trader IDs + news manual + cross-edition alpha

**Mechanic (near certain):**
- No new products.
- All counterparty IDs become public.
- News-sentiment manual puzzle with quadratic trade-size fee (P3 used `120·x²`; optimum ~83% allocation).

**Winning approach — three independent edges:**

1. **Counterparty flow detection (the Olivia signal).**
   - Segment all IDs by P&L trajectory:
     - Flat-line-up P&L + large position swings = **informed** → copy direction
     - Consistent flat P&L despite volume = **market maker** → ignore (copying = guaranteed loss, they make on spread)
     - Losing money overall + high volume = **noise/retail** → trade against
   - The informed trader is usually named after an IMC employee ("Olivia" in P1/P2/P3). In P3 she had 18/18 perfect tops/bottoms across 3 products × 3 days.
   - **Detect her from R1, not R5.** Top teams had ~200k head start from Olivia-copying starting R2 onwards. Don't wait for IDs — segment from R1 using P&L curve clustering.
   - **YOLO the signal when you find it.** P3 chrispyroberts and transcript-1 team both abandoned their stat-arb algos and went full Olivia-direction on CROISSANTS, accepting residual basket exposure. P&L from copying > P&L from own algo.

2. **Cross-edition regression (the Linear Utility alpha).**
   - P2-R5 winner regressed P1-2023 final prices against P2-2024 prices. Found R²=0.99 on two products: `diving_gear_2023 × 3 → roses_2024`, `coconuts_2023 × 1.25 → coconuts_2024`.
   - Built a **dynamic-programming optimal-execution** algo over the known price path with position-limit and available-volume constraints. Generated 2.1M shells in R5 alone — highest in field.
   - **P4 candidate alpha:** the moment P4-R5 reveals price paths, run the same regression against P3 final-day public data. High-R² matches = known-future execution problem. Pre-build the DP solver.

3. **Manual R5 quadratic-fee allocation.**
   - Portfolio allocate % across ~10 products given news articles. Fee quadratic in per-product allocation → optimum NOT 100% on best pick.
   - P3 optimal total allocation ≈ 83% (fee = `120·x²`).
   - Map products 1:1 to prior-edition analogues; trust the mapping's magnitude estimates, don't soften them (transcript-1 team softened cacti −65% prediction and regretted it).
   - Solve as constrained optimization (cvxpy). chrispyroberts used this in P3.

**Pre-built before R5 opens:**
- [ ] Counterparty P&L attribution + K-means cluster on (P&L trajectory, volume, win-rate)
- [ ] cvxpy portfolio-allocation optimizer with quadratic fee
- [ ] Cross-edition regression helper with R²-threshold and residual-autocorr sanity checks
- [ ] DP-over-known-path optimal execution with position-limit constraints

### 2.4 Ratchet & correlated-risk discipline

Kelly under rank-based tournament scoring is **not** log-wealth Kelly:

- Below leaderboard threshold → **increase variance** (more than full Kelly). Gamble-to-catch-up is correct under rank payoff. P3 top-USA team "doubled down to gamble" when they fell behind — mathematically correct.
- Above threshold → **cut to half-Kelly or less.** TimoDiehm (top global P3) explicitly "kept parameters conservative after building a 190k lead." Defensive mode wins when ahead.
- Before R5: **factor-expose audit.** Are all your strategies short vol? Long one basket? A single news release can liquidate a whole class simultaneously. Diversify across factor exposures, not just products.

---

## 3. Critical lessons from P3 top teams

### What actually worked

1. **Simple > complex.** chrispyroberts's basket trader was 5 lines of core logic. "The real work is hours of verified helpers around 5 lines of trading logic." Complexity in infrastructure, not strategy.
2. **One hyperparameter, stable neighborhood.** Pick params where highest P&L coincides with flat derivative (low overfit risk). Heatmap + manual inspection, not grid-optimum.
3. **Penny-jumping in the sim.** Quote one tick inside best — bots see your orders, trade on them, orders go away. NO team can front-run you. Works in sim, does NOT work in real crypto (transcript-1 speaker tested).
4. **Position-reducing at fair value.** When at position limits, accept fair-value trades to unlock future spread capture. "The one most teams missed."
5. **Take/clear/make execution.** Every top-3 team across P2/P3. Take crossing orders → clear outstanding hedges → market-make residual.
6. **Wall-mid pricing > simple midpoint.** Less manipulable on thin books.
7. **Fair-value probe trick.** Buy at known price, measure P&L to infer IMC's exact mid formula (P3 confirmed: mid of best_bid and best_ask, not last-trade). Run this on every product.

### What failed (and why)

1. **Delta-hedging in tight-spread books.** chrispyroberts paid ~$50k/day, had ~$16k unhedged loss. ~100× destructive.
2. **Over-fitted quadratic IV smile.** Fit broke day-to-day. Degrades to rolling window late in competition.
3. **Visualizer state overflow.** Jasper's open-source visualizer had a 100MB memory issue that wiped rolling windows in submission. **Verify submission path independently.**
4. **Linear regression on sunlight with 99% R².** Tell-tale of lookahead / leakage. Regime flags > continuous regression.
5. **Gamma scalping in 1-wide spread.** Spread cost dominates gamma edge.
6. **Collapsing the manual-round distribution.** Picking argmax under your own simulated prior is exploitable. Better to roll the dice on a mixed strategy.
7. **Treating position limits as non-binding.** Two strategies that line up in the same direction during stress will compete for the same book slot. Need a portfolio position manager.

---

## 4. Infrastructure priorities (rank-ordered by ROI)

Pre-built before R3 opens — each deliverable should have tests:

| Rank | Deliverable | Research ref |
|---|---|---|
| 1 | **Take/clear/make execution scaffold** — reusable per product | Prior editions §5 |
| 2 | **Inline `norm_cdf` + Black-Scholes module** — A&S approximation | Academic §1 |
| 3 | **Rolling deque-based indicators** (mean, std, EMA, IV, z-score) with `maxlen` cap | Prior editions §5 |
| 4 | **Kill-switch on realized drawdown + jump detector** | Creative §4, Academic §1.4 |
| 5 | **Counterparty-segmentation module** — P&L clustering from tick 0 | Transcript 1 §5, Prior §1f |
| 6 | **Z-score spread trader template** w/ hysteresis sizing | Academic §2.1-2.2 |
| 7 | **IV smile fitter with graceful degradation** (quadratic → rolling mid-IV) | Academic §1.2 |
| 8 | **Conversion break-even calculator** (symbolic tariffs) | Academic §3.1 |
| 9 | **News-triage LLM pipeline** (JSON schema + sanity filter + risk cap) | Creative §3.4 |
| 10 | **cvxpy quadratic-fee portfolio allocator** (manual R5) | Prior §1d |
| 11 | **Cross-edition regression helper + DP execution solver** (R5 alpha) | Prior §1b |
| 12 | **Submission bundle pre-commit hook** (tests, diff config JSON, human "y" gate) | Creative §4.5 |
| 13 | **Symbol constant module with fail-fast** | Creative §4.6 |
| 14 | **`traderData` size budget enforcer** | Prior §5.7 |
| 15 | **OOS held-out validation** (last day of replay reserved) | Creative §4.4 |

Generic infrastructure pays off regardless of which specific products land.

---

## 5. Meta-strategy & workflow

**Team:**
- Diverse skills: dev building tooling, quant with options intuition, analyst watching order book (P3 winners panel).
- Code-submitter MUST sleep 2-3 hours before submission. "You don't want someone sleep-deprived submitting a random thing."
- Everyone writes Python; critical thinking is the real bottleneck.

**Discord / community:**
- Dave + JK are trustworthy moderators. Everyone else ~50/50.
- Fake P&L charts and deepfake screenshots are common. **Cap community-signal prior weight ≤15%** (our F4 rule from P4-R2 post-mortem).
- Reverse-engineer legitimate posts: when P&L charts look believable, infer the trade timing from the chart shape.

**AI discipline:**
- Use AI for helper functions you can verify — never one-shot the full algo.
- "If you pass my code to Claude and say 'make it for this round,' it's going to break on anything different — Claude can't see data or backtest results." (Transcript 1 speaker)

**Submission discipline:**
- Tag every submission as `round-N-final-YYYYMMDD-HHMM`.
- Verify the submission path is independent from Jasper's visualizer (the 100MB bug exists).
- Run a diff-config dump and a human-y pre-commit gate.

---

## 6. Manual round readiness

Cross-edition manual archetypes (all will likely recur):

| Archetype | Appearance | Framework |
|---|---|---|
| Graph / FX cycle | P1 R1, P2 R1 | Bellman-Ford / LP — trivial |
| Tile picker w/ crowd penalty ("crowding") | P2 R3, P3 R2, P3 R4, **P4 R2 (done)** | Already in `src/manual_rounds/` |
| Sealed-bid auction | P2 R4 | `src/manual_rounds/bid_optimizer.py` |
| Hybrid bid w/ avg-bid coupling | Manual round agent brief | `src/manual_rounds/hybrid_bid.py` |
| News portfolio w/ quadratic fee | P3 R5 | cvxpy — **need to template** |
| (NEW) Auction mechanism design | Never used | `forecast_creative.md §3.1` |

**Manual-round calibrated lessons (from our own P4-R2 post-mortem, retained in [CLAUDE.md](../../CLAUDE.md)):**
- M1 — μ-ceiling sanity check; M2 — R×S dominates μ near optimum; M3 — tie-share wells; M4 — enumerate (r,s,v) isoquants.
- F1 — AI aggregate priors overshoot real field by 2-4 integers; F2 — look for density band, not point cluster; F3 — fields are bimodal (naive-low + smart-band + tail); F4 — community polls ≤15% weight; F5 — don't conflate round populations.
- P1 — when sub-models disagree, regress downward; P2 — Bayesian EV and minimax both overshoot; P3 — reconstruct before declaring.
- **Always run the μ-ceiling check before committing.** We overshot in P4-R2 by 8 integers; this would have flagged it.

---

## 7. The P4-R5 cross-edition regression play (highest-EV single bet)

**Hypothesis.** IMC reuses final-day price paths from prior editions as scaffolding for R5 revealed paths. Linear Utility exploited this in P2 (R²=0.99 on two products). P3 probably used P1 or P2 data. **P4 R5 will likely have regression links to P3 final-day prices.**

**Pre-work (do NOW, before R3 opens):**

1. Download all P3 final-day public price data. All 5 rounds' final CSVs. Store in `data/raw/prosperity_3/`.
2. Build a regression harness that accepts `(P3_series, P4_revealed_series)`, computes OLS / ridge, reports R², residual autocorr, best scale factor.
3. Build a DP optimal-execution solver: given a known future price path, position limits, available volume per tick, and bid/ask spreads, compute optimal trade schedule.
4. The moment P4-R5 reveals any price path: fire the regression against every P3 series. Anything R² > 0.9 → execute DP schedule with full risk budget.

**Confidence:** 6/10 this specific alpha exists. Low cost to prepare. If it exists, it's a 1M+ shell round-over-round P&L differential.

---

## 8. What NOT to do

- Don't delta-hedge options in a 1-wide-spread book.
- Don't fit a quadratic smile and trust it for multiple days — it breaks.
- Don't trust Jasper's visualizer submission path without independent verification.
- Don't copy market makers (guaranteed loss on spread) or trade against informed traders.
- Don't over-weight community priors (<15% cap).
- Don't pick manual-round argmax under your own simulated prior — play mixed.
- Don't run linear regression on an external signal with 99% R² and assume it generalizes.
- Don't hold short gamma across a round boundary or through an unhedged gap-risk window.
- Don't soften your magnitude predictions when mapping products to prior editions.
- Don't let two strategies consume the same book's position limit in the same direction — need a portfolio manager.
- Don't use `scipy` — blocked. Inline approximations only.
- Don't use `list.pop(0)` for rolling windows — use `collections.deque`.
- Don't let `traderData` grow unbounded — explicit size budget.

---

## 9. Reference map

Full research output (this repo):

- **[forecast_creative.md](forecast_creative.md)** — first-principles speculation on P4 R3-5 products (multi-expiry options, nested baskets, perpetuals, auction crosses, adverse-selection regimes, AMMs). Each scenario scored 1-10.
- **[research_prior_editions.md](research_prior_editions.md)** — 7 top-team repos (P1 Stanford Cardinal; P2 Linear Utility, jmerle; P3 chrispyroberts, Alpha Animals, TimoDiehm, Sylvain-Topeza). Full round-by-round table across P1/P2/P3. Architectural patterns.
- **[research_academic_quant.md](research_academic_quant.md)** — Sinclair, Gatheral-Jacquier SVI, Whalley-Wilmott no-trade band, Avellaneda-Stoikov, Kothari-Warner event study, Lazear-Rosen tournament Kelly. Threshold cheat-sheet.
- **[transcript_1_extracted.md](transcript_1_extracted.md)** — P3 8th-place finisher's 90-min post-mortem lecture. Specific failure stories, exact P&Ls, calibrated priors.
- **[HANDOFF_CONTEXT.md](../manual_round_2/HANDOFF_CONTEXT.md), [LESSONS_LEARNED.md](../manual_round_2/LESSONS_LEARNED.md)** — our own P4-R2 post-mortem (retained in CLAUDE.md M1-M4/F1-F5/P1-P3/W1-W2 blocks).

Transcript 2 (P3 winners panel with Dave Nandi, Anand, Rishi, Sedat) is consumed inline above; not re-exported.

---

## 10. Single-page action list (tear-out)

**Before R3 opens:**
- [ ] Download P3 final-day data + P2 data; build regression harness
- [ ] Cache Jasper's backtester BUT verify submission path independently
- [ ] Production BS module with inline `norm_cdf`
- [ ] Take/clear/make scaffold
- [ ] Rolling deque indicators (mean, std, EMA, z-score), maxlen=1000
- [ ] Kill-switch: halt on realized drawdown > X OR jump-detector ratio > 4.0
- [ ] Counterparty P&L tracker + clustering (run from R3 tick 0)
- [ ] cvxpy quadratic-fee allocator (manual R5 template)
- [ ] DP optimal-execution solver (R5 alpha)
- [ ] Submission bundle pre-commit hook (test + diff + "y" gate)
- [ ] Symbol constant module
- [ ] `traderData` size budget (hard cap, fail-fast)
- [ ] OOS validation: last day of replay reserved

**During R3 (basket / options arb):**
- [ ] ADF + half-life sanity check on any spread before trading
- [ ] Z-score entry 2.0 / exit 0.3 / kill 4.0
- [ ] Hysteresis sizing — asymmetric entry/exit
- [ ] Residual position budget 8% for market-making leftover
- [ ] Counterparty segmentation already running
- [ ] NEVER delta-hedge in 1-wide spread without Whalley-Wilmott check

**During R4 (options / stat-arb):**
- [ ] IV fit with graceful degradation (quadratic → rolling mid-IV)
- [ ] `int(external_mid + 0.5)` fill probe on cross-exchange products
- [ ] Batched conversions (3× conv_cap) not naive single-unit
- [ ] External signal = regime flag, not linear regressor
- [ ] Factor-exposure audit before R5

**During R5 (reveal + news):**
- [ ] Counterparty IDs now visible → confirm R3/R4 cluster detection
- [ ] Fire cross-edition regression against P3 final-day data
- [ ] Execute DP schedule if any R² > 0.9
- [ ] YOLO Olivia's direction if detected
- [ ] Manual allocation at ~83% of portfolio (quadratic fee)
- [ ] **Ratchet discipline:** if ahead, cut variance; if behind, raise it

---

*Everything above derives from primary sources: P3 winners panel, 8th-place lecture, 7 top open-source repos, academic literature, and our own P4-R2 post-mortem. Every claim should be traceable to one of the four research docs.*
