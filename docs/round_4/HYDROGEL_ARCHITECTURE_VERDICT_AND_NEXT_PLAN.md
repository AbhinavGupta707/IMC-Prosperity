# HYDROGEL Architecture Verdict And Next Plan

Date: 2026-04-27

## Verdict

We are not looking at a failed architecture, but we are close to the point where
more upload variants would become blind optimization unless we switch to a
regime-model workflow.

HYDROGEL's tested edge is not pure mean reversion, not terminal mark, and not a
confirmed counterparty-only exploit. The strongest evidence says it is a
**path-regime inventory-control asset**:

- base mean-reversion earns/loses through shorting high prints;
- in the official/day-3 high path, that short is early and bad;
- suppressing/reversing the short until the 60k release lifts realized cash PnL;
- final exposure is identical across high-regime variants, so the ranking is
  not a terminal-mark artifact.

The architecture should therefore be:

1. normal-state mean-reversion sleeve;
2. high-regime detector;
3. immediate inventory override after high-regime trigger;
4. abort/release logic if the high path does not persist;
5. terminal exposure guard.

That is a structural pivot from static R3 mean-reversion. It is not just
parameter tuning.

## What would be blind now

The following would be weak research:

- keep uploading `hardlongX_60k` for different `X`;
- tune exact thresholds around the official 100k prefix;
- choose `hardlong80` only because it has the highest current official score;
- call the 100k simulator "validation" when the HYD path matches public day 3.

Those would optimize the calibration set, not the unseen 1M objective.

## What the evidence says

Official HYD high-regime results:

- `hardlong80_60k`: `7,657` HYD, best 100k, worst false-trigger stress.
- `hardlong40_60k`: `7,151` HYD, strong but still path-fit risk.
- `hardflat60k`: `6,434` HYD, cleaner core edge.
- `slopegate15_cap40_flat60`: `5,615` HYD, safer but delayed too much.
- `slopegate18_cap80_flat60`: `5,112` HYD, most defensive of tested gates.
- `old_flat995`: `1,680` HYD, bad drawdown and almost no touch-liquidated edge.

Rolling false-trigger stress:

- hardlong family has the worst adverse windows;
- slope/cap gates reduce false-trigger loss;
- the 40k slopegate loses too much official-path alpha because the valuable
  inventory decision starts at the 20k-30k trigger, not at 40k.

So the right next structural form is not "slower confirmation". It is:

**act early, abort later.**

## Why not pivot completely

A full pivot would require evidence that another mechanism dominates:

- terminal-mark artifact: rejected for marginal ranking, because all high-regime
  variants finish `-200` and cash attribution explains the improvement;
- pure parameterized mean-reversion: weak, because width/mean tweaks do not
  explain the official jump;
- counterparty-only/Mark-driven alpha: not yet strong enough in HYD to replace
  price-regime inventory control;
- buy-and-hold/path trend: too risky; rolling false-trigger stress is poor.

Therefore the broad direction is right, but the current fixed hardlong upload is
not a final-1M-quality strategy by itself.

## Next systematic step

Build and upload only mechanism-discriminating candidates:

1. `abortgate15_flat60`
   - trigger high regime at `mid >= 10020` in `20k-30k`;
   - immediately force flat;
   - at 40k require `20k->40k` slope >= `15`;
   - if failed, abort and flatten/release to base;
   - if passed, continue to 60k release.

2. `abortgate15_long40_60`
   - same as above, but carry +40 after trigger.
   - This tests whether the long overlay is worth the extra risk.

3. Optional `abortgate18_flat60`
   - stricter confirmation if we want a lower false-positive final candidate.

Local exact proxy:

| candidate | official proxy HYD | hist day 3 1M HYD | hist all 1M HYD |
|---|---:|---:|---:|
| abortgate15_flat60 | 6,613 | 55,563 | 166,936 |
| abortgate15_long40_60 | 7,025 | 55,975 | 167,348 |

This is the best next alpha extraction path because it preserves the early
official high-path edge while adding a robustness escape hatch.

## Stop conditions

Reject the high-regime architecture, or demote it to a small defensive overlay,
if either happens:

- abort-gated candidates fail to beat `hardflat60k`/`hardlong40_60k` after
  accounting for drawdown and official fill calibration;
- official fills show the abort gate creates churn/slippage larger than the
  false-trigger insurance is worth.

Keep and integrate it if:

- abortgate flat keeps most of hardflat's HYD PnL with better stress;
- abortgate long40 adds several hundred HYD PnL without materially worse
  drawdown/stress;
- the integrated sell7/base version is additive, as `combo_sell7_hardlong40_60k`
  already was.
