# VELVET Cross-Round Trend Readout

Date: 2026-04-28

## Question

Compare historical Round 3 data, the final hidden 1M Round 3 outcome, and
historical Round 4 data. What does this imply for the best Round 4 VELVET
strategy?

## Price Path Facts

R4 public days 1 and 2 are the same VELVET paths as R3 public days 1 and 2.
R4 adds a new public day 3, which is a bearish stress day.

| sample | day | open | close | change | min | max | range | first 100k change |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| R3 public | 0 | 5250.0 | 5244.0 | -6.0 | 5216.5 | 5284.5 | 68.0 | -11.5 |
| R3 public | 1 | 5245.0 | 5265.5 | 20.5 | 5198.0 | 5283.0 | 85.0 | 2.5 |
| R3 public | 2 | 5267.5 | 5295.5 | 28.0 | 5207.0 | 5300.0 | 93.0 | -3.5 |
| R4 public | 1 | 5245.0 | 5265.5 | 20.5 | 5198.0 | 5283.0 | 85.0 | 2.5 |
| R4 public | 2 | 5267.5 | 5295.5 | 28.0 | 5207.0 | 5300.0 | 93.0 | -3.5 |
| R4 public | 3 | 5295.5 | 5232.0 | -63.5 | 5191.5 | 5300.0 | 108.5 | -42.0 |

Aggregate VELVET trend:

| sample | mean open-close change | days up | mean first 100k change | mean range |
| --- | ---: | ---: | ---: | ---: |
| R3 public | 14.2 | 2 / 3 | -4.2 | 82.0 |
| R4 public | -5.0 | 2 / 3 | -14.3 | 95.5 |

## Option Geometry

The voucher stack behaves like a levered and strike-filtered VELVET book, not
like independent assets. Intraday return beta versus VELVET is stable across
R3 and R4:

| strike | typical tick beta to VELVET |
| --- | ---: |
| VEV_4000 | 0.73 to 0.76 |
| VEV_4500 | 0.66 to 0.68 |
| VEV_5000 | 0.65 to 0.67 |
| VEV_5100 | 0.56 to 0.60 |
| VEV_5200 | 0.43 to 0.45 |
| VEV_5300 | 0.24 to 0.27 |
| VEV_5400 | 0.09 to 0.14 |
| VEV_5500 | 0.03 to 0.06 |

This supports the current schedule structure: deep/core strikes carry the real
inventory exposure, while VEV_5500 is a narrow terminal/spread-capture sleeve.
It does not support a large pivot into standalone smile/gamma trading, because
the tested option-native single-leg markouts were negative after spreads and
hedge cost.

## Round 3 Hidden 1M Evidence

The R3 final hidden 1M result matters more than public path beauty. The static
VELVET/options sleeve made 124,200 on the hidden 1M:

| product | hidden 1M PnL |
| --- | ---: |
| VELVETFRUIT_EXTRACT | 22,704 |
| VEV_4000 | 29,725 |
| VEV_4500 | 33,971 |
| VEV_5000 | 26,486 |
| VEV_5100 | 7,633 |
| VEV_5200 | 5,380 |
| VEV_5300 | -175 |
| VEV_5400 | 276 |
| VEV_5500 | -1,800 |
| VELVET complex total | 124,200 |

Interpretation: broad static/product-level structure generalized. The edge was
not pure R3 public-data overfit. But the hidden 1M also warns against exact
path/timestamp logic: static thresholds with terminal flattening were safer
than clever path oracles.

## Round 4 Official 100k Evidence

Current official simulator evidence:

| candidate | total official PnL | VELVET complex | HYD | VELVET end pos | read |
| --- | ---: | ---: | ---: | ---: | --- |
| expstack8060 | 77,974 | 70,317 | 7,657 | 161 | Best total and best VELVET complex |
| probe_stack | 71,997 | 70,317 | 1,680 | 161 | Best isolated VELVET complex |
| sell7 validated | 68,656 | 66,976 | 1,680 | -200 | Stable baseline |
| plus80 | 70,994 | 69,314 | 1,680 | 80 | Lower inventory risk, less upside |
| delayed_full | 70,255 | 68,575 | 1,680 | 49 | Most conservative gate family |

The negative-control result is the key caveat: it captured about 85% of the
one-shot official VELVET gain. So the extra VELVET gate is mostly removing a
bad early short / terminal exposure, not a proven repeatable recycler.

## Critical Read

The best family is still static schedule plus a restrained VELVET regime
inventory sleeve. R3 hidden 1M says static threshold structure can generalize.
R4 public says the sample includes one bearish stress day, so a strategy that
stays blindly short VELVET after a large early selloff is dangerous. R4
official says covering/reversing that short can add real PnL on the 100k path,
but much of the measured gain is terminal exposure.

This argues against two extremes:

- Do not use pure sell7 as the maximum-alpha choice unless optimizing for
  conservatism. It leaves the official early-selloff/terminal-exposure issue
  untouched.
- Do not replace the stack with rolling/event-heavy logic. Public windows show
  those variants overfire, and option-native tests did not clear promotion.

## Recommendation

For best expected Round 4 VELVET-only alpha, use `probe_stack`.

For best full current portfolio, use:

`outputs/submissions/r4/submission_r4_exp_stack_hydhardlong80_60k.py`

This is the best current total official result because it combines the best
VELVET complex (`probe_stack`, 70,317) with the stronger HYD sleeve.

If the final choice must be more risk-averse on unseen 1M, use the same static
sell7 backbone and downgrade the VELVET add-on to a capped/late gate
(`plus80` or `delayed_full`). That sacrifices about 1,000 to 1,700 official
100k PnL versus `probe_stack`, but reduces dependence on ending long 161
VELVET after an early drawdown.

Final stance: `probe_stack` is the best expected VELVET strategy, not because
it fully solved VELVET, but because it is the only tested add-on that improves
the official 100k materially while preserving the R3-proven static threshold
backbone. Treat it as medium overfit risk, not low risk.
