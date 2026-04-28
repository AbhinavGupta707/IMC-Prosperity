# Round 4 Mark Alpha — First-Principles Re-Audit

Date: 2026-04-27

## Why this doc exists

Prior R4 Mark research (`MARK_BEHAVIOR_CLASSIFICATION`,
`MARK_POLICY_HAZARD_RESEARCH`, `MARK_CONDITIONED_SCHEDULE_AUDIT`,
`MARK55_RECYCLER_OFFICIAL_READOUT`, `R4_NATIVE_ALPHA_OPTIONS_REVIEW`,
`HYD_OWN_FILL_COUNTERPARTY_ATTRIBUTION`) converged on:

- Mark IDs are real but small individually.
- Mark22 OTM voucher basket flow is the most coherent program pattern.
- Mark55/67 produced an upload-calibratable execution probe but the
  effect is hundreds, not tens of thousands.
- HYD own-fill Mark identity is regime-confounded.

This re-audit asks the harder question from scratch: are there Mark
behaviors we missed entirely, sequences we did not test, or basket
spillovers we never measured? It also delivers the user-requested
paired Mark22 experiment (treatment + control) so the question
"does Mark identity add alpha beyond regime/timing?" can be answered
directly.

## Artifacts

Audit script:

`/Users/abhinavgupta/Desktop/IMC/src/scripts/round_4/audit_mark_first_principles_v2.py`

Audit outputs (CSV):

`/Users/abhinavgupta/Desktop/IMC/outputs/round_4/mark_first_principles/`

- `basket_spillover_summary.csv`
- `basket_intervals.csv`
- `basket_next_within_summary.csv`
- `paired_arm_diff.csv`
- `mark67_next_seller_summary.csv`

Paired upload candidates:

- `outputs/submissions/r4/submission_r4_probe_m22sell_recycle_treatment.py`
- `outputs/submissions/r4/submission_r4_probe_m22sell_recycle_control.py`

Local smoke-test runner:

`/Users/abhinavgupta/Desktop/IMC/src/scripts/round_4/smoke_paired_m22_recycle.py`

## Structural facts re-derived from raw trades

Counts in `data/raw/round_4/trades_round_4_day_{1,2,3}.csv`:

- Total named-Mark trades: 4,281 across 3 days.
- Distinct Marks: 7 (`Mark 01, 14, 22, 38, 49, 55, 67`).
- Buyer-only Mark: `Mark 67` (never sells in any product, in any day).
- Mark22 trade direction: 1,330+ sell rows vs 41 buy rows. Effectively
  always-short.
- HYDROGEL bilateral: only `Mark 14` <-> `Mark 38`. No third party.
- OTM voucher basket: `Mark 22` is seller, `Mark 01` is buyer in
  ~95% of rows.
- Top voucher pairings: 317 rows of `Mark01 <- Mark22` in each of
  VEV_6000 and VEV_6500; 299 in VEV_5500; 263 in VEV_5400.

Implication: market microstructure is sticky-pair. The simulator
cannot place us between Mark01 and Mark22 unless our quote is strictly
better than Mark01's bid. This restricts execution-edge plays to
counterparties where we can credibly outbid the structural maker.

## Mark22 OTM basket structure

`detect_mark22_baskets` found 317 distinct (day, timestamp) groups.

Top basket compositions across 3 days:

| Composition (sells from Mark22) | Count |
| --- | ---: |
| VEV_5400 / 5500 / 6000 / 6500 | 115 |
| VEV_5300 / 5400 / 5500 / 6000 / 6500 | 108 |
| VEV_5200 / 5300 / 5400 / 5500 / 6000 / 6500 | 27 |
| VEV_5500 / 6000 / 6500 | 20 |

Inter-basket spacing day 1 (97 deltas):

| stat | min | p25 | p50 | p75 | p90 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ticks | 100 | 3,000 | 6,900 | 14,200 | 23,600 | 51,500 |

Conditional next-basket-within-H rate:

| Day | 1k | 5k | 10k | 30k |
| --- | ---: | ---: | ---: | ---: |
| 1 | 8.2% | 35.7% | 60.2% | 94.9% |
| 2 | 9.5% | 34.7% | 51.6% | 96.8% |
| 3 | 10.5% | 49.2% | 70.2% | 96.8% |

So baskets cluster: a basket today implies another within 30k with
near-certainty, but the next-1k probability is only ~10%. We cannot
front-run within a single basket (same timestamp), but we can reason
about the next-cluster window.

## Mark22 basket spillover into untouched strikes (NEW)

For each basket, `basket_spillover_summary.csv` records the
post-basket signed mid change at every voucher symbol, partitioned by
whether that symbol was hit by the basket.

Top finding: `VEV_6000` and `VEV_6500` mid never moves (std_mid_change
= 0 at all horizons across all days). These deep-OTM strikes have
static quotes — no exploitable mid drift.

Within-basket strikes (`VEV_5400`/`5500` when hit) show essentially
flat mid changes (`-0.04` to `+0.05` on day 1, similar across days):
Mark22 sells but the bid-ask doesn't visibly move. The basket is
absorbed by static market makers without price impact.

Untouched-strike spillover (a previously untested question) is real:

| Day | Symbol | Horizon | mean Δmid post-basket |
| --- | --- | ---: | ---: |
| 3 | VEV_5000 | 1k | +2.00 |
| 3 | VEV_5000 | 10k | +2.86 |
| 3 | VEV_5000 | 30k | +4.50 |
| 3 | VEV_5100 | 30k | +3.69 |
| 3 | VEV_5200 | 30k | +2.25 |
| 2 | VEV_5000 | 5k | +2.52 |
| 2 | VEV_5100 | 5k | +1.96 |
| 1 | VEV_5000 | 1k | +1.67 |

Day 3 (the volatile day; the official 100k slice is day-3-like) shows
substantially larger spillover than days 1-2. Near-OTM strikes
(5000-5200) drift UP after Mark22 baskets. Mid_change scales roughly
1/strike_distance: 5000 > 5100 > 5200 > 5300, with 5400+ flat.

## Paired control: matched-frequency non-Mark22 burst

`matched_frequency_control` finds, for each Mark22 basket, a
non-Mark22 voucher trade burst on the same day with similar total
quantity. The control arm then reuses the same forward-mid-change
metric.

Key results from `paired_arm_diff.csv`:

| Day | Symbol | Horizon | Treatment Δmid | Control Δmid | Diff |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | VEV_5000 | 1k | +1.67 | +0.06 | +1.61 |
| 1 | VEV_5000 | 5k | +1.35 | -0.49 | +1.84 |
| 2 | VEV_5000 | 5k | +2.52 | -0.61 | +3.13 |
| 3 | VEV_5000 | 5k | +2.69 | -0.23 | +2.92 |
| 3 | VEV_5000 | 10k | +2.86 | -1.00 | +3.86 |
| 3 | VEV_5000 | 30k | +4.50 | -3.73 | +8.23 |
| 3 | VEV_5100 | 30k | +3.69 | -3.42 | +7.11 |

This is the cleanest evidence so far that **Mark22 identity adds
information beyond a matched-frequency non-Mark VEV burst**. A random
voucher trade at similar size does not predict +1-8 ticks of upward
drift on near-OTM strikes; Mark22 baskets do.

Effect size: +1-3 ticks at 1k-5k for days 1-2, +3-8 ticks at 10k-30k
for day 3.

## Mark67 -> next-seller broader pattern

`mark67_next_seller_summary.csv` extends the prior Mark67->Mark55
finding to all VELVET sellers. Day 1 example:

| Horizon | Mark55 rate | Mark14 rate | Mark01 rate | Mark22 rate | Mark49 rate |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1k | 13.8% | 8.6% | 5.2% | 3.4% | 3.4% |
| 5k | 63.8% | 27.6% | 50.0% | 17.2% | 10.3% |
| 10k | 91.4% | 44.8% | 65.5% | 37.9% | 20.7% |
| 30k | 100.0% | 79.3% | 93.1% | 70.7% | 58.6% |

Mark55 dominates as the next VELVET seller across days/horizons
(93%+ rate at 30k). The previously-found Mark67 -> Mark55 pattern is
the strongest VELVET sequencing signal; broadening to other sellers
does not add a separable trade.

## Q&A against task questions

### Q1. Mark behaviors we missed entirely

- VEV_6000 and VEV_6500 mids are STATIC (zero variance). The Mark22
  basket has zero price impact on these strikes. They are pure
  inventory transfer between Mark22 (seller) and Mark01 (buyer) at
  fixed price. Any "deep OTM voucher" alpha attempt should account
  for this — passive maker fills here are competing directly with
  Mark01 at a fixed price.
- Near-OTM (5000-5200) spillover is positive after Mark22 baskets
  (especially day 3). This was not in prior research.
- The Mark22 inter-basket spacing is bi-modal: many short gaps
  (3-5k) and a long-tail of 20k+. This is consistent with a program
  that fires "in clusters" rather than a steady clock.

### Q2. Mark sequences predicting future trades / price / surface

- Yes, weakly. Mark67 VELVET buy -> Mark55 VELVET sell within 5k:
  ~63% rate (vs base ~50%). Officially calibrated lift was 2.37 in
  the 100k slice (113 rows, 27.8% qty coverage).
- Mark22 basket -> next basket within 30k: 95-97%. But within 1k:
  only 8-10% — we cannot front-run within a single basket.
- Mark22 basket -> near-OTM strike upward drift: +1-8 ticks
  depending on day/horizon (treatment-vs-control).
- Mark55 / Mark14 / Mark01 baseline rates already exceed 50% at 5-10k
  horizons in VELVET; raw market state already captures most of this.

### Q3. Is Mark22 informational, structural, or regime?

All three, in different respects:

- **Structural**: Mark22 hits a fixed basket of strikes with very
  consistent composition. The pair Mark22<->Mark01 is rigid. This is
  market-making vs. systematic short-vol client structure.
- **Regime**: When Mark22 fires, it usually fires multiple times
  within 30k. Activity is regime-clustered.
- **Informational**: The treatment-vs-control diff (paired_arm_diff)
  shows Mark22 baskets predict +1-8 tick near-OTM drift that a
  matched-frequency non-Mark VEV burst does not predict. This is
  weak but real signal that survives the matched control.

### Q4. Exploit through passive execution / quote skew / recycling?

The realistic exploits are:

- **Recycle existing OTM longs** when Mark22 is in selling mode. The
  prior `MARK_CONDITIONED` audit and our paired_arm_diff both point
  to short-horizon improvement on near-OTM sells when Mark22 is
  active. Effect size: ~+5-10 PnL per fire on size-5 lots.
- **Mark55 single-lot recycler**: passive VELVET inside-quote bid,
  exit at +1 tick within 10k. Already prepared:
  `submission_r4_probe_mark55_singlelot_recycle_pt1_age10k.py`.
  Counterfactual estimate +50-150 PnL vs validated.
- **Don't take terminal inventory** in any of these. The losing
  feature of the q5 upload was the held -150 VELVET position.

### Q5. Theoretical edge upper bound per Mark

Local-replay 3-day attribution (full 1.2M ticks):

| Lever | Local 3-day Δ | Implied 1m Δ |
| --- | ---: | ---: |
| Mark22-gated VEV5000/5100 recycle (treatment) | +242 | ~+67 |
| Time-cadence VEV5000/5100 recycle (control) | +216 | ~+60 |
| Mark55 single-lot recycler (counterfactual estimate) | n/a | +50-150 |
| Stack-officialmax core+VELVET regime | n/a | +3,239 (100k slice proxy) |
| HYDROGEL high-regime hardlong40 | n/a | +5,471 (100k slice proxy) |

Mark-specific edges are small. Mark22 ID over time-cadence is +0.4-1
tick per unit, which integrates to +5-30 PnL per 100k slice — below
the 100k upload noise floor (typical ~100-200 PnL stdev).

### Q6. Next upload candidate and matched control

Based on the analysis:

- **Best ROI for next upload slot**: NOT the Mark22 pair. The local
  result already shows treatment ~ control. The official 100k slice
  cannot resolve a +5-30 PnL difference.
- **Recommended upload**:
  `submission_r4_exp_flat995_vev5500_sell7_stack_officialmax_probe.py`
  (stacked alpha probe, +3,239 vs base in 100k proxy). This delivers
  the largest non-Mark alpha currently available.
- **Recommended Mark calibration upload**:
  `submission_r4_probe_mark55_singlelot_recycle_pt1_age10k.py`
  (already prepared). Tests counterparty execution edge with strict
  refill blocking. Expected +50-150 vs validated.
- **Mark22 paired upload**: only worth running if the user wants
  formal proof Mark22 ID adds zero. The local result is already
  evidence-of-zero with ~+26 treatment-vs-control on 1.2M ticks
  (0.0017% gross). Spending an upload slot to confirm has marginal
  value.

## Paired Mark22 experiment — design and result

### Treatment (Mark22-gated recycle)

`outputs/submissions/r4/submission_r4_probe_m22sell_recycle_treatment.py`

- Wraps validated baseline (`flat995_vev5500_sell7_validated`).
- Each tick reads `state.market_trades` for any VEV_*/VELVET trade
  where `seller == "Mark 22"`. Tracks the most-recent such timestamp.
- Gate active = last Mark22 sell within 5,000 ticks.
- Cooldown = 5,000 ticks between wrapper fires.
- Action: when gate active, position >= 100, and best_bid >=
  threshold (268 for VEV_5000, 177 for VEV_5100), append a single
  passive sell of size 5 at best_bid.
- Validator: 0 errors, 89,877 bytes (91% of soft cap).

### Control (time-cadence)

`outputs/submissions/r4/submission_r4_probe_m22sell_recycle_control.py`

- Same wrapper; only the gate changes.
- Gate active = >= 10,000 ticks since last fire and ts >= 30,000.
  (10k cadence ≈ Mark22 inter-basket median; 30k delay ≈ first-Mark22
  event timestamp in the observed 100k slice.)
- Same cooldown / position / threshold action.
- Validator: 0 errors, 88,561 bytes (90% of soft cap).

### Local 3-day replay

| Variant | total_pnl | Δ vs validated |
| --- | ---: | ---: |
| validated | 886,964.00 | 0 |
| treatment | 887,206.00 | +242 |
| control | 887,180.00 | +216 |

Per-product breakdown vs validated:

| Variant | VEV_5000 Δ | VEV_5000 Δqty | VEV_5100 Δ | VEV_5100 Δqty |
| --- | ---: | ---: | ---: | ---: |
| treatment | +275 | +30 | -33 | +40 |
| control | +263 | +30 | -47 | +30 |

Per-unit edge:

- VEV_5000: treatment +9.2 / unit, control +8.8 / unit
  (Δ_M22 = +0.4 per unit, ~+5 per 100k slice).
- VEV_5100: treatment -0.8 / unit, control -1.6 / unit
  (Δ_M22 = +0.8 per unit, ~+10 per 100k slice).

So Mark22 identity adds ~+0.5 ticks per recycle unit over time-cadence.
At realistic firing density (10 events per 100k × 5 units × 0.5
ticks) = +25 PnL per 100k slice. Below the 100k upload noise floor.

### Verdict

**Mark22 identity adds detectable but very small incremental alpha
over a matched-frequency time-cadence.** The recycle action itself is
the +200 PnL contributor; the Mark22 gate is the +20-30 incremental.
This is consistent with the prior MARK_CONDITIONED report's
strike-level analysis (Mark22 sells improve VEV_5000 sell @ 10k by
+11.66 ticks observationally, but only the first few ticks
materialize when execution friction is included).

## Pushback against overreach

- The paired_arm_diff is OBSERVATIONAL and does not include spread,
  fill probability, or inventory cost.
- The local 3-day replay has the same fill model assumptions as
  prior R4 work; official simulator may differ.
- The Mark22 effect is regime-amplified on day 3. If the live R4
  competition runs in a less-volatile regime, the effect shrinks.
- VEV_6000/6500 having zero mid variance is a strong indicator that
  the "OTM voucher market" is structurally pinned. Any alpha
  hypothesis that depends on these strikes moving is wrong.

## Recommended action

1. **Upload next**: `submission_r4_exp_flat995_vev5500_sell7_stack_officialmax_probe.py`
   for the +3,239 PnL gain (option/VELVET regime alpha; not a Mark
   alpha). Rationale: largest immediately-available delta vs base.
2. **Upload after that**: `submission_r4_probe_mark55_singlelot_recycle_pt1_age10k.py`
   to test execution edge (counterparty fill discipline). Rationale:
   moderate expected delta (+50-150), tests a distinct mechanism.
3. **Defer**: paired Mark22 treatment+control. The local-replay
   evidence already says the Mark22 gate adds <30 PnL per 100k slice
   on top of time-cadence. Spending two upload slots to formally
   confirm a near-zero effect is low ROI given the mechanism is
   already understood.
4. **If a future upload slot becomes available**: revisit the paired
   experiment with **larger fire size and 1m simulation**, not 100k.

## Kill criteria for the paired upload (if used)

- treatment - control < 50 official PnL: Mark22 ID adds no alpha;
  retire the Mark22 gate.
- treatment - control between 50 and 150: Mark22 ID adds noisy alpha;
  do not deploy as standalone.
- treatment - control >= 150 with same sign: Mark22 ID is real;
  promote a refined gate (e.g., basket-specific qty thresholds) for
  a bigger probe.
- Either arm loses >= -300 vs validated: abort, the recycle action
  has a fill-model issue.
