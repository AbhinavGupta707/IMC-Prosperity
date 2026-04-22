# Academic & Practitioner Research for IMC Prosperity 4 — Rounds 3-5

Pre-round research pack. Assumes reader knows BSM, Greeks, and basic stat-arb.
Focus: implementation-ready heuristics, thresholds, and failure modes. Round 3
(options), Round 4 (basket + cross-exchange macarons), Round 5 (news/signal).

---

## 1. Short-dated options: market making, vol arb, hedging

### 1.1 Gamma-scalping ↔ theta-decay tradeoff for weeklies

**Core principle.** Long gamma earns when realized volatility (RV) of the
underlying, hedged at finite intervals, exceeds the premium paid for theta.
Instantaneous P&L along the path for a delta-hedged option is approximately:

    dPnL ≈ ½ · Γ · S² · (dS/S)² − Θ · dt
         ≈ ½ · Γ · S² · (σ_realized² − σ_implied²) · dt

Profit per day ≈ ½ · Γ · S² · (σ_RV² − σ_IV²) · (1/252). Ties out with
Wilmott/Sinclair: *you are trading the square of realized vs. square of
implied, weighted by $-gamma*.

**Practical heuristic (weeklies/near-expiry).**
- ATM straddles give the **highest gamma per dollar of theta** → preferred
  vehicle for scalping. (volatilitybox.com)
- For 0DTE / 1DTE, theta accelerates exponentially intraday: typically ~0.15
  of premium/hr near open rising to 0.8-1.2/hr in the final hour. Avoid
  holding long-gamma into the last 60-90 minutes unless you have a directional
  view; late-session path dependence usually beats even a correct vol call.
  (Volatility Box, 0DTE guide)
- Rule of thumb: a long-gamma trade needs a daily *absolute* underlying move
  of roughly `σ_IV · S · √(1/252)` just to break even on theta. If the 1-day
  realized over the last N sessions is below 0.8× that, skip the trade.

**Common failure mode.** Treating IV > RV as a free short-gamma trade ignores
jump risk and mean-reversion of vol itself. Over short windows IV is often
wrong *and* correct (wrong on level, right on expected jump). In a sim
environment with predictable mid-price drift between events, the scalper
usually wins; around any news-like event they lose everything they earned.

**Formula / threshold.** Enter long straddle when
`(σ_RV(20) / σ_IV) > 1.15` *and* half-life of the vol spread < expiry.
Otherwise, neutral or short. (Sinclair, *Volatility Trading* 2nd ed. — regression
of 20-day RV on IV is the single most robust trigger he recommends.)

Sources:
- https://volatilitybox.com/research/gamma-scalping-explained/
- https://volatilitybox.com/research/0dte-options-volatility-day-trading-guide/
- https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5285239 (Ramkumar 2024 — formal gamma-theta tradeoff)
- Sinclair, *Volatility Trading* 2e (Wiley). https://www.wiley.com/en-us/Volatility+Trading,+++Website,+2nd+Edition-p-9781118416723

### 1.2 IV smile regression & parametric fits (SVI, quadratic)

**Core principle.** Cross-sectional IV across strikes is approximately a
smooth convex function of log-moneyness `k = ln(K/F)/√T`. Any strike whose
fitted residual is > kσ from the smile is a candidate for RV arb against
neighboring strikes (skew / butterfly). Gatheral's SVI with arbitrage-free
constraints (Gatheral & Jacquier 2013) is the industry workhorse; a simple
quadratic `v = a·k² + b·k + c` is usually sufficient for short-dated strips
with 5-10 strikes.

**Practical heuristic (matches what Prosperity 3 top teams used).**
- Compute `m = ln(K/S)/√T`, fit quadratic to mid-IV across strikes each tick
  (or at a slow cadence e.g. every 500 ticks).
- Trade each voucher against the smile: if observed IV is below fit, buy;
  above, sell. Market-make around the fitted fair, skewing quotes toward
  cheap strikes.
- **Prosperity 3 top teams replaced the fit with a rolling window of the
  *mid-IV itself*** once it was clear the quadratic stopped tracking late in
  the round — 200k/day vs 80k/day. Lesson: treat the parametric fit as a
  *prior*, let recent mid-IV dominate when recent data is available.
  (chrispyroberts/imc-prosperity-3 writeup)
- Delta-hedge only if spread cost < expected gamma P&L. Prosperity 3 top team
  **stopped delta-hedging** after calculating ~40k in spread costs vs. ~16k
  realistic unhedged loss per step.

**Common failure mode.** Over-fitting to a single slice (e.g. one timestep)
produces a smile that inverts sign between ticks → your signal flips on noise.
**Smooth IV temporally** (EWMA with half-life 200-500 ticks) before using
the fit to quote.

**Formula / threshold.** Trade voucher k if
`|IV_obs(k) − IV_fit(k)| > 1.0 · σ_residual` estimated over the last 500
timesteps. Cap individual-strike position at 20-40% of the voucher position
limit.

Sources:
- Gatheral & Jacquier, *Arbitrage-Free SVI Volatility Surfaces* (2014). https://arxiv.org/pdf/1204.0646
- Martini & Mingone 2020 update. https://arxiv.org/pdf/2005.03340
- chrispyroberts writeup (Prosperity 3, 1st USA). https://github.com/chrispyroberts/imc-prosperity-3
- Sylvain-Topeza writeup (top 1% P3). https://github.com/Sylvain-Topeza/imc-prosperity-3

### 1.3 Full vs. partial delta hedge — when spread cost dominates

**Core principle.** Leland (1985) showed BSM delta-hedging at fixed intervals
with TC λ produces hedging error that scales with √(frequency); Whalley &
Wilmott (1997) derived the optimal **no-trade band**:

    Δ_band = (3/2 · λ · Γ² · S² / γ)^(1/3) · σ^(−2/3) · T_residual^(1/3)

where γ is risk aversion. Scaling is `λ^(1/3)` — **band is surprisingly wide
for even moderate TC**, and a joint-hedger of two correlated options trades
less often.

**Practical heuristic for sim markets with 1-wide spreads.**
- Compute cost of one round-trip hedge = 2 × (½ spread) × |ΔQ|.
- Compute expected gamma P&L per step = ½ · Γ · S² · σ² · dt.
- **Hedge only if |Δ_current − Δ_target| > band**, with band widening as
  expiry approaches (gamma goes vertical → bigger band sounds wrong but
  formula gives it; intuition: mis-hedge P&L scales with ΔΔ²·Γ, and Γ·S² is
  large, so a small ΔΔ is fine).
- For a portfolio of vouchers, hedge the **aggregate delta**, not
  strike-by-strike. Reduces hedge volume ~3-5× vs. per-strike hedging.
- If spread cost per hedge > expected per-step gamma P&L, **don't hedge**.
  Carry the directional exposure; it's cheaper than the leak.

**Common failure mode.** Hedging every tick in a 1-wide spread market
systematically bleeds the theta budget you just paid for. A common observed
outcome: long-gamma book PnL looks like theta-minus-TC, and you lose exactly
what you expected to make.

**Formula / threshold.**
- 1-wide spread, per-step Γ·S² ≈ V, RV ≈ σ: hedge when |ΔQ| ≥ `max(1,
  (2·λ/σ²·V)^(1/3))` units. For small books this usually collapses to
  "hedge when cumulative Δ exceeds 5-10 units" rather than every tick.

Sources:
- Whalley & Wilmott 1997 / 1999. https://users.ox.ac.uk/~ofrcinfo/file_links/mf_papers/1999mf17.pdf
- Zakamouline, *Optimal Hedging with Transaction Costs* (EFMA 2005). https://www.efmaefm.org/0efmameetings/efma%20annual%20meetings/2005-Milan/papers/284-zakamouline_paper.pdf
- Sepp on Wilmott discretization. https://artursepp.com/2017/05/01/how-to-optimize-volatility-trading-and-delta-hedging-strategies-under-the-discrete-hedging-with-transaction-costs/amp/

### 1.4 Jump detection & gap risk for short-gamma

**Core principle.** Sim environments typically stitch discrete regimes
(news ticks, bot regime changes). A short-gamma book is P&L-symmetric to
diffusion but **linearly short a jump**: one mis-sized jump can wipe a
week. Detection relies on variance-ratio tests or simple absolute-return
outliers.

**Practical heuristic.**
- Track |r_t| / EWMA(|r|, halflife=500). If ratio > 4.0 in a single step,
  treat as jump regime; halt short-gamma, flatten any directional leg.
- Maintain a **gross-gamma cap** per voucher book, e.g. net Γ·S² at ATM
  ≤ 2 × typical per-step gamma P&L. Caps worst single-step loss to ~2× edge.

**Common failure mode.** Assuming jump is mean-reverting and doubling down.
In a scored competition, drawdown from a single fat-tail step often exceeds
cumulative theta earned to that point.

### 1.5 Calendar / diagonal spreads on weeklies-only chains

**Core principle.** When only one expiry is listed (typical Prosperity
setup), calendar spreads are unavailable. *Term-structure* arb is then
restricted to trading one strike against the fair at *different times*
(statistical arbitrage on the smile residual's mean-reversion). Half-life
of IV residuals is usually 100-800 ticks; estimate by OU fit on daily
residuals.

If two expiries exist, a **calendar** = long far / short near of same K
earns on vol term-structure mean-reversion; a **diagonal** lets you isolate
skew at a price. Sinclair's practical rule: short the wing where IV is
> 1σ above the smile, long the ATM, delta-hedge the package.

---

## 2. Basket / ETF statistical arbitrage

### 2.1 Cointegration + Kalman filter for spread

**Core principle.** For basket `B` and constituents `C_i`, the spread
`B − Σ w_i · C_i` is stationary when weights are correct. Kalman filter
treats the hedge ratio as a hidden state and updates with Bayesian noise.

**Practical heuristic.**
- Start with **static regression** weights over first 100k ticks of replay
  data. If Engle-Granger ADF p < 0.05, cointegration holds — use static
  weights initially.
- Layer Kalman on top only if weights drift. State: `β_t = β_{t−1} + η_t`;
  observation: `B_t = β_t · C_t + ε_t`. Tune `Q/R` ratio by cross-validation
  on out-of-sample half-life.
- Compute spread z-score: `z = (S_t − μ̂_t) / σ̂_t` where μ̂, σ̂ are
  rolling EWMA or OU-fitted. Enter at |z| > 2, scale out by z=0, stop at
  |z| > 4 (regime break signal).
- **Half-life of mean reversion** is the decisive parameter:
  `τ = −ln(2) / θ` where θ is the OU speed. Reject the trade if τ is longer
  than remaining round horizon. ArbitrageLab's default rule: only trade
  pairs with τ ≤ 25 bars / ≤ 10% of session. (Hudson & Thames)

**Common failure mode.** A cointegration test passes at full-sample but
fails out-of-sample because one constituent has a regime shift (e.g. bot
change). Always **purged-CV the ADF test** with 10+ folds before going live.

**Formula / threshold.**
- Entry: |z| > 2.0.
- Exit: |z| < 0.3 OR time-stop at τ × 3 steps.
- Kill: |z| > 4.0 (suspect regime break).

### 2.2 Hysteretic / asymmetric sizing (Nandi's rule)

**Core principle.** If you size *entry* proportional to spread width, you
load maximally where the edge is biggest. If you use the *same trigger* for
exit, you under-exit in persistent regimes. **Exit triggers should be
tighter than entry triggers** — e.g. enter at |z|=2, exit at |z|=0.3 rather
than symmetric z=0. This is the "hysteresis" shape.

**Practical heuristic.**
- Entry size ∝ min(|z|, 3.0) / 3.0, i.e. full size at |z|=3, half at |z|=1.5.
- Skip trades with |z| < 1.0 (signal below typical noise).
- Include a **no-trade dead zone** around z ≈ 0 to avoid whipsaw.
- If half-life τ is short, use tight exit (fast reversion). If τ is long,
  use both time-stop and target-z exit.

**Common failure mode.** Scaling out linearly at small z values leaves
position exposed during the long tail of reversions; profits erode. Better:
take full flat at z=0.3 and wait for next setup.

### 2.3 Lead-lag between basket and constituents

**Core principle.** In a two-book system, one book usually leads — ETFs
typically lag large constituents in human markets; in sim, it depends on bot
behavior. The leader reveals information; trading the lagger against the
leader's move is the classic edge.

**Practical heuristic.**
- Compute cross-correlation of 1-step log returns at lags -5 … +5 over 10k
  ticks. The peak lag's sign identifies the leader.
- If constituent leads basket by k ticks: when constituent moves > 1σ,
  front-run the expected basket move with size proportional to
  `ρ_lag · σ_basket / σ_constituent`.
- Track the signal's **hit rate** on held-out data; a realistic IC is
  0.02-0.08. Anything reporting > 0.15 is almost certainly lookahead leakage.

**Failure mode.** Reversing the lag sign mid-session. Protect with a
rolling-window re-estimation and a sanity check that the lag is consistent
across multiple sub-periods.

### 2.4 Two-correlated-book market making (Avellaneda-Stoikov extension)

**Core principle.** A-S for a single asset skews quotes around a reservation
price `r = s − q · γ · σ² · (T − t)` where q is inventory. For two
correlated books, the reservation prices become coupled via the correlation
matrix, and quoting one book's edge *against* its hedge in the other book
tightens the effective bid-ask.

**Practical heuristic.**
- Estimate `ρ` between two books' mid returns over 5k ticks.
- For book A, shift reservation price by `γ · σ_A · σ_B · ρ · q_B ·
  (T − t)` in addition to own-inventory skew.
- If you hold inventory q_B (hedged position) that will be unwound in book
  B, tighten book A's quote on the side that naturally unwinds q_B.

**Failure mode.** Assuming ρ is constant. When correlation breaks, you end
up long both books in a panic. Cap joint gross exposure at a hard limit
regardless of ρ.

Sources:
- Avellaneda-Stoikov 2008. https://people.orie.cornell.edu/sfs33/LimitOrderBook.pdf
- ArbitrageLab cointegration docs. https://hudson-and-thames-arbitragelab.readthedocs-hosted.com/en/latest/spread_selection/cointegration_spread_selection.html
- ArbitrageLab OU / half-life. https://hudson-and-thames-arbitragelab.readthedocs-hosted.com/en/latest/cointegration_approach/half_life.html
- Hudson & Thames, caveats in OU calibration. https://hudsonthames.org/caveats-in-calibrating-the-ou-process/
- QuantStart Kalman pairs. https://www.quantstart.com/articles/Dynamic-Hedge-Ratio-Between-ETF-Pairs-Using-the-Kalman-Filter/

---

## 3. Cross-exchange stat-arb + external signals (Round 4 territory)

### 3.1 Tariff / convenience-yield arb framework

**Core principle.** If asset trades locally at `P_L` and externally at
`P_F`, with transport t, import-tariff τ_i, export-tariff τ_x, and storage
c, the no-arbitrage band is:

    P_F + τ_i + t ≤ P_L ≤ P_F − τ_x − t       (after storage/carry corrections)

Outside the band, execute paired conversion. *Negative* tariffs (subsidies)
are the big giveaway and the Prosperity 3 macaron edge — top teams
identified that `conversion_ask + import_tariff + transport < local_bid`,
producing a 2-legged lock.

**Practical heuristic.**
- Compute `sell_local_break_even = conversion_ask + import_tariff +
  transport_fee` each step.
- Whenever local_bid > break_even, sell locally and convert inward.
- Use batched conversions (Prosperity 3: batches of 30 vs. naive 10) to
  amortize fixed costs — accept a capped adverse-selection loss (~12k) in
  exchange for ~2× the PnL.
- Track the *sign* of tariffs over time; in a volatile-tariff world, the
  band shrinks and arb disappears. Don't assume stationarity.

### 3.2 Forecasting commodity price from weather/sunlight proxies

**Core principle.** Weather signals are a **regime indicator**, not a
precise forecast. Macrosynergy's commodity-carry research argues the carry
signal dominates price forecasting; weather adds value only as a dummy
(e.g. low_sunlight → supply squeeze → higher fair value).

**Practical heuristic from P3 macarons.**
- In "normal sunlight" regime: run the two-way arbitrage (±).
- In "low sunlight" regime: flip to accumulation only (buy-and-hold, export-
  ban). Don't try to sell into a squeeze.
- Threshold: percentile rank the sunlight index over a rolling 100-day
  window; below the 25th pct → squeeze regime; above the 75th → glut regime.

**Failure mode.** Continuous interpolation of the signal (e.g. linear-
regressing price on sunlight) over-fits to sample noise. The Prosperity 3
macaron example showed a linear regression with 99% R² — a tell-tale of
lookahead or leakage. Prefer discrete regime flags + robust quantile
thresholds.

Sources:
- Macrosynergy, *Commodity carry as a trading signal*. https://macrosynergy.com/research/commodity-carry-as-a-trading-signal-part-1/
- IMC Prosperity 3 macaron writeup. https://medium.com/@matius_chong/imc-prosperity-3-challenge-2025-2af2a7a4132b

### 3.3 Signal blending (weak predictive + pure arb)

**Core principle (Grinold-Kahn).** For uncorrelated signals, the combined
IC is roughly `√(Σ IC_i²)` — adding a weak signal (IC=0.03) to a strong one
(IC=0.10) only helps when signal is uncorrelated. Convert raw signal to
alpha via:

    α_i = σ · IC_i · z(signal_i)

Blend with inverse-variance weighting on each signal's forecast error.

**Practical heuristic.**
- Keep arb and predictive signals **as separate P&L streams**, each sized
  to its own edge, only blending at the **risk** layer (position cap).
- Never let a weak predictive signal override the arb signal — if the arb
  says "enter at band", enter; predictive should only skew size, not
  direction.
- Cap predictive's share of risk at 20-30% until it has produced at least
  2k realized ticks of consistent edge.

### 3.4 Hidden liquidity detection

**Core principle.** Trades executing for more size than was displayed at
top-of-book → iceberg / hidden-replenishment signal. In sim with bot
counterparties, hidden orders typically take the form of "bot always refills
at this price if touched".

**Practical heuristic.**
- Log (best_ask_size_before_trade, trade_size, best_ask_size_after_trade)
  per execution. If trade_size > displayed and price unchanged, count as
  hidden-replenishment event.
- At a price level with > 3 replenishment events in 500 ticks, treat as
  *pinned* — quote aggressively one tick inside and expect fills.
- Prosperity 3 macaron hint: teams detected a taker bot that filled
  attractive offers regardless of displayed size — a hidden-fair signal
  extractable by regressing filled-side on mid.

Sources:
- Zotikov, *CME Iceberg Detection* (arXiv 2019). https://arxiv.org/pdf/1909.09495
- Christensen-Woodmansey, *Hidden Liquidity in GLOBEX Futures*. https://www.semanticscholar.org/paper/Prediction-of-Hidden-Liquidity-in-theLimit-Order-of-Christensen-Woodmansey/cf0a3e09fb2090720b2f64548cdc9b9d04c3887e

---

## 4. News / event-driven trading in simulated environments

### 4.1 Parsing structured news to positions

**Core principle.** In Prosperity-like sims, news is a categorical regime
flag appearing on a small number of timestamps. The alpha is the **reaction
window** after the flag — typically 50-500 ticks where mid-price drifts
monotonically before absorbing the shock.

**Practical heuristic.**
- Pre-compute per-news-type impulse response from replay data:
  average abnormal return over t=0 … 500 after each news tag.
- Enter at news tick with position sized to `0.5 × peak_abnormal_return ×
  risk_budget / observed_σ`.
- Scale out along the decay curve — don't hold past the estimated reaction
  horizon.

### 4.2 Event-study framework for bounded horizons

**Core principle (Kothari-Warner 2007).** Short-horizon event studies
(< 30-day windows) are *well specified* — test statistics have nominal
power. Long-horizon studies are not. For a 1M-step round, any single
event's "long-horizon" is already short in absolute terms → short-horizon
methodology applies.

**Practical heuristic.**
- Abnormal return `AR_t = r_t − r̂_t` where r̂ is predicted from a pre-
  event baseline model (mid AR(1) is sufficient).
- Cumulative abnormal return (CAR) over (0, h) measures trade edge. Test
  significance with Boehmer-Musumeci-Poulsen standardized residual test —
  robust to event-induced variance.
- Pick the holding horizon h that maximizes the CAR-Sharpe, not just CAR.

### 4.3 Pre-announcement positioning when event time is known

**Core principle.** If event time t* is known, there's a predictable run-up
/ uncertainty premium in the window (t* − k, t*). Strategy: scalp the
run-up if consistent, OR stand aside and trade the post-event drift (usually
more robust).

**Practical heuristic.**
- In replay, measure abnormal volume and AR in (t*−50, t*−1) across all
  past events. If AR is significantly signed, front-run; if not, stand aside.
- If uncertainty is the dominant pre-event effect, *buy* cheap gamma in
  the window and scalp the widened IV — Sinclair's standard pre-earnings
  play.

Sources:
- Kothari & Warner, *Econometrics of Event Studies*. https://www.bu.edu/econ/files/2011/01/KothariWarner2.pdf
- arXiv 2512.00280, *Retail Horizon & Earnings Announcements*. https://arxiv.org/html/2512.00280

---

## 5. Meta / portfolio level

### 5.1 Kelly sizing under rank-based tournament scoring

**Core principle.** Classic Kelly maximizes E[log W]. But tournament payoff
is a function of **rank**, not absolute wealth — the top 3 get ~same large
payoff, ranks 10-100 get smaller, ranks 500+ get nothing. This is a step
function, not a log utility.

**Practical heuristic.**
- If you are currently *below* the payoff threshold: take **more than full
  Kelly** — variance raises tail probability of reaching top. This is the
  "gamble-to-catch-up" heuristic and it's correct under rank scoring.
- If you are *above* the threshold already: cut to **half-Kelly or less** —
  you only need to not collapse. Reducing variance *raises* expected rank.
- Threshold position is revealed by the leaderboard — use it. Teams that
  ignore it leave EV on the table (sim writeups from P3 confirm this:
  top-1 USA explicitly "doubled down to gamble" when they fell behind).

**Formula.**
- Let f* = Kelly fraction from edge/variance. Use `f = f* · (1 +
  shortfall_to_threshold / current_stake)` clipped to [0.25 · f*, 2 · f*].

### 5.2 Robustness vs. peak P&L

**Core principle.** Top teams in Prosperity 2-3 writeups consistently
report: **the stable per-round edge comes from market-making and arb**
(50-80% of PnL), **the tail wins come from one big directional signal**
(news / Olivia-style bot detection). Don't pick one — run both with separate
risk budgets.

**Practical heuristic (budget splits from top P3 writeups).**
- 50-60% of risk → inventory-aware market making on cheap / low-drift
  products (kelp, resin equivalents).
- 20-30% → basket/cointegration arb (picnic basket analogue).
- 10-20% → options vol arb (smile residuals, unhedged if spread dominates).
- 0-20% → signal-following (news / Olivia bot). Start low, scale with
  realized IC.

### 5.3 Inventory split across strategies

**Core principle.** Position limits (~100/product) are binding. Two
strategies competing for the same book line up *in the same direction*
during stress, doubling your risk exactly when you can least afford it.

**Practical heuristic.**
- Maintain a single **portfolio position manager** that takes per-strategy
  signals as *requests* and allocates within the book's cap using
  inverse-variance or CVaR weights.
- Reserve 20% of every book's capacity for the arb legs — do not let MM
  consume the full cap or your arb won't fit when the spread widens.

Sources:
- Kelly criterion basics. https://en.wikipedia.org/wiki/Kelly_criterion
- Lazear & Rosen, *Rank-Order Tournaments*. https://ideas.repec.org/p/nbr/nberwo/0401.html
- Grinold & Kahn *Active Portfolio Management* notes. https://people.brandeis.edu/~yanzp/Study%20Notes/Active%20Portfolio%20Management.pdf
- Chris Pyroberts, 1st USA P3 writeup. https://github.com/chrispyroberts/imc-prosperity-3
- CarterT27, Alpha Animals P3. https://github.com/CarterT27/imc-prosperity-3

---

## Appendix: quick threshold cheat-sheet

| Decision | Rule | Source |
|---|---|---|
| Long gamma entry | σ_RV(20) / σ_IV > 1.15 AND τ_vol < expiry | Sinclair |
| IV smile trade | |IV − IV_fit| > 1.0 · σ_residual over 500 ticks | Gatheral/SVI, P3 writeups |
| Delta-hedge fire | |ΔQ| > (3λΓ²S²/γσ²·(T−t))^(1/3), else skip | Whalley-Wilmott |
| Coint pair accept | ADF p<0.05 AND τ_half < 10% round | Hudson & Thames |
| Spread entry | |z| > 2.0 | ArbitrageLab |
| Spread exit | |z| < 0.3 OR 3·τ ticks, whichever first | ArbitrageLab |
| Spread kill | |z| > 4.0 | OU regime break |
| Tariff arb | local_bid > conv_ask + τ_imp + transport | P3 macaron |
| Weather regime | sunlight_pct < 25 → accumulate; > 75 → glut | P3 macaron |
| Rank sizing | f = f* · (1 + shortfall/stake), clip [0.25f*, 2f*] | Lazear-Rosen adapted |
| Jump detect | |r| / EWMA(|r|, 500) > 4.0 → halt short-gamma | Standard |
| MM risk budget | ≤ 60% of book cap for MM, reserve 20% for arb | P3 top teams |

---

## Closing notes for Prosperity 4 R3-R5 prep

1. The **single highest-leverage insight** from P3 top teams: once local
   evidence of regime change appears (smile stops fitting, sunlight flips,
   bot behavior shifts), **drop the parametric model and trade raw
   rolling-window statistics**. Frameworks must degrade gracefully.
2. For options, **don't delta-hedge** if the per-step spread cost is larger
   than per-step gamma P&L. The math almost always argues for unhedged in a
   tight-spread 1-wide-tick book.
3. For baskets, estimate **half-life of mean reversion first**; reject any
   pair with τ > 10% of remaining session.
4. For cross-exchange arb, the tariff / conversion-fee arithmetic *is* the
   alpha — do it symbolically so sign flips are automatic.
5. Treat signals like Olivia/insider bots as **regime flags to scale
   existing strategies**, not as standalone positions. The P3 writeups are
   unanimous on this.
6. Tournament sizing: **size for rank**, not for mean. When behind
   threshold, increase variance; when ahead, decrease it. This is
   the Lazear-Rosen-adapted lesson that matches top-team post-mortems.
