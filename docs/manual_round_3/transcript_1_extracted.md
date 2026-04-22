# Transcript 1 — Extracted Notes (Prosperity 3 Lecture / Post-Mortem)

## Source Metadata

- **Format:** ~90-minute lecture to an audience of students planning to compete in Prosperity 4.
- **Speaker:** A former Prosperity 3 top-finisher. CMU computational physics + ML/philosophy minor; ex-CERN jet-tagging researcher; now AI/ML engineer at **Spirit Labs** (AI security/bug-bounty startup). Repeatedly recruits interns at the end.
- **Covers:** All 5 algo rounds AND all 5 manual rounds from Prosperity 3. This is the same edition covered in transcript 2 (winners panel), but from a single competitor's perspective, with far more mechanical detail.
- **Team outcome:** Finished 8th overall. After R2 = 7th. R3 disaster → dropped to ~241st (visualizer bug + vol-smile overfit + ruinous hedging cost). Came back to 8th via R5 Olivia-copy signal + good manual-round play.

## Tooling / Infrastructure References

- **Jasper's open-source visualizer** — used for backtest step-through. **Had a bug that crashed on submission in R3** and is directly blamed for the team's R3 P&L collapse. Lesson: do not blindly trust the community visualizer's submission path; verify logs.
- Prior-year write-ups: "everything is similar to the previous year… tutorial is very similar to the previous year. A lot of the alpha from this stuff comes from just preparing, reading the open source stuff, figuring out what happened last year."
- "Before AI" vs "using AI": migrated to Claude Code mid-competition. Endorsed mode = AI writes helper functions you can verify; never one-shot the full algo.

## Per-Round Breakdown (ALGO)

### Round 1 — Rainforest Resin (stable @ 10,000), Kelp (~600, low vol), Squid Ink (high vol, mean-reverting)

- **Fair-value inference trick:** bought at 9,996 / end-of-day mid ≈ 10,000 / P&L came back as +4 → confirmed IMC calculates P&L using **mid of best-bid + best-ask**, not mark-to-last. Do the same inference test for every new product.
- Three R1 optimizations (all on resin):
  1. **Fair-value taking:** any ask < 10,000 buy; any bid > 10,000 sell.
  2. **Penny jumping:** quote one tick inside best bid/best ask. Works because "bots see your orders, place trades on it, then your orders go away" — no other competitor can front-run you. Explicitly said this does NOT work on real-world crypto 5-min markets.
  3. **Position-reducing at fair value:** when at/near position limits, accept trades AT fair value that reduce inventory (you forgo $0 profit on that trade but unlock future spread capture). The one most teams missed.
- **Trading against bots, not teams.** IMC codes the counterparties; the game is extracting value from hard-coded agent logic, not competing against other teams' order flow.
- After R1: team was 771st "because we got screwed by squid." Squid was unprofitable for them.

### Round 2 — Baskets (PICNIC_BASKET1 = 6C+3J+1D, PICNIC_BASKET2 = 4C+2J)

- Plot basket market price vs. theoretical (sum of constituents × weights) → residual = **premium** graph. Trade the premium mean-reversion.
- **ADF test via ChatGPT** to confirm stationarity. Basket-vs-constituents ADF p = 0.06 ("not quite < 0.05 but close enough"). Premium-of-B1 vs premium-of-B2 was much cleaner visually.
- **Position-limit algebra:** cannot simultaneously be 100% long both baskets AND short all constituents (limits break). Chose to trade the **spread between the two basket premiums** instead of basket-vs-constituents, to sidestep the constraint. #2 team did the reverse (premium vs constituents) — both work, different trade-offs.
- Strategy: **Z-score reversion, one hyperparameter** (threshold, symmetric). "Your code should look like this so that you fundamentally understand it" — 5 lines of trading logic.
- Hyperparameter picked from a heatmap: highest P&L AND flat/stable in parameter space (derivative near zero) → low overfit risk.
- **Residual position budget (~8%):** market-make with the leftover. Spread was 8 → extra ~$5k/day just from this. "Don't leave money on the table."
- Frankfurt (top-3 team) differences: individual-asset Z-score on each constituent, plus **informed-trader signal detection** — track max/min trade sizes seen; a large print = informed flow, and they piggybacked. Team also did 50% hedging, closed on zero-crossing.
- After R2 = 7th.

### Round 3 — Volcanic Rock + 5 vouchers (European calls, 5 strikes, same 7-day expiry) — THE DISASTER ROUND

- Options primer covered: delta/gamma/vega/theta. Traded primary variable = **implied vol** (back-solved from Black-Scholes).
- **Vol smile:** compute IV for each strike, plot vs **moneyness (log(K/S) / sqrt(T))** — hint was explicitly given in-competition. Fit a quadratic to the smile; that's your IV curve → convert back to a fair option price → market-make around it.
- Buy when market < fair, sell when market > fair. "Not really market making, more just fixing inefficiency." Strategy "printed money … insane amounts of money" (when it ran).
- Position limit: 400 per voucher (paraphrased as "400 drop limit"); they capped themselves at 80 per voucher.
- **Three compounding R3 failures** (together dropped them to ~241st):
  1. **Jasper visualizer bug crashed their submission** — effectively did not trade R3. Expected ~100k, got near-zero.
  2. **Overfit the quadratic smile** — fit was not robust day-to-day.
  3. **Hedging cost ruinous.** Paid ~$50k/day crossing spread to delta-hedge. Measured: "delta exposure at avg 150 contracts" vs spread cost — spread cost outweighed unhedged delta P&L by ~100×. Dropped hedging entirely.
- Two things they missed (what #2 team did):
  - **Volcanic rock itself was mean-reverting** — they never even checked because "the whole thing is options, right?"
  - **IV scalping (delta-neutral so you isolate IV as a tradable series)** + **gamma scalping**. They tested gamma-scalping; made 100× less than #2. Also tested being net-short theta — not enough P&L.

### Round 4 — Magnificent Macarons (cross-island arbitrage)

- Local island ↔ Pristine island. Transport fee = 1 seashell. Storage = 0.1 seashells per macaron per tick (short or long — penalty either way). **Import tariff was NEGATIVE** (you get paid to import). Also given sunlight + sugar series.
- **Break-even formula** is derivable from (transport, import_tariff, storage, export_tariff). One-sided: only importing is profitable; exporting always loses.
- **Hidden aggressive-buyer exploit:** on the local island there was a bot that "really liked macarons and bought in max volume." A bid placed at mid price always got lifted, regardless of size — but tiny miss on price and it wouldn't fill. **Calibrate exact fill level empirically.** Arbitraging this way yielded **~1.4 seashells per macaron × ~100,000 trades ≈ 146k.**
- **Convert-cap trick missed (left on table, doubles P&L).** Conversion cap = 10 units/tick. They sold 10/tick — limited by ticks when buyer absent. Optimal = sell 30 at a time to keep a stockpile, so you can convert every tick even when the bot is AWOL. Net of extra storage + drift ≈ negligible (~12k cost for the expansion). **Would have roughly doubled** R4 P&L. #2 team also missed this.
- **Pricing rounding optimization** (did NOT matter this year but did in P2): bid @ 10 vs @ 11 when mid = 10.5 → measure the empirical fill-probability vs extra-per-roundtrip tradeoff. Smaller roundtrip margins → round aggressively; bigger margins → round conservatively to maximize fill.
- **Sunlight + sugar were a red herring for the arb, but genuinely predictive via linear regression.** The speaker deliberately ignored them because in Prosperity 2 they were "a red herring" too. In P3 they DID predict price direction — but the arb was so much bigger that regression-on-sunlight was dominated. **Key: always estimate expected P&L of each candidate strategy before committing.**

### Round 5 — Full Market + Counterparty Names Revealed

- In R5 you SEE who is on the other side of every trade. Three archetypes:
  - **Noise traders** (retail) — you want to trade with them (capture).
  - **Market makers** — beat them, don't copy them. (Copy-trading a market maker = guaranteed loss because they make money on spread, not direction.)
  - **Informed traders** — copy them, don't trade against them.
- **The Olivia signal.** One counterparty ("Olivia") was an informed trader with **18/18 perfect tops & bottoms across 3 products × 3 days.** Just detect Olivia trading a product and copy direction.
- **Croissant YOLO.** Olivia traded croissants perfectly. Team abandoned their stat-arb algo, went 100% long/short on croissants in Olivia's direction, accepting residual basket-premium exposure (worst-case loss estimated ~20k). P&L from following > P&L from their own algo.
- **The Olivia signal was visible from Round 1 data** if you plotted trades per counterparty and segmented by P&L trajectory. Top teams had a ~200k head start by R5 because they started Olivia-copying from R2 onward.
- Meta: segment ALL counterparties by P&L curve and position pattern from day 1. Traders with flat-line-up P&L and large position swings = informed. Traders with consistent flat P&L despite large volume = market makers.

## Per-Round Breakdown (MANUAL)

### M1 — Currency conversion graph (trivial)
LeetCode-medium. 4 currencies, find best cycle of ≤ trades. "Every team got this."

### M2 — Container game (10 crates, multipliers, hidden inhabitants; payoff = 10,000 × mult / (inhabitants + pct_of_field_picking)) — THE OVERSHOOT TRAP
- Nash equilibrium = all crates equal EV. Not everyone plays Nash → exploit.
- Their prior (calibrated to gut): 50% random, 10% Nash, 20% psychological numbers (73, 37, 90, 10), + naive-EV-peak + MC sims.
- Picked crate 80 (highest EV under their prior).
- **Error they called out themselves: collapsed the distribution** — should have rolled the dice and played mixed. Picking the argmax under your own simulated prior is exploitable and introduces bias.
- Empirical finding: **~50% of people do NOT play random; the field is far closer to Nash than they'd assumed.** Their prior was "garbage."
- **73 and 37 are disproportionately picked** (Veritasium "pick a random number" result — people think "nice-random" numbers are nice). Model it, but don't over-model.

### M3 — Flipper/turtle dual-bid
- Uniform seller reserve in [160, 200] AND [250, 320]. Set 2 bids. Profit = 320 − bid_i conditional on fill.
- **Bid 1 optimum = 200.** Derivative of payoff, closed form. Always quote the high end of the range when you're bounded.
- **Bid 2 has an average-bid penalty:** below-average penalty is **cubic**, above-average penalty is **linear.** → asymmetry pushes you to just-above the expected average. Nash = 285. They picked **290**. Empirical average 286. Lost only 4%.
- Watchout: **griefers** (people make burner accounts to push the average up and tank everyone else). Happened in Prosperity 2 container game; accounts got banned.

### M4 — Suitcase game (20 cases, multipliers, pick up to 3; case-2 fee = 50k, case-3 fee = 100k)
- First Nash check: EV per suitcase ≈ 56k. Case 1 free → take. Case 2 @ 50k fee → EV = +6k → take. Case 3 @ 100k fee → negative EV → **do not take a third case.**
- Recalibrated prior using R2 empirical field data: 55% Nash, 12.5% concentrated-Nash (just the high multipliers), inverse-Nash, 15% random, 12.5% psychological.
- Top-EV cases: **47, 83, 89.**
- Came back from 241st → 8th via this round.

### M5 — Portfolio allocation over 10 products with sentiment news
- **Goldberg-terminal-style problem.** Each product has a news article (positive/negative sentiment). Predict magnitude of price move per product. Allocate percent of portfolio across 10 products.
- **Fee is QUADRATIC in allocation** → sweet spot is NOT 100% on your best pick; diminishing returns. Optimal total allocation was ~83% of portfolio.
- Map products 1:1 to previous-year products. Predicted magnitudes: e.g., cacti needles −65% (they softened this, regretted softening — should have trusted).
- Solve the constrained optimization (quadratic fee, linear predicted returns, sum ≤ 1).
- Performed top-20 on this round.

## Cross-Cutting Meta Lessons (Author's Final Slide)

- **Simple > complex, but simple is not easy to implement.** 5 lines of trading logic behind hours of verified helpers.
- **Don't hardcode** and don't cheat (bans happen).
- **All alpha reduces to buy low / sell high.** "You don't need crazy ML. Options are just IV-trade buy-low-sell-high."
- **Trading ≈ hacking.** You search for "this happens and shouldn't" (= alpha = bug). Everything you see worked because of a thousand failures they didn't show.
- **AI discipline:** use AI for helper functions you can verify; never one-shot the algo. "If you take my code, pass it to Claude Code and say 'make it for this round,' it's going to break if anything is different — Claude can't see data or backtest results."
- **Gaming & chess map to trading.** IMC specifically recruits esports / chess players. Need 8-24h focus endurance. On tariff-tweet days "every trader I knew was in the office til 3 am recalibrating."

## Delta vs Transcript 2 (P3 Winners Panel) — What's New Here

1. **Exact arbitrage mechanics for macarons** (import-only, break-even formula, 30-unit stockpile trick).
2. **Explicit R3 failure mode taxonomy** (visualizer crash, quadratic overfit, hedge cost > delta P&L).
3. **Counterparty-segmentation methodology** for finding Olivia from R1 data (before R5 revealed names).
4. **Penny-jumping only works in this simulator** (doesn't work in real crypto — speaker tested).
5. **Manual-round Nash + prior-calibration framework** end-to-end, with observed failures (P2 container overshoot, P3 container collapse, P3 flipper 290).
6. **Fee-quadratic portfolio-allocation optimum** for R5 manual.

---

## Raw Quotes (verbatim)

> "After round two we were in seventh. … Cost of hedging was insane. We were paying around $50,000 a day just to hedge. … the spread cost outweighed the delta exposure by like 100x on the submission day. So we just got rid of delta hedging."

> "If you put a bid to sell at the mid price of any size, it would get taken always, no matter what size you put … Some guy just really liked macarons and was buying it in max volume on the island … 1.4 sea shells per macaron. You do this 100,000 times in a round, you made 146k."

> "We would want … a stockpile so that we're always taking advantage of the fact that we can convert 10 on a turn. If we sell 30 on a turn, we can go two turns without trading and still make the arbitrage. … This would have doubled our P&L."

> "Olivia 18 out of 18 perfect predictions. So all you need to do in your code is basically detect whenever Olivia trades a product, just copy it. … Other top teams already knew about this signal from round one. If you were smart enough and you did your due diligence, you would have figured this out from round one."

> "You're trading against hard-coded bots. You're not competing with each other … IMC has coded a bunch of trading bots that have their own logic and your job is to extract as much value as you can."

> "We bought at 9,996 and our P&L was 4, which means … the way they actually calculate P&L is through the mid price of the best bid and the best ask."

> "73. It's a real psychological thing. … Veritasium did a video where he asked a lot of people … 37 was predicted disproportionately. … Model for psychological effects, but don't over-model for it. … 50% of people do not play randomly. People play much closer to Nash than you would actually expect."

> "If your code depends on just one hyperparameter, and the region around the optimum is stable … we found that this produces the highest P&L on all the back tests and the region was stable. With slight modifications to our hyperparameter, we still maintain really good profit. So one highest P&L, two if you take the first derivative, it's a stable point in hyperparameter space."

> "If you take my code, pass it to cloud code and say 'make it for this round,' it's going to — if it's different, cloud code is not going to know why it didn't work. It can't see the data. It can't see the back test results."

> "Trading is literally just buying low, selling high, and everything else is just technical jargon. … No matter how complicated you might think options are, if you just isolate IV or gamma and then buy it low, sell it high, you're trading options."
