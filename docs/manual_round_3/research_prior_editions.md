# Prior-Editions Research: IMC Prosperity R3/R4/R5 Across P1, P2, P3

**Purpose:** Reference document for Prosperity 4 R3/R4/R5 preparation. All claims cited inline. Forecasts explicitly marked `SPECULATION:`.

**Date compiled:** 2026-04-22 (P4 currently mid-R2).

---

## 1. Top open-source repositories (all 3 editions)

### 1a. Prosperity 1 (2023) — Stanford Cardinal (Overall Rank 2)
- Repo: https://github.com/ShubhamAnandJain/IMC-Prosperity-2023-Stanford-Cardinal
- Products per round (R1 PEARLS/BANANAS → R2 COCONUTS/PINA_COLADAS → R3 BERRIES/DIVING_GEAR/DOLPHIN_SIGHTINGS → R4 BAGUETTE/DIP/UKULELE/PICNIC_BASKET → R5 revisit).
- Key parameters explicitly named in the README:
  - **PEARLS:** bid at `10000 - 1`, ask at `10000 + 1` (fixed fair value).
  - **BANANAS:** bid at `EMA - 1`, ask at `EMA + 1`.
  - **PINA_COLADAS / COCONUTS:** pair-trade `pina_colada - (15/8) * coconut` (~94% correlation observed).
  - **BERRIES:** hardcoded time-of-day pattern — "buy at timestamp 350k, sell at 500k, buy-or-sell at 750k depending on day trend" (seasonality / intraday cycle).
  - **DIVING_GEAR:** signal-filter on DOLPHIN_SIGHTINGS — shifts of `±5` = real signal, `±2` = noise.
  - **R4 Picnic Basket arb:** `basket − 4*DIP − 2*BAGUETTE − UKULELE − 375` (375 is the stationary premium).
  - **R5:** dropped component trades; kept only basket spread, Olivia-signal on UKULELE, Olivia-signal as **augment** to BERRIES. Explicitly avoided overfitting complex models.

### 1b. Prosperity 2 (2024) — Linear Utility (Rank 2, $10k prize)
- Repo: https://github.com/ericcccsliu/imc-prosperity-2
- R3 (Gift Baskets): spread `basket − synthetic` where `synthetic = 4*choc + 6*strawb + 1*rose`. Spread oscillated around **~370**. Evolved from hardcoded threshold (projected 120k PnL) → rolling-window z-score (projected 135k, realized 111k from slippage).
- R4 (Coconuts / Coconut Coupons): 10,000-strike call, 250-day expiry. IV oscillated around **~16%**. Delta ≈ **0.53**. Position limits: 300 coconuts / 600 coupons. Could not fully delta-hedge 600 coupons (would require 318 coconuts), held residual delta for higher variance. Realized 145k, dropped to rank 26 mid-round.
- R5 **breakthrough (the paper that got them to #2):** used the prior-year (2023) public data and discovered:
  - `diving_gear_2023 × 3 → roses_2024` (R² = **0.99**)
  - `coconuts_2023 × 1.25 → coconuts_2024` (R² = **0.99**)
  - Built a **dynamic-programming optimal-execution algo** over the known price path with position-limit and available-volume constraints. Spread cost 0.99, volume pct 185/300 = 61.7%. Generated **2.1M seashells** in R5 alone (highest in the field). Final: **3,501,647 total**, rank 2.

### 1c. Prosperity 2 (2024) — jmerle (Rank 9)
- Repo: https://github.com/jmerle/imc-prosperity-2
- R3 gift baskets: grid-searched thresholds. Lost 36k on roses → disabled component trading, kept basket-only.
- R4 coupons: Black-Scholes fair value against coupon price; 420k projected in backtest.
- R4 manual: bid `952 / 980` (vs 952/978 R2), reasoning "other players will push high bid toward average."
- R5 signals — **specific counterparty-ID trades** before IDs were public, inferred via filter:
  - `If Vladimir sells CHOCOLATE to Remy → go long CHOCOLATE`
  - `If Remy sells CHOCOLATE to Vladimir → go short CHOCOLATE`
  - `If Vinnie sells ROSES to Rihanna → go long ROSES` (and inverse)
- Manual R5: 10% icicle earrings, 90% split evenly across 5 other products.

### 1d. Prosperity 3 (2025) — chrispyroberts (7th Global, 1st USA)
- Repo: https://github.com/chrispyroberts/imc-prosperity-3
- **R3 (Volcanic Rock Vouchers):** 5 call strikes (9500 / 9750 / 10000 / 10250 / 10500). European, 7-day expiry at round start. Key parameters: voucher pos cap **80 per strike** (to keep rock-hedge capacity), rock pos limit **400**, theta **~430 seashells/day** at full 200-voucher hold, spread cost **0.5/trade**, worst-case unhedged loss **~16k**. Strategy: fit **moneyness smile** `m = log(K/S_t)/√TTE`, quadratic regression to predict fair IV → Black-Scholes fair price → spread-trade vouchers. **Upgraded** from quadratic fit to rolling-window IV mean (backtest 80k→200k/day). **Failure mode:** quadratic smile broke on official submission day; memory overflow (100MB) from Jasper's visualizer wiped rolling windows → dropped 7th → 241st mid-round.
- **R4 (Magnificent Macarons):** position limit **75**, conversion limit **10/timestep**. Hidden **taker-bot discovery**: placing sell at `int(externalBid + 0.5)` got filled ~**60%**, ~3 seashells better than local best bid. Tried a **logistic regression on sunlight index** features (sunlight_diff coef −2.05, sunlight_critical +0.47, sunlight_critical_time −0.0014, all p<0.01) — 25k/day historic but abandoned because of generalization concerns + export/import-arb interference. Final: static quote at `int(externalBid + 0.5)`, 10 units/tick. 447,251 combined PnL (highest R4 PnL).
- **R5 (Trader IDs public):** no new products. Identified **Olivia** — "buys 15 at daily low, sells 15 at daily high, every day, 3 products." R5 "YOLO": used Olivia's signal on **CROISSANTS** — ride long via both baskets (up to **1050 croissant-equivalent exposure**), max loss 300/basket × 150 baskets ≈ 45k (actually sized to 20k risk). Jam leg left unhedged (30 units) to free 60 more croissant slots. Expected upside 120k, baseline 50k from basket-arb. Also manual R5: **cvxpy convex optimization** across 9 products with quadratic fee `Fee(x) = 120·x²`. Final algo 244,740 + manual 138,274.

### 1e. Prosperity 3 (2025) — Alpha Animals / CarterT27 (9th Global, 2nd USA)
- Repo: https://github.com/CarterT27/imc-prosperity-3
- R3: BS with rolling IV window across strikes. **Exploited a bug** that kept them max-short on volcanic rock for a full day — which happened to be profitable and bumped them to 2nd peak.
- R4: two-regime macaron strategy — normal sunlight = two-way cross-market arb; low sunlight = aggressive long accumulate. Disabled before R5 due to implementation issues.
- R5: identified Olivia via **win-rate statistical analysis**, copy-trade on SQUID INK + CROISSANTS. Inventory-aware sizing.
- Final: 1,190,077 seashells.

### 1f. Prosperity 3 (2025) — TimoDiehm (top global, strong write-up)
- Repo: https://github.com/TimoDiehm/imc-prosperity-3
- Labels self "Preparing for Prosperity 4? This repo won't help you win, but will help you understand why you didn't" — Intentionally failure-diagnostic.
- R3 **IV-scalping specifically at the 10,000-strike** voucher: detected negative 1-lag autocorrelation in returns → lightweight mean-reversion with fast-EMA thresholds. 100–150k/day from IV scalping alone; mean-rev lost ~50k in R4 and was kept as hedge against competing teams.
- R4: same taker-bot fill trick as chrispyroberts (`int(externalBid + 0.5)`, ~60% fill).
- R5: **kept parameters conservative** (half-hedged baskets, reduced mean-rev exposure) after building a lead of ~190k. Defensive mode wins.

### 1g. Other strong references

| Repo | Edition | Rank | URL |
|---|---|---|---|
| Sylvain-Topeza | P3 | top 1% | https://github.com/Sylvain-Topeza/imc-prosperity-3 |
| pe049395 | P2 | 13 | https://github.com/pe049395/IMC-Prosperity-2024 |
| gabsens (manual-only) | P2 | 30 | https://github.com/gabsens/IMC-Prosperity-2-Manual |
| hochfilzer | P2 | - | https://github.com/hochfilzer/prosperity2 |
| nicolassinott | P1 | - | https://github.com/nicolassinott/IMC_Prosperity |
| MichalOkon | P1 | 57 (top 1%) | https://github.com/MichalOkon/imc_prosperity |
| VincentTLe | P4 prep | - | https://github.com/VincentTLe/imc-prosperity-4-prep (cross-edition lesson synthesis) |
| jmerle backtester | P2/P3 | - | https://github.com/jmerle/imc-prosperity-2-backtester and https://github.com/jmerle/imc-prosperity-3-backtester |

---

## 2. Medium / written write-ups

- **David Teather, P2**: https://medium.com/@davidteather/imc-prosperity-2-b1c94b1ebba8 — describes components sold separately because no bundling allowed; R3 manual tile picker (ranked 1st + 6th EV, hedging against irrational players); R4 chose 960/980 bids; R5 barely participated. R2 final 381 overall / 103 US.
- **Matius Chong, P3**: https://medium.com/@matius_chong/imc-prosperity-3-challenge-2025-2af2a7a4132b — describes the regression-with-99%-R² trap in R4 macarons, and a volcanic-rock algo bug that lost 82,558 shells.
- **Sam Bennett, P3, UK 4th / top 0.8%**: https://medium.com/@samjgbennett/trading-triumphs-my-journey-to-finishing-4th-in-the-uk-and-top-0-8-globally-in-algo-trading-0248f862ec0b — confirms the 5-round structure with "each round concluding with a Manual trade in the form of a mathematical optimization problem."
- **Martin Oravec, P3**: https://medium.com/@oravec.martin01/imc-prosperity-3-be859180f133 — confirms 6 rounds (including tutorial), each with 1 manual + 1 algo.

---

## 3. Official / archive sources

- Official landing (P4): https://prosperity.imc.com/
- IMC corporate (P3 announcement): https://www.imc.com/us/corporate-news/prosperity-3-IMCs-global-trading-challenge-returns
- IMC corporate (P4 announcement): https://www.imc.com/us/articles/prosperity-4-imc-global-trading-challenge
- P4 T&Cs (PDF): https://prosperity.imc.com/docs/terms-and-conditions.pdf
- **Notion wiki (P4, registration-gated):** https://imc-prosperity.notion.site/prosperity-4-wiki — not publicly scrapable.
- jmerle R1 manual gist: https://gist.github.com/jmerle/394c1e37d8240d63e4e374953bc8e45a
- P4 outer-space theme confirmed in landing page. Timeline: April 14 – April 30.

---

## 4. Cross-edition round-by-round table

### Prosperity 1 (2023)

| Round | Algo products | Mechanic | Winning approach | Common failure |
|---|---|---|---|---|
| 1 | PEARLS, BANANAS | Mean-reverting MM / EMA MM | Fixed-price MM (10k ± 1) + EMA MM | Overfitting EMA window |
| 2 | + COCONUTS, PINA_COLADAS | Pair-trade (0.94 corr) | `pina − (15/8)·coco` z-score | Wrong hedge ratio |
| 3 | + BERRIES, DIVING_GEAR, DOLPHIN_SIGHTINGS | Time-of-day seasonality + exogenous signal | Hardcoded BERRIES timestamps; DIVING_GEAR filter `|Δdolphin| ≥ 5` | Treating noise as signal |
| 4 | + BAGUETTE, DIP, UKULELE, PICNIC_BASKET | ETF arbitrage, premium=375 | `basket − 4·dip − 2·bag − uku − 375` | Components cost more than basket (over-hedge) |
| 5 | No new; + **trader-ID Olivia** | Counterparty flow | Olivia signal on UKULELE + BERRIES augment | Overfitting on tiny R5 sample |

### Prosperity 2 (2024)

| Round | Algo products | Mechanic | Winning approach | Common failure |
|---|---|---|---|---|
| 1 | AMETHYSTS, STARFRUIT | MM + mean-rev | Fixed 10k ± 1 + rolling mid MM | — |
| 2 | + ORCHIDS | Cross-island arbitrage w/ sunlight + humidity, storage cost, tariffs | Static take-profit cross quote | Treating storage cost as negligible |
| 3 | + CHOCOLATE, STRAWBERRIES, ROSES, GIFT_BASKET (4+6+1) | ETF spread-arb, premium ~370 | Rolling z-score on `basket − synthetic` | Trading components (Linear Utility kept all 4, jmerle disabled components after −36k on roses) |
| 4 | + COCONUT, COCONUT_COUPON (10k strike, 250d) | Long-dated option, IV ~16%, Δ~0.53 | IV mean-rev + partial delta hedge | Cannot fully hedge 600 coupons → residual Δ |
| 5 | No new; **trader IDs** | Counterparty flow | jmerle: Vladimir↔Remy CHOCO flow, Vinnie↔Rihanna ROSES flow; Linear Utility: cross-edition regression + DP optimal execution on revealed price path (R²=0.99) | Not using prior-year data for regression |

### Prosperity 3 (2025)

| Round | Algo products | Mechanic | Winning approach | Common failure |
|---|---|---|---|---|
| 1 | RAINFOREST_RESIN, KELP | Fixed + mean-rev MM | Static-price MM (resin), EMA MM (kelp) | — |
| 2 | + SQUID_INK | Volatile mean-reversion | Z-score mean-rev with tight stops | Running out of position limit, over-trading |
| 3 | + CROISSANTS, JAMS, DJEMBES, PICNIC_BASKET_1 (6c+3j+1d), PICNIC_BASKET_2 (4c+2j) | Two-basket ETF arb | Spread-arb both baskets independently | Over-hedging djembe |
| 3/4 edge-case | + VOLCANIC_ROCK, 5 VOUCHERS (9500/9750/10000/10250/10500) | Short-dated (7-day!) ATM/OTM call options | Fit IV smile `m=log(K/S)/√TTE`, quadratic fit → BS fair; IV-scalp at 10k strike (neg 1-lag autocorr) | Quadratic smile overfits → breaks on submission day; theta bleed ~430/day |
| 4 | + MAGNIFICENT_MACARONS (pos 75, conv 10/tick) | Cross-exchange w/ sunlight, sugar, tariffs | Static quote `int(externalBid + 0.5)` → ~60% fill via hidden taker bot | Over-engineering sunlight regressions (suspicious 99% R²) |
| 5 | No new; **trader IDs public** | Counterparty flow | Direct Olivia-ID tracking; copy-trade CROISSANTS/SQUID_INK; manual = cvxpy quadratic-fee allocation | False-positive Olivia detection (pre-ID) cost hundreds of shells |

### Manual-round archetypes (cross-edition)

P2 R1 manual: **currency-arbitrage chain** (5 trades on a conversion matrix — classic FX graph-cycle). P2 R3: **tile picker with 100x multiplier + hunter-split** (game-theory crowd prediction — same as our P4-R2 Invest & Expand archetype). P2 R4: **sealed-bid fish auction** (use average-bid info). P3 R2: tile picker again with different fields. P3 R4: **tile picker (same as R2, with a 2nd choice costing 25k instead of 50k)**. P3 R5: **news-based sentiment allocation** with quadratic trade-size fee `120·x²`. Manual puzzles recycle archetypes across editions (sources: TimoDiehm README, chrispyroberts, and search result summary).

---

## 5. Recurring architectural / code lessons

From VincentTLe's cross-edition study and explicit mentions in Linear Utility, chrispyroberts, TimoDiehm:

1. **Three-phase execution model** (`take → clear → make`) — used by every top-3 team across P2 and P3. Take crossing orders first, clear outstanding hedges, then market-make residual.
2. **Wall-mid pricing** > simple midpoint — less manipulable on thin books.
3. **Submission-safe `norm_cdf`** (Abramowitz–Stegun approximation) — all top P2/P3 options traders inline this; scipy is blocked.
4. **`collections.deque` for rolling windows** — O(1) append/popleft vs `list.pop(0)` O(n).
5. **Logger class with truncation** — IMC truncates stdout ~3750 chars/tick; uncontrolled logging silently drops data.
6. **Position-limit awareness per-tick** — the `ConversionObservation` counts against a separate conversion limit (P2 Orchids, P3 Macarons).
7. **`traderData` size discipline** — persisted state string grows and can blow memory (chrispyroberts lost R3 R3 to a 100MB visualizer overflow wiping rolling windows).
8. **Backtest vs submission gap** — Linear Utility: projected 135k, got 111k; chrispyroberts: backtest 200k/day, got 75k R3. Slippage + fill-probability differences are structural.

---

## 6. P4 R3 / R4 / R5 forecast

Current known (P4):
- R1: RAINFOREST_RESIN (fixed), KELP (mean-rev), SQUID_INK (volatile) — same as P3 R1+R2.
- R2 (currently running): fresh products — ASH / MAF / tomatoes per this repo's `src/core/` and `outputs/`.

### SPECULATION: P4 R3 most likely contains
- **An ETF/basket arbitrage pair** (P1 R4, P2 R3, P3 R3 all had this). P3 introduced **two** baskets — P4 likely keeps two or introduces three for added complexity.
- **A new volatile/seasonal product** with either a time-of-day or exogenous-index signal (P1 BERRIES timestamps, P2 ORCHIDS sunlight, P3 VOLCANIC_ROCK news cycle).
- Possibly a short-dated option (see R4 below) introduced one round earlier to raise difficulty.

### SPECULATION: P4 R4 most likely contains
- **Options on one of the R3 products** (P2 had COCONUT_COUPON on COCONUT in R4; P3 had VOLCANIC_ROCK_VOUCHER essentially in R3/R4). IMC's clear preference: a **multi-strike call chain** around the current underlying, with 1-week (P3) or 250-day (P2) expiry. P4 likely picks a new expiry regime — e.g., **2-week or multiple-expiry** (to punish the teams who just fit a static IV smile).
- **Cross-exchange / location arbitrage** of a commodity with an exogenous-variable signal (ORCHIDS sunlight/humidity → MACARONS sunlight/sugar → P4 likely has **multi-variable** external signal). Based on our repo's `tomatoes` and `sunlight_index` tooling for R2, IMC may promote one of these to a full-round arb.
- If IMC adds options in R3 instead, R4 is then likely **another exotic** — e.g., a perpetual/futures product, or a stablecoin-style anchored asset with a break-threshold (this is pattern-extrapolation, not confirmed).

### SPECULATION: P4 R5 almost certainly contains
- **No new products.**
- **Trader IDs made public** (P2 inferred, P3 explicit, P4 continues). Expect 10–12 bots with 1 "signal bot" named after an IMC employee (Olivia in P1-P3) who trades max-drawdown lows and peaks. The trick is **which products** Olivia is assigned to — changes per edition.
- **News/sentiment manual puzzle** with quadratic trade-size fee (P3 used `120·x²`). P4 may scale the fee or expand the product set to 12–15.
- **A "make any open trade profitable" opportunity** by extrapolating from the prior edition's data (Linear Utility's P2 R5 breakthrough — `diving_gear_2023 × 3 → roses_2024`, R²=0.99). If this pattern repeats, **P3's R5 disclosed price paths become the training set for P4 R5**. Strong alpha candidate: test linear combinations of P3 final-day prices against P4 R5 revealed data as soon as R5 opens.

### Meta-hints from Dave Nandi (per user brief)
User brief: "Dave Nandi (options quant) is the round designer and hints future rounds may include news-based algo shocks." SPECULATION consistent with this: expect at least one **discrete exogenous news shock** in R3 or R4 (beyond sunlight/humidity). Historical precedent: P3 R4 macarons had CSIPR (Critical Sunlight Index Pressure Regime) switches. P4 may layer **discrete news events** (binary headlines / numeric reports) that shift a fair-value permanently mid-day.

### Concrete preparation priorities for P4 R3 (next round for this team)
1. **Finalize a production Black-Scholes module** with inline `norm_cdf` (A&S approximation) before R3 opens. Prove correctness against a Python reference; do not rely on scipy.
2. **Template an ETF-arb z-score trader**: spread = basket − Σ component_weights·component_price; rolling window 500–2000 ticks; z-score entry ±2, exit 0.
3. **Rolling IV estimator with safe memory bounds** — deque, max-length 1000, not list. Preempt the chrispyroberts 100MB wipe.
4. **Three-phase take/clear/make scaffold** for any new product. Every top team has this.
5. **Cache prior-edition price data** — download P3 final-day public data now; regression-test it against P4 R5 the moment IDs/paths are revealed.
6. **Manual-round muscle memory**: expect one of {tile-picker-with-hunters, FX-arbitrage-chain, sealed-bid-auction, quadratic-fee-allocation, news-sentiment-allocation}. Our repo already has `src/manual_rounds/invest_expand*.py` framework — generalize it.

---

## 7. Summary

Across P1→P2→P3, rounds 3/4/5 follow a remarkably stable skeleton:
- **R3 = ETF/basket arbitrage** (adds complexity each year: 1 basket → 1 basket w/ larger basket → 2 baskets).
- **R4 = options and/or location arbitrage** (P1 R4 was baskets; P2 introduced long-dated options; P3 introduced short-dated options *and* cross-exchange macarons in the same edition).
- **R5 = no new products + trader-ID flow + manual news-allocation**. The decisive alpha in P2-R5 was cross-edition price regression; in P3-R5 it was Olivia direct-ID copy-trading.

The edit for P4 will be a novel twist — outer-space theme, likely multi-expiry options or a new exogenous-signal regime — but the **fundamental tooling needs** (BS with inline normal CDF, ETF z-score, take/clear/make, trader-ID flow) transfer directly.
