# HYDROGEL Overfit And Alpha Strategy Review

Date: 2026-04-27

## Executive Read

`hardlong40_60k` is the best official 100k HYD probe so far, but it is not a
fully robust final-1M theorem.

What is robust:

- Early cheap shorts are bad in the official/day-3 high-continuation prefix.
- Hard HYD order replacement is safer than soft filtering.
- A small long before the high-regime short adds real PnL in that prefix.
- Other sleeves did not move, so HYD attribution is clean.

What is overfit-prone:

- The exact `20k-30k` trigger and `60k` release are calibrated to one 100k
  path.
- The official 100k HYD book path is exactly the same as historical
  `prices_round_4_day_3.csv` first 100k in the local dataset.
- Rolling historical 100k windows do not support "high at 20k-30k means long
  until 60k" as a universal rule.

Current best broad strategy group:

`regime-conditioned mean-reversion / inventory recycling`

Do not pivot to pure trend, pure Mark/counterparty, or pure terminal-mark
mining. The next alpha should come from better regime classification and
release logic, not another width tweak.

## Official Batch Result

Other-product PnL is unchanged at `64,906.9`, so each total delta is HYD-only.

| run | total | HYD PnL | delta vs old | avg buy | avg sell | final pos |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| old `flat995` | 66,586.9 | 1,680 | 0 | | 10025.15 | -200 |
| soft no-short 60k | 68,418.9 | 3,512 | +1,832 | 10035.87 | 10034.52 | -200 |
| cap80 60k | 69,200.9 | 4,294 | +2,614 | 10040.00 | 10038.30 | -200 |
| cap40 60k | 70,048.9 | 5,142 | +3,462 | 10040.80 | 10042.34 | -200 |
| hardflat 60k | 71,340.9 | 6,434 | +4,754 | 10029.00 | 10047.79 | -200 |
| hardlong40 60k | 72,057.9 | 7,151 | +5,471 | 10030.25 | 10047.91 | -200 |

Interpretation:

- cap80 < cap40: more early short inventory is worse.
- hardflat > cap40: fully suppressing inner HYD behavior until release is
  valuable.
- hardlong40 > hardflat: the rising-leg long is worth about `+717` official PnL.

This is strong evidence for the high-regime mechanism. It is not strong
evidence that `+40 until exactly 60k` generalizes.

## Simulator Independence Caveat

I compared official `flat995` HYD book rows against historical R4 day 3 first
100k:

- rows: `1000` vs `1000`
- timestamp mismatches: `0`
- best bid/ask price mismatches: `0`
- best bid/ask volume mismatches: `0`
- mid mismatches: `0`

So in this local workspace, the official 100k HYD price path equals
`prices_round_4_day_3.csv` first 100k. The official simulator still calibrates
official fill behavior and product interactions, but it is not an independent
price-path validation for HYD.

This matters a lot. Repeated uploads to this 100k path can overfit the exact
day-3 prefix.

## Rolling-Window Generalization Test

Script:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.analyze_hydrogel_regime_generalization
```

Outputs:

- `outputs/round_4/hydrogel_probes/regime_generalization_windows.csv`
- `outputs/round_4/hydrogel_probes/regime_generalization_summary.csv`

Method:

- scan rolling 100k windows in R4 historical days;
- trigger if HYD mid >= `10020` in relative `20k-30k`;
- test whether long `+40` to relative `60k` works;
- test whether delaying a short from trigger to relative `60k` works;
- compare against the official/day-3 prefix.

Summary:

| sample | triggered windows | long40 to 60k mean | long40 positive rate | short-delay to 60k mean | short-delay positive rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| all historical rolling windows | 117 | -1,231.8 | 12.8% | -3,039.3 | 27.4% |
| official/day-3 prefix | 1 | +760 | 100% | +7,000 | 100% |

This is the overfit warning. The official prefix is a favorable high-trigger
case. Across historical rolling windows, fixed-60k waiting is usually bad.

A price-release rule is better but not sufficient:

| sample | price-release short-to-terminal mean | positive rate |
| --- | ---: | ---: |
| all historical rolling windows | +2,265.8 | 60.7% |
| official/day-3 prefix | +6,200 | 100% |

Price release is more structural than fixed timestamp, but it still has large
negative tails in historical windows.

## Are We In The Correct Broad Strategy Group?

Yes, with a qualification.

HYD is not best modeled as:

- pure trend: broad path/trend candidates were poor in the earlier isolation
  research;
- pure Mark/counterparty: Mark flow is economically large but role-confounded
  and not independently predictive enough;
- pure terminal artifact: local 1M `flat995` makes strong PnL with low terminal
  exposure;
- pure static mean reversion: the official/day-3 high path breaks the static
  anchor early.

The correct broad group is:

`mean-reversion with regime-conditioned inventory timing`

The strategy should have two modes:

1. Breakdown / R3-like cycle mode
   - Trade the static/rebound cycle.
   - This is where R3 got 20k+ realized HYD PnL.

2. High-continuation mode
   - Do not short early just because static fair says high.
   - Stay flat or carry a small long while the path is still rising.
   - Flip short only after a high enough price or turn confirmation.

The current `hardlong40_60k` is an upload-calibrated prototype of mode 2, not
the final architecture.

## Are We Leaving Alpha On The Table?

Yes, but not by a simple parameter.

Evidence:

- Official terminal-mark oracle from prior HYD work: about `18,017`.
- Best official tested HYD: `7,151`.
- Local historical force-flat oracles are much larger than current capture.

What remains:

1. Better high-regime release
   - Fixed `60k` is the riskiest part of the current probe.
   - A release based on `bid >= high threshold`, persistence, or turn
     confirmation is more defensible.

2. Target-size calibration
   - `+40` added `+717` official PnL over hardflat.
   - `+60/+80` may add more on the official prefix, but rolling-window evidence
     says long exposure is dangerous unless the regime classifier is stronger.

3. Recycling after the first high short
   - The current official winners reach `-200` and stop.
   - The oracle gap requires dynamic long/short recycling after the first flip,
     not only a better first entry.

4. Terminal-risk controls
   - All official 100k winners end `-200`, so they remain `-200/tick`
     terminal-mark sensitive in the 100k probe.
   - For final 1M, the `995k` flatten wrapper matters, but early `-200`
     inventory can still create path drawdown and missed recycling.

## Final-Candidate Implication

For the final 1M hidden run, I would not call `hardlong40_60k` "robust" in the
absolute sense. I would call it:

`best official-calibrated high-regime overlay so far`

Why it may still be acceptable:

- It is guarded; day 1/day 2 first-100k do not trigger in local replay.
- On day 3 full 1M, it improves HYD from `50,766` to `56,320`.
- It improves official drawdown and official PnL path materially.

Why it may fail:

- If hidden final begins with a false high trigger that mean-reverts before
  `60k`, hardlong loses relative to the static short.
- Rolling historical windows show false high triggers are common if generalized
  beyond the exact day-start prefix.

Practical risk ranking for final:

1. safest: `flat995`
2. moderate: `cap40_60k`
3. stronger but more path-fit: `hardflat_60k`
4. highest current official EV, highest overfit risk: `hardlong40_60k`

Given the competition objective, `hardlong40_60k` is a reasonable candidate if
we accept official/day-3 calibration risk. If we want robustness over maximum
official-probe score, `hardflat_60k` or `cap40_60k` is cleaner.

## Next Research

Do not tune width. Do not keep relaxing early cap. The next high-value tests
are:

1. hardlong size sweep with strong caveat
   - `+20`, `+40`, `+60`, `+80`;
   - evaluate not only official PnL but rolling false-trigger loss.

2. structural release
   - release when `bid >= 10048` and path has not broken down;
   - or release after a local turn from a high percentile;
   - compare against fixed `60k`.

3. false-trigger protection
   - if the path drops below support before release, switch back to static
     mean-reversion rather than staying long/flat.

4. dynamic recycling after first short
   - allow partial covers on meaningful pullbacks and resells on rebounds;
   - this is where the remaining oracle gap likely lives.

## Bottom Line

We are in the right broad family. The big unlock is not a total pivot. It is
turning the HYD sleeve from:

`static anchor + one terminal short`

into:

`regime classifier + inventory target + structural release + recycling`

The current hardlong40 result is a valuable clue, but the exact timestamp rule
should be treated as a calibrated probe, not a settled final theory.
