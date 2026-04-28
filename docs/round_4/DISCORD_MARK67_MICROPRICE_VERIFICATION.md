# Discord Mark67 / Microprice Claims Verification

Date: 2026-04-27

## Claims Checked

Discord snippets suggested:

- Mark67 should not be used standalone; it is a proxy.
- The real signal is VELVET microprice imbalance `> 0.6` maintained for 3 ticks.
- That condition allegedly gives about `+1.8` ticks at `h=100`.
- Some participants claim large daily PnL from Mark67/Mark patterns.

## Artifact

Script:

`/Users/abhinavgupta/Desktop/IMC/src/scripts/round_4/audit_velvet_microprice_mark67.py`

Outputs:

`/Users/abhinavgupta/Desktop/IMC/outputs/round_4/velvet_microprice_mark67/`

## Literal Microprice Claim

I define VELVET microprice imbalance as:

`(bid_volume_1 - ask_volume_1) / (bid_volume_1 + ask_volume_1)`

This is equivalent to the normalized top-of-book microprice skew.

Result:

- Historical max consecutive run with imbalance `> 0.6`:
  - day 1: 2 ticks
  - day 2: 2 ticks
  - day 3: 2 ticks
- Therefore `> 0.6 maintained for 3 ticks` produces **zero events** in the
  three public historical days.
- It also produces **zero events** in the official 100k simulator book path
  checked via `expstack8060`.

So the claim as written does not match our data. It may be using a different
definition, threshold, or timestamp convention, but under the natural definition
it is false.

## Softer Threshold Check

I also checked imbalance `> 0.5` for 3 ticks.

Historical positive imbalance, all active rows:

| Horizon | N | Signed mid move | Aggressive buy edge |
| ---: | ---: | ---: | ---: |
| 100 | 84 | +0.35 | -4.39 |
| 1,000 | 84 | -0.31 | -5.14 |
| 5,000 | 84 | -0.38 | -5.19 |

Official positive imbalance `>0.5` for 3 ticks:

| Horizon | N | Signed mid move | Aggressive buy edge |
| ---: | ---: | ---: | ---: |
| 100 | 3 | +1.17 | -4.00 |
| 1,000 | 3 | +0.33 | -5.00 |
| 5,000 | 3 | -8.83 | -14.00 |

Interpretation:

- There is a small one-tick mid markout in some cases.
- It is nowhere near tradable by crossing the spread.
- The official sample is tiny and not supportive beyond one-tick mid movement.
- This does not justify a standalone upload.

## Mark67 Standalone

Historical Mark67:

- Mark67 is a public buyer only in VELVET.
- Historical rows: 165, qty 1,510.
- At Mark67 buy timestamps, average imbalance is `+0.573`.

Mark67 buy markouts:

| Horizon | Signed mid move | Aggressive follow edge |
| ---: | ---: | ---: |
| 100 | +1.97 | -1.41 |
| 1,000 | +2.24 | -1.05 |
| 5,000 | +1.92 | -1.37 |
| 10,000 | +1.48 | -1.81 |
| 30,000 | +0.63 | -2.63 |

Official 100k Mark67:

| Horizon | N | Signed mid move | Aggressive follow edge |
| ---: | ---: | ---: | ---: |
| 100 | 5 | +2.10 | -1.00 |
| 1,000 | 4 | +1.75 | -2.00 |
| 5,000 | 4 | +4.13 | +0.75 |
| 10,000 | 4 | -6.38 | -10.00 |

Interpretation:

- Mark67 really does identify short-term upward mid movement.
- But simply following him aggressively is not alpha after spread, except for a
  tiny 5k official sample of four rows.
- The Discord phrase "he is a proxy" is plausible. The claim "just following
  him is the alpha" is not supported by spread-aware evidence.

## Can Mark67 Sell To Us?

Yes, but this is not the same as public Mark67 behavior.

Across official uploads:

- Public non-SUBMISSION Mark67 rows are buy-only.
- In some Mark67-specific probes, `SUBMISSION` bought from Mark67:
  - `always_q5`: 19 qty from Mark67
  - `age10k`: 10 qty from Mark67, plus 1 qty sold to Mark67
  - `new_age10k`: 10 qty from Mark67
  - `m67_q5`: 5 qty from Mark67

So "Mark67 only buys" is true for public bot-vs-bot tape, but our order can
still match against Mark67 as seller if we post/cross into his resting liquidity.

## VEV_5200 Mark14/Mark22 Sequence

Historical rows:

- Mark14 buys VEV_5200: 33 rows across 3 days
  - day 1: 6
  - day 2: 8
  - day 3: 19
- Mark22 sells VEV_5200: 46 rows across 3 days
  - day 1: 7
  - day 2: 8
  - day 3: 31

Sequence lift:

| Trigger | Target | Horizon | Rows | Hit rate | Baseline | Lift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Mark14 buys VEV_5200 | Mark22 sells VEV_5200 | 10k | 33 | 33.3% | 13.1% | 2.55 |
| Mark14 buys VEV_5200 | Mark22 sells VEV_5200 | 30k | 33 | 60.6% | 29.4% | 2.06 |
| Mark22 sells VEV_5200 | Mark14 buys VEV_5200 | 10k | 46 | 21.7% | 9.6% | 2.27 |
| Mark22 sells VEV_5200 | Mark14 buys VEV_5200 | 30k | 46 | 39.1% | 22.5% | 1.74 |

Official 100k path:

- Only one public VEV_5200 print: `Mark14` buys from `Mark22` at timestamp
  98,900.
- The official 100k slice therefore cannot validate this sequence.

Verdict:

- Worth exploring as a discovery probe if uploads are unlimited.
- Not worth prioritizing ahead of final VELVET/HYD integration because sample
  size is small and official 100k has almost no validation surface.

## Research Verdict

Discord claims are directionally useful but exaggerated:

- Mark67 is a real proxy for short-term VELVET upward pressure.
- The literal microprice `>0.6 for 3 ticks` rule does not exist in our data.
- A softer imbalance rule does not survive executable spread costs.
- Large Mark PnL is more plausible from passive liquidity/recycling around
  predictable takers than from aggressive Mark-following.

Next useful research should target passive/execution surfaces, not standalone
Mark67 following.

