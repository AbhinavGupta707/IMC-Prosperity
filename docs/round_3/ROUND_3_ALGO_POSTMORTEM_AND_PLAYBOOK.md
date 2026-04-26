# Round 3 Algorithmic Postmortem And Future Playbook

Date: 2026-04-26

This note captures the high-value lessons from Round 3 after final results,
the Velvet/options branch, and the post-round clue that a top-10 team used
Black-Scholes plus gamma scalping.

## Final Result Snapshot

Submitted combined strategy:

- Hydrogel sleeve: `submission_r3_hydrogel_publicguard_1m9988_tw32.py`
- Velvet/options sleeve: static product-switch v2 with terminal flattening
- Combined artifact:
  `outputs/submissions/submission_r3_combined_hydrogel_publicguard_1m9988_tw32_velvet_v2_flat980.py`

Final official PnL:

- Total: 178,797
- HYDROGEL_PACK: 54,597
- VELVETFRUIT_EXTRACT: 22,704
- VEV_4000: 29,725
- VEV_4500: 33,971
- VEV_5000: 26,486
- VEV_5100: 7,633
- VEV_5200: 5,380
- VEV_5300: -175
- VEV_5400: 276
- VEV_5500: -1,800
- VELVET plus options total: 124,200
- Options-only total: 101,496

Leaderboard context from user:

- Team ranked around the 100-110 area.
- Top 100 threshold was around 190k.
- First place algorithmic was around 346k.
- Multiple top teams were around 280k-300k.

This was a strong result, but the spread to the top suggests we captured
only part of the structural option alpha.

## What Worked

### 1. Hydrogel Research Process Was Sound

The Hydrogel sleeve followed a good research sequence:

1. Isolate the product.
2. Understand the path behavior.
3. Compare families instead of only local parameters.
4. Use official simulator uploads for calibration.
5. Promote strategies based on realized PnL, attribution, and robustness.

The final Hydrogel result of 54,597 was close to the publicguard/fallback
research expectation and materially better than early Hydrogel-only versions.
This was not the primary source of the final gap to top teams.

### 2. Velvet Static Thresholds Found Real Edge

The static Velvet/options sleeve was crude but not useless. It extracted
124k from the Velvet complex on the final hidden 1M ticks. That means the
public research and official 100k simulator diagnostics found a genuine
structural inefficiency, not pure overfit.

The main strength was simplicity:

- product-level thresholds
- wide enough bands to survive unseen data
- terminal flattening to remove hidden-fair settlement uncertainty
- no timestamp path oracle

### 3. Official Calibration Discipline Helped

The repeated 100k uploads avoided the worst failure mode: trusting local
replay blindly. We correctly learned that:

- local rankings were useful nearby, but not exact;
- official hidden data could change drawdown shape;
- terminal flattening mattered;
- overfit path logic should be disabled for final.

## Core Miss

The main miss was not spending too much time on Hydrogel. The deeper miss was
an asset-geometry mismatch in the Velvet/options sleeve.

We treated vouchers too much like independent price paths:

```text
product price -> buy threshold / sell threshold -> target position
```

But vouchers are options. The natural state variables are:

```text
underlying spot
strike
TTE
implied volatility
realized volatility
delta
gamma
vega
theta
smile residual
hedge cost
settlement/mark behavior
```

We computed some Black-Scholes diagnostics, but the live strategy did not
become a Black-Scholes/Greak-aware portfolio strategy. The final Velvet
strategy remained a static product threshold strategy.

## Did We Use Black-Scholes Plus Gamma Scalping?

No, not in production.

We did use Black-Scholes-adjacent tools:

- IV and moneyness analysis.
- BSM fair values.
- Smile residuals.
- Greek calculations.
- `SmileCache`, `R3DeltaBudget`, and disabled hedge scaffolding.
- Rolling-IV and cached-smile diagnostic sweeps.

But we did not build a proper gamma scalper.

A true gamma scalper would:

1. Estimate implied volatility from voucher prices.
2. Estimate realized volatility/regime from VELVET movement.
3. Buy options when implied vol is cheap versus expected realized vol.
4. Sell options when implied vol is rich versus expected realized vol.
5. Delta hedge dynamically with VELVET and/or deep ITM vouchers.
6. Rebalance when delta drifts enough to justify spread cost.
7. Attribute PnL into option mark PnL, hedge cash, gamma scalp, theta, vega,
   spread cost, and settlement mark.

The submitted strategy did not do this. It bought and sold individual products
at static levels.

## Why This Matters

Static thresholds can win when prices are obviously wrong. Gamma scalping can
win even when options are only relatively wrong, because it harvests convexity
through time.

The top-10 clue is important because it points to a different alpha family:

```text
implied volatility vs realized volatility + dynamic delta hedging
```

Our research had early IV/smile sweeps, but they were not enough to reject the
family. They were incomplete implementations:

- no full delta-hedged portfolio accounting;
- no gamma/theta/vega attribution;
- no realized-volatility forecast objective;
- no hedge-frequency cost optimization;
- no deep ITM synthetic hedge design;
- no official diagnostic upload isolating long-gamma and short-gamma behavior.

The lesson is that a weak prototype of a correct family should not be treated
as evidence that the family is weak.

## The First-Principles Lesson

Before optimizing a strategy, classify the instrument by payoff geometry.

For each new round/product, explicitly decide whether the product is:

- delta-one mean-reversion/trend;
- option/convexity;
- basket or spread;
- conversion/settlement;
- auction/rank game;
- hidden bot/liquidity game;
- inventory liquidation game.

Then build the research primitive around that geometry.

For Round 3, once vouchers were known to be options, the first production-grade
research object should have been a Greek-aware portfolio simulator, not a
threshold sweeper.

Correct order:

1. Map payoff geometry.
2. Define state variables implied by that geometry.
3. Build PnL attribution for those variables.
4. Estimate oracle or upper bound by strategy family.
5. Implement the simplest correct version of each high-potential family.
6. Only then tune parameters.

We inverted steps 3-5 on Velvet: static thresholds scored well quickly, so we
spent most tuning budget around them before fully exhausting option-native
families.

## Hardcoding Clarification

IMC's clarification matters:

Allowed and valuable:

- hardcoded parameters inferred from public data;
- reverse-engineered bot behavior;
- fitted IV curve coefficients;
- strike-specific risk limits;
- quote-update rules;
- regime thresholds;
- TTE-specific model parameters;
- market-maker behavioral rules.

Not allowed or dangerous:

- hardcoded future price paths;
- hardcoded exact timestamp positions;
- external/non-public data;
- platform bug exploitation;
- pricing data pasted directly as future knowledge.

The practical rule:

```text
Hardcode market structure, not the future path.
```

We were right to disable path-oracle-like behavior for final. But for future
rounds, we should be more aggressive about hardcoding inferred structural
behavior when it is derived from public tapes and expressed as rules.

## What We Should Have Explored More

### 1. Realized Volatility Versus Implied Volatility

For each strike and time window:

- current IV;
- rolling realized volatility of VELVET;
- forward realized volatility after entry;
- IV minus expected realized vol;
- PnL of long-gamma and short-gamma portfolios after hedge cost.

This should be evaluated as a volatility trade, not a price forecast.

### 2. Delta-Hedged Option PnL

Every option trade should decompose into:

- option entry edge;
- option mark-to-market;
- hedge cash PnL;
- residual delta PnL;
- gamma scalp PnL;
- theta/vega approximation;
- spread/slippage cost;
- terminal hidden-fair contribution.

Without this attribution, we cannot tell whether a strategy is earning from
volatility, direction, stale quotes, or accidental settlement exposure.

### 3. Deep ITM Vouchers As Hedge Instruments

VEV_4000 and VEV_4500 should not only be judged as standalone products.
They can also act as synthetic delta instruments with different spreads,
capacity, and quote behavior versus VELVET.

Future options research should compare hedging with:

- VELVET only;
- deep ITM vouchers only;
- hybrid hedge basket;
- strike-specific hedge ratios.

### 4. Cross-Strike Surface Packages

Instead of trading each voucher independently, build packages:

- long cheap IV / short expensive IV;
- butterflies for curvature residuals;
- call-spread residual packages;
- delta-neutral long-gamma packages;
- delta-neutral short-vega packages.

The objective should be residual convergence and Greek exposure control, not
single-product threshold PnL.

### 5. Bot And Quote Behavior Reverse Engineering

Hardcoding guidance means this is fair game if based on public data.

Research should inspect:

- quote update frequency by product;
- stale option quotes after VELVET moves;
- deterministic spread placement;
- hidden bot fair-value rules;
- volumes by side and time;
- whether one side lags spot more than the other;
- whether bots react to our fills or only to time/price.

Top strategies may have encoded these rules as hardcoded parameters rather
than generic adaptive models.

## Future Round Research Architecture

Use this sequence before tuning:

### Phase 1: Product Geometry Map

For each product:

- payoff type;
- dependencies;
- settlement rule;
- inventory limit;
- likely hidden fair;
- natural arbitrage relations;
- natural risk factors.

### Phase 2: Family-Level Oracles

Build rough upper bounds for each family:

- directional;
- mean reversion;
- market making;
- relative value;
- volatility/gamma;
- conversion/settlement;
- bot exploitation.

Do not optimize a low-ceiling family just because it is easy.

### Phase 3: Correct Minimal Prototype

Implement the smallest faithful version of each high-ceiling family.

For options, this means:

- BSM or alternative pricing model;
- IV inversion;
- Greeks;
- dynamic delta hedge;
- hedge threshold;
- transaction cost model;
- PnL attribution.

### Phase 4: Official Diagnostic Uploads

Use small uploads that isolate hypotheses:

- long-gamma only;
- short-gamma only;
- delta-neutral smile residual;
- deep ITM hedge only;
- passive stale-quote probe;
- terminal-settlement probe.

The upload goal is not immediate max PnL. It is calibration of the simulator
to the research model.

### Phase 5: Robust Assembly

Only combine sleeves after each sleeve has:

- positive realized official PnL;
- clear attribution;
- acceptable drawdown;
- cross-slice robustness;
- known failure modes;
- position/settlement control.

## Decision Rules For Future Rounds

1. Do not let a profitable crude strategy crowd out the correct asset-native
   strategy family.
2. Do not reject a family from a naive prototype.
3. Build attribution before heavy sweeps.
4. Use hardcoding for structural reverse engineering, not path memorization.
5. Treat official simulator uploads as calibration experiments, not only as
   leaderboard attempts.
6. For options, never evaluate price PnL alone. Always evaluate Greek-adjusted
   and hedge-adjusted PnL.
7. If theoretical/oracle alpha is much larger than realized alpha, the next
   research question is family mismatch, not parameter tweaking.

## Round 3 Artifact Map

Velvet/options branch artifacts have been merged into the main repo:

- `outputs/round_3/velvet_options_research/`
- `outputs/round_3/velvet_static_threshold_robustness/`
- `outputs/round_3/velvet_final_pass_research/`
- `outputs/round_3/velvet_hybrid_profile_research/`
- `outputs/round_3/velvet_cycle_core_research/`
- `outputs/round_3/velvet_smile_cached_research/`
- `outputs/round_3/velvet_call_spread_arb_research/`
- `outputs/round_3/velvet_passive_maker_research/`
- `outputs/round_3/velvet_trade_event_research/`
- `outputs/round_3/velvet_official_testing_results/`
- `src/scripts/round_3/run_velvet_*.py`
- `src/strategies/round_3/velvet_options_rolling_iv.py`
- `src/engines/r3_velvet_options_engine.py`
- `src/engines/r3_velvet_options_factory.py`

Important caveat: the merged rolling-IV engine is a diagnostic artifact, not
the final best Velvet strategy. The final best Velvet strategy lived mostly in
standalone submission files under `outputs/submissions/`.

## Highest-Value Fix For Next Time

Before writing strategy code, write the following one-page brief:

```text
What is this product's payoff geometry?
What are its state variables?
What PnL decomposition proves the alpha source?
What is the oracle ceiling by family?
What minimum correct prototype can falsify each family?
What official upload isolates each hypothesis?
```

If that brief is missing, pause tuning. The risk is not slow progress; the risk
is optimizing the wrong abstraction.
