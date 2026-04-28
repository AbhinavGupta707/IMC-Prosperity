# Round 4 Mark Behavior Classification Groundwork

Date: 2026-04-27

## Why This Exists

The IMC hint says to classify counterparties, not just compute markouts. The
right questions are:

- Is the Mark maker-like or taker-like?
- Does it appear rhythmically or opportunistically?
- Does it use repeated clip sizes?
- Does it trade one product or program baskets?
- Does it lead schedule signals or just appear inside them?
- Should we respond through order placement, exposure management, or price
  interpretation?

This is groundwork. It is not yet a strategy.

## Artifacts

Script:

`/Users/abhinavgupta/Desktop/IMC/src/scripts/round_4/audit_mark_behavior_classification.py`

Outputs:

`/Users/abhinavgupta/Desktop/IMC/outputs/round_4/mark_behavior/`

Key files:

- `historical_mark_totals.csv`
- `historical_behavior_labels.csv`
- `historical_interval_summary.csv`
- `historical_schedule_lead_summary.csv`
- `historical_basket_summary.csv`
- `official_sellonly_*` equivalents from `r4 Sim Results/sellonly/497595.log`

Run:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.audit_mark_behavior_classification \
  --data-dir /tmp/imc-r4-counterparty-audit/data/raw/round_4 \
  --official-log /Users/abhinavgupta/Desktop/IMC/r4\ Sim\ Results/sellonly/497595.log \
  --out-dir /Users/abhinavgupta/Desktop/IMC/outputs/round_4/mark_behavior
```

## Method

For each trade, the script creates two actor rows: buyer-side Mark and
seller-side Mark.

It attaches contemporaneous top-of-book state and infers role:

- buyer at/above ask = taker-like buyer
- seller at/below bid = taker-like seller
- opposite side = maker-like/passive

It computes:

- volume fingerprints and repeated clip sizes
- inter-arrival intervals
- taker/maker rate
- signed past and future mid movement
- spread-aware future edge
- relation to existing schedule signals
- same-timestamp basket/program clusters

## Main Classification

Historical totals:

| Mark | Role | Products | Notes |
| --- | --- | ---: | --- |
| Mark 14 | almost pure maker/passive | 7 | HYDROGEL and VELVET/VEV passive liquidity provider |
| Mark 01 | pure maker/passive | 7 | especially OTM voucher basket buyer vs Mark22 seller |
| Mark 55 | pure taker | 1 | VELVET-only, both sides, consistently adverse after spread |
| Mark 22 | mostly taker/seller | 12 | broad option-complex seller, especially OTM baskets |
| Mark 38 | pure taker | 7 | HYDROGEL and VEV4000 taker, very adverse after spread |
| Mark 67 | one-way taker buyer | 1 | VELVET-only buyer, small sample official |
| Mark 49 | mostly maker/passive | 1 | VELVET-only, mostly seller/passive |

This is a cleaner structure than raw Mark markouts alone.

## What Replicated In Official 100k

Using `sellonly/497595.log`, the role structure largely replicated:

- `Mark 14`: maker-like/passive, 100% maker rate official.
- `Mark 01`: maker-like/passive, 100% maker rate official.
- `Mark 22`: mostly taker/seller, 92% taker rate official.
- `Mark 55`: VELVET taker, 100% taker rate official.
- `Mark 38`: HYDROGEL/VEV4000 taker, 100% taker rate official.
- `Mark 67`: VELVET one-way taker buyer, but only 5 official rows.

The directional edge did not replicate as cleanly as role. That is important:
roles are more robust than markout signs.

## Basket / Program Behavior

The strongest program structure is Mark22 vs Mark01 in OTM vouchers.

Historical:

| Actor | Side | Counterparty | Product set | Clusters | Component rows | Total qty |
| --- | --- | --- | --- | ---: | ---: | ---: |
| Mark22 | sell | Mark01 | VEV_5400/5500/6000/6500 | 140 | 560 | 1,980 |
| Mark22 | sell | Mark01 | VEV_5300/5400/5500/6000/6500 | 101 | 505 | 1,705 |

Official 100k:

| Actor | Side | Counterparty | Product set | Clusters | Component rows | Total qty |
| --- | --- | --- | --- | ---: | ---: | ---: |
| Mark22 | sell | Mark01 | VEV_5400/5500/6000/6500 | 8 | 32 | 124 |
| Mark22 | sell | Mark01 | VEV_5300/5400/5500/6000/6500 | 3 | 15 | 45 |

This is the clearest "larger participant / program flow" pattern so far.

## Rhythm Finding

Strong exact periodicity is not the dominant signal.

Most high-volume cells have low top-interval concentration. Example historical:

- `Mark55` VELVET sell: median interval 3.3k, top interval only 3.0% of intervals.
- `Mark55` VELVET buy: median interval 3.4k, top interval 2.9%.
- `Mark14`/`Mark38` HYDROGEL: median interval ~4.1k-4.2k, top interval ~3.7%.

So the hint's "predictable intervals" does not currently imply an exact clock
we can exploit. The more robust pattern is role and basket identity.

## Schedule Relation

Historical schedule-leading is mostly unsurprising:

- passive voucher buyers like `Mark01` often appear exactly when our schedule
  would also buy those vouchers;
- VELVET buy-side Marks often occur near VELVET buy schedule states;
- official schedule-lead samples are small.

This does not yet justify a new rule. It is useful context for the Mark-conditioned
schedule audit, where Mark22 VELVET sell-flow was a better conditioner than most
single-Mark direction rules.

## Strategy Implications

1. `Mark55` is likely noisy VELVET liquidity-taking flow.
   - It is 100% taker-like in historical and official.
   - Both buy and sell sides are adverse after paying spread.
   - Candidate use: passive VELVET liquidity provision / quote-skew probe, not
     follow/fade crossing.

2. `Mark22` is a broad OTM voucher basket seller.
   - This is the strongest program-flow pattern.
   - Candidate use: price interpretation and passive-bid/recycling probes in
     OTM vouchers.
   - Caution: current VEV_5500 buy disabling improved official PnL, so do not
     blindly buy every Mark22 OTM sale.

3. `Mark14`/`Mark01` are passive liquidity providers.
   - Their identity is useful mainly to identify the opposing taker/program.
   - We cannot choose to trade specifically with them, so this is more
     explanatory than directly actionable.

4. `Mark38` is a strong taker/adverse role in HYDROGEL/VEV4000.
   - This should feed the HYDROGEL isolation session.
   - It may matter for avoiding bad passive liquidity provision rather than
     for standalone directional crossing.

5. `Mark67` is a one-way VELVET buyer, but official sample is too small.
   - Treat it as a possible state variable, not a main candidate.

## Pushback Against Overreach

The IMC hint is relevant, but it does not say "follow the informed Mark." The
evidence says:

- role classification is robust;
- exact rhythm is weak;
- directional markout is less robust than role;
- basket behavior is real;
- strategy response should be execution-aware, not a fresh aggressive cross.

The next step should be controlled probes that exploit role:

1. Passive/noisy-taker probe in VELVET against Mark55-like flow.
2. OTM basket-flow probe for Mark22, with VEV_5500 disabled as a control.
3. HYDROGEL Mark38/Mark14 role handoff to the HYD session.
4. Negative controls with matched frequency to separate Mark identity from
   generic regime timing.

Follow-up bot-policy/hazard research is saved in
`/Users/abhinavgupta/Desktop/IMC/docs/round_4/MARK_POLICY_HAZARD_RESEARCH.md`.
The strongest official-calibrated result is narrow: recent Mark67 VELVET buying
predicts elevated Mark55 VELVET sell flow over the next 1k ticks. This supports
a small VELVET passive-execution probe, not a broad Mark overlay.

## Passive-Maker Upper Bound

I also computed a rough upper bound for being the passive maker against taker
Marks. Output:

`/Users/abhinavgupta/Desktop/IMC/outputs/round_4/mark_behavior/historical_passive_maker_upper_bound.csv`

`/Users/abhinavgupta/Desktop/IMC/outputs/round_4/mark_behavior/official_sellonly_passive_maker_upper_bound.csv`

The estimate assumes we earn the opposite side of the taker's spread-aware
future edge, with a rough 30% passive allocation. It is not a strategy result,
but it ranks where the monetizable flow probably lives.

Top historical 5k passive-maker opportunities:

| Taker Mark | Product | Taker side | Qty | 30% passive maker edge |
| --- | --- | --- | ---: | ---: |
| Mark38 | HYDROGEL | buy | 2,065 | +10,404 |
| Mark38 | HYDROGEL | sell | 2,031 | +9,631 |
| Mark55 | VELVET | sell | 3,297 | +4,564 |
| Mark55 | VELVET | buy | 3,254 | +4,267 |
| Mark38 | VEV_4000 | sell | 461 | +2,809 |
| Mark38 | VEV_4000 | buy | 415 | +2,574 |
| Mark22 | VEV_5400/5500/6000/6500 sells | ~1k each | +330 to +387 each |

Top official 100k 5k passive-maker opportunities:

| Taker Mark | Product | Taker side | Qty | 30% passive maker edge |
| --- | --- | --- | ---: | ---: |
| Mark38 | HYDROGEL | sell | 77 | +411 |
| Mark38 | HYDROGEL | buy | 35 | +199 |
| Mark55 | VELVET | sell | 126 | +174 |
| Mark55 | VELVET | buy | 82 | +110 |
| Mark38 | VEV_4000 | buy | 11 | +62 |
| Mark38 | VEV_4000 | sell | 7 | +51 |
| Mark22 | OTM voucher sells | 42-48 each | +12 to +14 each |

Interpretation:

- Mark-based alpha is most likely an execution/liquidity-provision problem.
- Mark22 OTM baskets are the cleanest program pattern but not the largest direct
  PnL source in the 100k slice.
- Mark38/HYDROGEL and Mark55/VELVET are larger, but require us to actually get
  passive fills without taking unacceptable inventory risk.
