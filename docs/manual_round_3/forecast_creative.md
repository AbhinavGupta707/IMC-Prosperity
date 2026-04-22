# P4 R3/R4/R5 Creative Forecast

Forward-looking first-principles speculation. Every scenario is anchored in
a P1/P2/P3 archetype or a real-market analog. Hot-takes are tagged
`LOW-CONFIDENCE:`. Confidence scores are on a 1–10 scale where 10 = "bet the
farm this will appear verbatim" and 1 = "amusing but unlikely."

---

## 1. Extrapolation from the arc — likely additions

### 1.1 Options R3: multi-expiry surface instead of single-expiry ATM/OTM grid

- **Mechanic.** Not one week-expiry underlying with five strikes (P3), but
  2–3 expiries × 3–5 strikes on the same underlying. A term structure +
  skew surface to arbitrage. Possibly a synthetic-forward / put–call
  parity pair at each expiry.
- **Why IMC.** P2 introduced long-dated coconut options; P3 made them
  weekly + multi-strike. The natural next step is multi-*expiry*, which
  lets them grade on vol-surface calibration, calendar spreads, and
  forward-vol consistency rather than just one skew curve.
- **Winning approach.** Fit a parametric surface (SVI or SABR-lite) across
  strikes per expiry, then enforce calendar-arbitrage-free forward vols
  across expiries. Trade when local quotes drift off-surface. Size by vega
  rather than delta. Crucially: net-vega limit across the surface, not per
  leg.
- **Confidence: 7/10.**

### 1.2 Options R3: 0-DTE / intraday expiry as a second product

- **Mechanic.** A daily-expiry option that expires at end-of-day, on top
  of the weekly options from P3. Short half-life — gamma explodes into
  the close.
- **Why IMC.** Dave Nandi is an options quant; 0-DTE is the hottest topic
  in real-world equity derivs since 2022. It grades skill at gamma
  management under decay, not just direction.
- **Winning approach.** Quote tight, trade small, fade flow into the
  close when theta accumulates, but cap inventory hard — *never* be net
  short gamma through the last few ticks. Treat as a market-making game
  with explicit inventory-at-expiry penalty.
- **Confidence: 5/10.** (Real-market relevance is huge, but simulator
  mechanics may not support sub-day expiry cleanly.)

### 1.3 LOW-CONFIDENCE: variance swap / realized-vol product

- **Mechanic.** A product whose payoff = Σ(log-return²) over the round
  window, quoted as "implied variance points." Not an option but a
  variance forward.
- **Why IMC.** Teaches the difference between price and vol exposure;
  natural extension once options exist. Real-market analog is clear.
- **Winning approach.** Replicate via a log-contract portfolio of options
  across strikes, hedge delta continuously, capture the vrp.
- **Confidence: 2/10.** (Too exotic for a manual-simulator game. Listed
  for completeness.)

### 1.4 Baskets → nested / 3-basket / basket-vs-future

- **Mechanic.** Either (a) three ETFs with overlapping constituents
  (exposes cross-basket redemption arb), (b) a basket whose constituents
  include *another* basket (nested), or (c) a basket that also has a
  futures contract referencing the same NAV, so you arb ETF vs future
  vs constituents.
- **Why IMC.** P2 had one basket; P3 had two disjoint baskets. The
  pattern is clearly "keep adding baskets and/or relate them." Overlap
  or nesting is the obvious escalation.
- **Winning approach.** Build the full replication matrix up front
  (rank of constituents vs baskets), pick the cheapest replicating
  portfolio each tick, and use SVD to detect which "edge" is the
  actual arb vs collinear noise.
- **Confidence: 7/10** for more-baskets; **4/10** for nested specifically.

### 1.5 Exchange-arb signal with two external signals (Macaron++)

- **Mechanic.** A product priced off *two* correlated external indicators
  (not just sunlight; e.g., sunlight + humidity, or sunlight + a leaked
  import-quota series). One of them is noisy or has a regime-switch.
- **Why IMC.** P2/P3 each had one exchange-arb product with one
  exogenous signal. Adding signals grades multivariate regression
  skill, feature engineering, and noise-robustness.
- **Winning approach.** Ridge-regression both signals against fair
  value, with a rolling-window refit; add a gating rule to detect
  regime change (signal 1 decoupling from signal 2 → step back).
- **Confidence: 6/10.**

---

## 2. Orthogonal novelty — creative additions

### 2.1 Perpetual futures with funding rate

- **Mechanic.** A perpetual contract on an existing underlying, with
  a funding rate paid every N ticks based on (perp – spot) basis.
  Long funding when perp > spot, short funding otherwise.
- **Why IMC.** Perps are the dominant real-market crypto-derivative and
  have never appeared in Prosperity. They're a natural evolution of
  the "basket vs constituents" basis-arb pattern.
- **Winning approach.** Classic cash-and-carry: if funding is
  materially positive, short perp + long spot, collect funding. Size
  by funding-rate sharpe over the lookback. Beware regime flips near
  round boundaries.
- **Confidence: 4/10.** (IMC has leaned agri/soft-commodity flavor, not
  crypto, but the mechanic is generic.)

### 2.2 Time-varying position limits / position-cost holding fee

- **Mechanic.** Limit shrinks over the round (forcing wind-down), *or*
  a per-tick holding fee proportional to |position|. A "storage cost"
  or "capital charge."
- **Why IMC.** P3's Magnificent Macarons already had a per-unit storage
  cost on long inventory. Generalizing this to *all* products — or
  making it asymmetric (cost long, no cost short) — grades inventory
  discipline.
- **Winning approach.** Every strategy gets a mandatory inventory-decay
  term in its objective. No more "hold through the dip." Calibrate
  half-life = ln(2) / fee_rate.
- **Confidence: 6/10.** (Variant likely; exact form uncertain.)

### 2.3 Opening / closing auction cross

- **Mechanic.** First and last N ticks of the round are a batch auction
  — orders accumulate, cross at a single clearing price. Rest of the
  round is continuous.
- **Why IMC.** Mirrors real equity markets and is a clean test of
  mechanism understanding. Rewards teams that model auction indicative
  prices separately.
- **Winning approach.** Submit IOI-style orders in the imbalance window,
  but never a market order at the cross — always a limit at a
  conservative indicative price. Arb the cross against the continuous
  session if both exist.
- **Confidence: 3/10.** (Elegant but implementation-heavy for IMC.)

### 2.4 Adverse-selection / "informed flow" regime

- **Mechanic.** Counterparties become informed under certain conditions
  (e.g., when signal X crosses a threshold) — their aggression
  temporarily predicts direction. Naive market makers get run over.
- **Why IMC.** P3 already hinted at this with the Squid Ink
  volatility regime. Making it explicit and signal-triggered raises
  the bar on adverse-selection awareness.
- **Winning approach.** Skew the quote based on recent toxicity: if
  hit-rate on one side > threshold, widen or quote single-side. A
  Glosten-Milgrom-style Bayesian update of the "probability
  counterparty is informed."
- **Confidence: 5/10.**

### 2.5 LOW-CONFIDENCE: limit-up / limit-down circuit breakers

- **Mechanic.** If price moves more than X% in N ticks, trading halts
  for M ticks.
- **Why IMC.** Teaches gap-risk and queue position. Real-market analog
  clear.
- **Winning approach.** Use halts as free information — after a halt,
  the next session open is informationally rich. Never have big
  positions going into a halt trigger.
- **Confidence: 2/10.** (Fun but adds simulator complexity.)

### 2.6 LOW-CONFIDENCE: AMM / constant-product pool

- **Mechanic.** A pool where price = f(reserve_x, reserve_y);
  participants trade against the curve and pay a fee that accrues
  to LPs.
- **Why IMC.** Very creative, grades understanding of impermanent
  loss. But stylistically off-brand.
- **Confidence: 1/10.**

---

## 3. Manual round creative angles

### 3.1 Auction mechanism design (new family)

- **Mechanic.** Instead of "allocate across pillars," players submit
  *bids* in a sealed-bid auction (first-price or second-price). Payoff
  tied to winning certain item combinations. Could include
  combinatorial auctions.
- **Why IMC.** Never used. Tests understanding of revenue equivalence,
  winner's curse, and optimal shading.
- **Winning approach.** For first-price: shade by (n−1)/n of signal
  mean; for second-price: bid truthfully; for combinatorial: solve
  the LP relaxation of the winner-determination problem and back out
  a bid vector.
- **Confidence: 4/10.**

### 3.2 Bayesian signaling / cheap talk

- **Mechanic.** Each player gets a private signal about a state; they
  publicly "announce" a message before choosing an action. Payoff
  depends on everyone's actions + state.
- **Why IMC.** Natural extension of news-portfolio archetype; grades
  information aggregation.
- **Confidence: 3/10.**

### 3.3 Matching market / stable-matching

- **Mechanic.** N players, N resources, submit preference rankings;
  assignment is done by deferred-acceptance. Payoff = value of
  assigned resource.
- **Why IMC.** Tests Gale-Shapley and truth-telling under strategy-proof
  mechanisms.
- **Confidence: 2/10.** (Niche, but one-shot manual rounds love niche.)

### 3.4 News round: structured JSON vs unstructured prose

- **Machine-parse approach (structured).** Pre-build a parser skeleton
  that handles the announced schema. Map each field to a pre-computed
  reaction in a lookup table. 3-day turnaround becomes feasible.
- **LLM-triage approach (unstructured).** Ship the prose through an
  LLM with a strict JSON-output schema (tickers mentioned, sentiment
  sign, magnitude class). Combine with a rule-based sanity filter. Cap
  any single-news impact at a pre-set risk budget.
- **Meta-defence.** Assume adversarial news — at least one release is
  a decoy/trap. Never let one news item uncap risk.

### 3.5 LOW-CONFIDENCE: repeated game / reputation

- **Mechanic.** Same opponents across multiple manual sub-rounds;
  cooperation vs defection with memory.
- **Confidence: 2/10.**

---

## 4. Meta-defences (risks to prepare for regardless)

1. **Gap-move catastrophe (P3-R3 launch analog).** Never be unhedged
   short gamma across a round boundary or a halt trigger. Hard kill-
   switch on realized P&L drawdown > X.
2. **Regime-shift whipsaw.** EMA-band / mean-reversion strategies
   blow up in trending moves. Gate every MR strategy on a trend-strength
   filter (ADX-like) and disable during strong trends.
3. **Fake Discord / deepfake P&L.** Cap community-poll prior weight
   ≤15% (F4 from P4-R2 lessons). Treat any "leaked" screenshot as
   adversarial. Never let community signals override quantitative
   evidence.
4. **Overfitting to cached replay data.** Hold out the last day of
   replay for OOS validation. If a param change looks too good on
   full-sample, re-check on held-out — if it disappears, discard.
5. **Submission bundle bug under time pressure.** Pre-build a
   pre-commit hook that (a) runs tests, (b) dumps the final config
   into a diffable JSON, (c) requires a human "y" to proceed. Label
   every submission branch `round-N-final-YYYYMMDD-HHMM` and tag.
6. **Off-by-one in instrument IDs.** Map every symbol to a constant
   module at load time; fail-fast if a symbol is missing from the
   config. Never let a typo in a symbol name silently route orders
   to a wrong product.
7. **Latency / tick-gap assumptions.** Don't assume uniform tick
   spacing. Index everything by `state.timestamp`, not tick count.

---

## 5. The one-bet-per-round asymmetry

P3 showed that R4+R5 aggregate PnL dominated final rank, because the
distribution of outcomes is heavy-tailed in later rounds.

- **Budget split (suggested).** Treat R1–R3 as *qualification* and
  *learning*; the goal is top ~15–20% cumulative, not top 1%. Reserve
  the bulk of the risk budget for R4 manual (if high-variance
  positional) and R5.
- **R5 is the big-bet round.** Historically R5 = all products + a
  news-based manual. The news manual can swing ±50k easily. Pre-
  build your news-parsing pipeline during R3/R4 so it's ready.
- **Ratchet discipline.** Every round, if you're comfortably in the
  cumulative leaderboard band you target, DECREASE variance next
  round (safer parameters, smaller positions). If you're below, you
  can selectively crank a single strategy.
- **Correlated-risk audit.** Before R5, check that your per-product
  strategies aren't all exposed to the same latent factor (e.g., all
  short vol). A single news release can liquidate a whole class of
  strategies simultaneously.

---

## 6. Creative combined-product plays IMC could introduce

### 6.1 Option on a basket (compound mispricing)

- **Mechanic.** A call on the P2-style basket NAV. Mispricing can come
  from (a) option mis-valuation vs basket vol, (b) basket mis-valuation
  vs constituents, or (c) both.
- **Why IMC.** Compounds two existing archetypes; very natural.
- **Winning approach.** Compute basket vol from constituent vols +
  correlation matrix, plug into BSM, trade the option only when edge
  exceeds basket-arb friction. Hedge with constituents, not the basket.
- **Confidence: 6/10.** (High probability if options return.)

### 6.2 Basket whose constituents include an option

- **Mechanic.** ETF NAV = weighted sum of (stock1, stock2, call_on_stock1).
- **Why IMC.** Forces teams to re-price the basket as option Greeks
  change. Realistic analog: convertible-bond index.
- **Confidence: 3/10.**

### 6.3 Tradable external signal (meta-game)

- **Mechanic.** In the P3 Macarons model, sunlight was an exogenous
  series. P4 variant: the signal itself is tradable — e.g., a
  "sunlight futures" product whose settlement is the sunlight
  reading, AND a second product priced off it.
- **Why IMC.** Introduces a principal-agent / reflexivity layer. Grades
  understanding of derivative pricing w.r.t. a tradable factor.
- **Winning approach.** Triangulate: signal-product fair value ↔
  signal realization ↔ downstream product fair value. Arb the
  implied-vs-realized basis on the signal product itself.
- **Confidence: 5/10.**

### 6.4 Stat-arb pair within single exchange

- **Mechanic.** Two volatile products whose mid-prices are covertly
  linked via a hidden factor (e.g., same news affects both, with a
  lag of N ticks on one).
- **Why IMC.** Lets them grade cointegration and lag detection. Less
  structurally imposed than baskets — the link is empirical, not
  definitional.
- **Winning approach.** Rolling cointegration test (Engle–Granger or
  Johansen-lite), build a spread, mean-revert on Z-score > 2. Gate
  on rolling half-life staying stable.
- **Confidence: 5/10.**

### 6.5 LOW-CONFIDENCE: FX triangle

- **Mechanic.** Three currencies A/B, B/C, A/C quoted simultaneously
  with a small triangular-arb window.
- **Confidence: 2/10.** (Off-brand for IMC's product universe.)

---

## Summary — highest-expected-value preparation

Rank-ordered by "prep time per unit of expected impact":

1. **Multi-expiry option surface + option on basket.** (1.1 + 6.1,
   combined confidence ~8/10 that *something* in this region appears
   in R3.) Pre-build an SVI-lite fitter + a basket-vol calculator.
2. **More baskets / overlapping baskets.** (1.4, 7/10.) Generalize the
   P3-R2 replication engine to N baskets and M constituents with
   overlap.
3. **Exchange-arb with multiple signals.** (1.5, 6/10.) Pre-build a
   multi-regressor + regime-change detector.
4. **Position-decay / holding cost generalization.** (2.2, 6/10.)
   Add an inventory-cost term to every strategy's objective now.
5. **News-round LLM triage pipeline.** (3.4.) Ship a JSON-schema
   prompt + rule-based sanity filter *before* R5 drops. This is
   the single highest-leverage pre-build.
6. **Meta-defences.** (§4.) Kill-switch, trend-filter gating,
   submission-bundle hook, symbol-constant module. All before R3.

The biggest mistake will be betting the whole prep budget on a specific
product forecast. Invest in *generic infrastructure* (fitters, kill-
switches, news-triage, symbol safety) that pays off regardless of
what actually lands.
