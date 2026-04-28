# Round 4 Mark Bot-Policy / Hazard Research

Date: 2026-04-27

## Objective

The IMC hint suggests classifying Mark behavior and anticipating future activity.
This research asks a stricter question than raw markouts:

Can we predict future Mark events from current book state and recent Mark flow
well enough to design execution probes?

This is a transparent rule-search, not a black-box model. With only three
historical days, the first useful test is whether simple conditions survive
leave-one-day validation.

## Artifacts

Scripts:

`/Users/abhinavgupta/Desktop/IMC/src/scripts/round_4/audit_mark_policy_hazard.py`

`/Users/abhinavgupta/Desktop/IMC/src/scripts/round_4/calibrate_mark_policy_official.py`

Outputs:

`/Users/abhinavgupta/Desktop/IMC/outputs/round_4/mark_policy/`

Key files:

- `all_base_rates.csv`
- `all_rule_summary.csv`
- `all_loo_rules.csv`
- `official_rule_calibration.csv`
- `strong_rule_official_calibration_summary.csv`

## Targets Tested

- `Mark55` VELVET taker buys
- `Mark55` VELVET taker sells
- `Mark38` HYDROGEL taker buys/sells
- `Mark38` VEV_4000 taker buys/sells
- `Mark22` OTM voucher basket sells

Features included current book state, schedule flags, recent same-product Mark
history, and recent Mark22 basket history.

Important correction: the first run exposed a leaked future-move feature. I
removed all `future` columns from feature search and reran before trusting
results.

## Base Hazard Rates

Some Marks are so frequent that "predict within 5k/10k" is almost trivial:

- `Mark55` VELVET buy within 5k: historical base rate ~60%-67%.
- `Mark55` VELVET sell within 5k: historical base rate ~62%-64%.
- `Mark38` HYDROGEL buy/sell within 5k: historical base rate ~53%-62%.

This matters. A rule with lift 1.1 at a 60% base rate is not a clean exploit by
itself. It needs to translate into passive fill quality or inventory management.

## Historical Rules That Survived 3/3 LOO

Best non-leaky results:

| Target | Horizon | Rule | Mean test lift | Min test lift | Qty coverage |
| --- | ---: | --- | ---: | ---: | ---: |
| Mark55 VELVET buy | 1k | high recent Mark67 VELVET buy qty, 30k window | 1.50 | 1.15 | 7.5% |
| Mark55 VELVET sell | 1k | high recent Mark22 VELVET sell qty, 30k window | 1.38 | 1.06 | 9.4% |
| Mark55 VELVET sell | 1k | high recent Mark22 VELVET sell count, 30k window | 1.34 | 1.06 | 12.5% |
| Mark55 VELVET sell | 1k | high recent Mark67 VELVET buy count, 30k window | 1.16 | 1.12 | 25.8% |
| Mark38 VEV4000 buy | 1k | low recent Mark38 VEV4000 buy activity, 10k window | 1.12 | 1.08 | 54.6% |

Interpretation:

- VELVET has the clearest Mark event-hazard structure.
- Mark55 flow appears clustered after other VELVET Mark activity.
- Mark38 VEV4000 has a weak cooldown-style rhythm, but this is probably more
  useful for timing/risk than for a standalone strategy.

## Official 100k Calibration

I applied the historical leave-one-day rules to
`r4 Sim Results/sellonly/497595.log` without retraining on official data.

Most important official-calibrated result:

| Historical rule | Official lift | Official support | Official qty coverage |
| --- | ---: | ---: | ---: |
| Mark55 VELVET sell within 1k after high recent Mark67 buy count | 2.37 | 113 rows | 27.8% |

This is the strongest Mark hazard result so far. It is narrow but replicated:
after Mark67 VELVET buying activity, Mark55 VELVET sell flow becomes much more
likely in the next 1k ticks.

The historical `Mark55 buy after Mark67 buy qty` rule did **not** calibrate
officially because the official Mark67 quantity never reached the historical
threshold. That is an important robustness warning.

HYDROGEL Mark38 historical hazard rules did not calibrate well officially.
The Mark38/HYD edge still exists as passive-maker economics, but event timing
from simple rules is not stable.

## What This Means For Alpha

This supports a narrower "bot exploit" thesis:

1. `Mark55` VELVET flow is predictable enough to test a passive execution probe.
   - Not follow/fade by crossing.
   - Quote passively or skew VELVET quotes after Mark67/Mark22 VELVET activity.
   - Keep inventory cap small because this is an execution edge, not a huge
     directional thesis.

2. `Mark38` HYDROGEL remains economically large but not timing-predictable from
   simple rules.
   - Best handled by the HYDROGEL session as passive quoting / inventory-risk
     design, not as a standalone Mark hazard trigger.

3. `Mark22` OTM baskets are structurally real but direct hazard uplift is not
   strong enough yet.
   - Use as option-flow state and negative-control source.

4. Do not build a broad Mark model.
   - The robust result is specific: VELVET Mark state -> Mark55 taker flow.
   - Broad overlays risk turning a small execution edge into a large inventory
     mistake.

## Next Controlled Probes

1. `VELVET_MARK55_PASSIVE_PROBE`
   - Trigger after high recent Mark67 VELVET buy count or Mark22 VELVET sell
     activity.
   - Place small passive VELVET quotes on the side likely to be hit by Mark55.
   - Tight inventory cap, fast flatten/decay.

2. Matched negative control:
   - Same quote schedule/frequency triggered by generic VELVET trade count or
     Mark55 self-history, not Mark67/Mark22.
   - If control performs similarly, the alpha is generic volatility/regime, not
     Mark identity.

3. `VEV4000_MARK38_COOLDOWN_PROBE`
   - Very small diagnostic only.
   - Uses low recent Mark38 VEV4000 activity as a timing state.
   - Needs strict official calibration because local rule is weak and product
     interaction with option schedule can dominate.

4. HYD handoff:
   - Share Mark38/HYD passive-maker economics with HYDROGEL session, but do not
     implement a Mark38 timing rule yet.

## Passive Probe Follow-Up

New scripts:

`/Users/abhinavgupta/Desktop/IMC/src/scripts/round_4/test_mark55_passive_probe.py`

`/Users/abhinavgupta/Desktop/IMC/src/scripts/round_4/audit_mark55_passive_opportunity.py`

New outputs:

- `mark55_passive_probe_summary.csv`
- `mark55_passive_opportunity_panel.csv`
- `mark55_passive_opportunity_summary.csv`

### Local Wrapper Result

The first wrapper test is not locally encouraging:

| Variant | Local total delta | VELVET maker buy qty | Interpretation |
| --- | ---: | ---: | --- |
| periodic touch q5 target -150 | +17 | 3 | noise-level control win |
| Mark67 touch q5 target -150 | -15 | 19 | no local edge |
| Mark67 inside q5 target -150 | -228 | 31 | local replay undercredits inside quotes and realized path loses |
| always touch q5 target -150 | -221 | 68 | generic passive VELVET bidding is adverse locally |

This does **not** disprove the official inside-quote hypothesis, but it does
show that exact-price historical replay is not a reason to promote the idea.

### Opportunity Audit

The fill bottleneck is severe. In the official 100k sellonly log:

- Mark67-count gate active: 113 rows.
- Next-step Mark55 sell flow during that gate: 6 steps / 35 units.
- Exact prior-touch 30% fill proxy: only 1 unit.
- One-tick-inside potential proxy: 28 units.
- Inside proxy markout: +43 at 1k, +103.5 at 5k in the 100k slice.

So this is a small calibration experiment, not the main R4 alpha source. If it
scales linearly to 1m ticks, the order of magnitude is around hundreds to low
thousands, not tens of thousands.

Timing is also not a clean exploit:

- Historical Mark67 buys -> next Mark55 sell within 1k only ~16%, within 5k
  ~63%.
- Official Mark67 buys -> next Mark55 sells appeared around 1.3k, 1.6k, and
  4.1k; none within 1k.
- Delayed 1k-5k gates did not dominate the original 30k count gate. They improve
  some 1k opportunity numbers but hurt 5k and have very small support.

### Upload Calibration Files

Created two diagnostic submissions:

- `/Users/abhinavgupta/Desktop/IMC/outputs/submissions/r4/submission_r4_probe_mark55_m67_inside_q5.py`
- `/Users/abhinavgupta/Desktop/IMC/outputs/submissions/r4/submission_r4_probe_mark55_always_inside_q5.py`

Both compile and pass local full replay. Local replay:

| File | Local total | VELVET PnL | VELVET maker qty |
| --- | ---: | ---: | ---: |
| Mark67 inside q5 | 886,736 | 109,621 | 31 |
| Always inside q5 | 886,213 | 109,098 | 91 |

Recommended use: upload both as a matched pair. If Mark67-inside improves
officially while always-inside does not, the official simulator is rewarding the
counterparty anticipation. If both lose or both win similarly, Mark55 is not a
distinct enough alpha source.

Current judgment: Mark55 is a useful execution calibration probe, but not where
the main gap to theoretical maximum lives. The larger unexploited space remains
dynamic inventory/recycling in HYDROGEL and the VELVET/options complex.

## Official q5 Upload Results

New official artifacts:

- `r4 Sim Results/m67 q5.zip`
- `r4 Sim Results/always q5.zip`

Saved analysis outputs:

- `/Users/abhinavgupta/Desktop/IMC/outputs/round_4/mark_policy/q5_official_upload_summary.csv`
- `/Users/abhinavgupta/Desktop/IMC/outputs/round_4/mark_policy/q5_official_extra_velvet_fills.csv`
- `/Users/abhinavgupta/Desktop/IMC/outputs/round_4/mark_policy/timestamp_420_audit.csv`

### Result Versus Validated Baseline

| Candidate | Official PnL | Delta vs validated | VELVET delta | VELVET final pos | Extra VELVET qty |
| --- | ---: | ---: | ---: | ---: | ---: |
| validated | 68,655.81 | 0.00 | 0.00 | -200 | 0 |
| Mark67 q5 inside | 68,589.99 | -65.81 | -65.81 | -150 | +50 |
| always q5 inside | 68,449.99 | -205.81 | -205.81 | -150 | +96 |

This is exactly mixed calibration evidence:

- The Mark filter mattered. `Mark67 q5` beat `always q5` by ~140 PnL and had
  much less noisy early churn.
- The overlay still lost to the no-q5 baseline because buying VELVET reduced a
  profitable structural short.
- The effect was entirely VELVET; HYDROGEL and voucher PnL were unchanged
  versus the validated baseline.

### What Filled

`Mark67 q5` added 50 VELVET buy units:

- 45 units bought from `Mark 55`
- 5 units bought from `Mark 67`

So the counterparty prediction worked: the probe really did capture mostly the
target Mark55 sell flow.

The problem was holding the fills. The extra `Mark67 q5` buys had positive
short-horizon markouts:

- +1.52 average at 100 ticks
- +2.47 average at 1k ticks
- +0.79 average at 5k ticks

but negative longer-horizon / terminal contribution:

- -0.44 at 20k
- -0.91 at 30k
- about -1.6 to final mid proxy
- official VELVET PnL delta: -65.81

Interpretation: Mark55 q5 is not a hold-to-end alpha. It is a short-horizon
liquidity/recycling edge. If used at all, it must buy from Mark55 and then
re-short/recycle quickly, preserving the core -200 VELVET structural exposure.

### Always q5 Failure Mode

`always q5` added 96 extra VELVET units and was worse:

- It bought early at high prices from both `Mark55` and `Mark67`.
- It also triggered base schedule sells shortly afterward, creating noisy
  buy/sell churn.
- This confirms that generic inside VELVET quoting is adverse; Mark identity is
  doing useful filtering, just not enough by itself.

### Updated Mark55 Judgment

Do not upload q5 as a final overlay in its current form.

Potential next diagnostic only:

- `Mark67/Mark55 recycler`: allow passive Mark55 buy fills, but immediately
  try to re-short back to -200 after a small profit / time horizon.
- Measure whether the official simulator lets us realize the positive 100-1k
  markout without paying too much spread or creating churn.

Expected value is likely small. Based on the 100k slice, even a clean recycler
looks like hundreds to low-thousands over the 1m final, not the main gap to
theoretical maximum.

### Timestamp "420" Pattern

The timestamp-contains-`420` idea looks like multiple-testing noise, not a
usable bot exploit.

Historical all-Mark buy rows:

- `420` timestamp bucket: 50 rows / 204 qty.
- 1k win rate: 16%, qty-weighted edge -4.72.
- 5k win rate: 26%, qty-weighted edge -6.04.
- This is not better than the non-420 base.

Official sellonly:

- only 2 qualifying Mark buy rows / 11 qty.
- 1k and 5k win rate: 0%.
- qty-weighted edge: -11.36 at 1k, -26.36 at 5k.

Some tiny subgroups show 100% win rate, but sample sizes are 1-3 rows. Treat
them as noise unless they survive cross-day, official, and mechanism checks.
