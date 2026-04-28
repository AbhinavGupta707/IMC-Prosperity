# Round 4 Phase 1 - Current Strategy Anatomy

Date: 2026-04-27

## Scope

Phase 1 answers one question before deeper sleeve research:

> What exactly is the current R3-to-R4 strategy exploiting, what has already
> been optimized, and where is the remaining alpha likely to live?

Evidence used:

- Official 100k simulator logs in `r4 Sim Results/`.
- Current R4 candidate files in `outputs/submissions/r4/`.
- Historical 1M R4 day replays from the R4 audit worktree.
- Prior R3 lessons: option attribution must be Greek-aware; official uploads
  are calibration experiments; do not overfit one public/simulator slice.

## Current Candidate Stack

The base R4 strategy is the final R3 algorithm with R4 TTE corrected to `4`.
It contains two mostly independent engines:

- `HYDROGEL_PACK`: static mean-reversion around the R3/R4 long-run anchor,
  with terminal risk handled by a wrapper.
- `VELVETFRUIT_EXTRACT + VEV_*`: fixed schedule thresholds across the
  underlying and voucher chain.

The wrapper/probe layer now contains:

| Candidate | Purpose | Local 3x1M replay | Official 100k |
|---|---:|---:|---:|
| `control_r3unchanged_tte4` | Pure R3 with TTE=4 | 889,540 | 66,586.90 |
| `safer_hydflat995` | Control plus HYDROGEL flatten from 995k | 885,951 | 66,586.90 |
| `vev5500_disabled` | `flat995`, no `VEV_5500` | 885,164 | 67,621.36 |
| `vev5500_sellonly` | `flat995`, `VEV_5500` sell threshold 8 | 886,064 | 67,621.36 |
| `vev5500_sell7` | `flat995`, `VEV_5500` sell threshold 7 | 886,964 local; official projected +1,050 vs disabled | not uploaded yet |

The official `sellonly` and `disabled` runs are identical because threshold
`sell >= 8` never fired. Their +1,034.46 improvement over `flat995` comes
entirely from avoiding the baseline's bad `VEV_5500` long.

## What The Strategy Is Actually Exploiting

### HYDROGEL

Current HYDROGEL is a static mean-reversion bet, not an adaptive market-maker.

Local evidence supports the anchor:

- R4 historical HYDROGEL mean is close to the static 9988/9995 region.
- The 100k simulator HYDROGEL mean was much higher and should be treated as a
  one-window outlier, not a reason to re-anchor blindly.

Wrapper optimization so far:

- `flat995` costs about 3,589 local PnL versus unguarded control.
- It reduces terminal HYDROGEL residual from about `+128` to about `+12`.
- This is a real hidden-FV risk reduction, not a PnL-maximizing change.

Conclusion: HYDROGEL wrapper risk is handled reasonably; HYDROGEL alpha itself
is not maximized.

### VELVET + Vouchers

This is the main engine.

The R3 schedule is not a subtle learned model. It is a fixed threshold book:

- Sell VELVET and deep ITM calls when bids are high.
- Buy ATM/OTM calls when asks are low.
- Across full 1M historical days, many products round-trip to flat and collect
  repeated spread/regime PnL.
- In the official 100k probe, the same schedule reaches position limits early
  and then mostly stops.

Official `sellonly/disabled` position state after the early ramp:

| Product | End Position |
|---|---:|
| HYDROGEL | -200 |
| VELVET | -200 |
| VEV_4000 | -300 |
| VEV_4500 | -300 |
| VEV_5000 | +300 |
| VEV_5100 | +300 |
| VEV_5200 | +300 |
| VEV_5300 | +300 |
| VEV_5400 | +300 |
| VEV_5500 | 0 |

This is why the chart shows an initial ramp and then a long flat region.

Timing from the official `sellonly/disabled` run:

- 50% of final PnL by tick 25,200.
- 80% by tick 39,100.
- 99% by tick 41,900.
- Last submission fill at tick 51,600.
- Final tick is 99,900.

After tick 51,600 the strategy is not finding fewer signals. It is mostly
capacity-saturated.

Blocked buy signals after the last fill in `flat995`:

| Product | Blocked buy snapshots | End-mark value of taking them with infinite extra capacity |
|---|---:|---:|
| VEV_5000 | 101 | +3,739 |
| VEV_5100 | 169 | +4,151 |
| VEV_5200 | 286 | -4,650 |
| VEV_5300 | 482 | -20,579 |
| VEV_5400 | 342 | -6,781 |
| VEV_5500 | 484 | -7,833 |

This proves two things:

1. The plateau is real capacity exhaustion.
2. Naively increasing capacity or buying every blocked signal would overfit
   and likely lose. The missed alpha is selective recycling, not simply more
   size.

## How Far From Theoretical Max?

A deliberately overfit level-1 top-of-book dynamic-programming oracle on the
official 100k probe gives:

| Metric | PnL |
|---|---:|
| Actual `sellonly/disabled` | 67.6k |
| Independent-product L1 hindsight oracle | 138.7k |
| Gap | 71.1k |

Largest oracle gaps:

| Product | Gap |
|---|---:|
| HYDROGEL | +16.3k |
| VELVET | +13.9k |
| VEV_5100 | +10.2k |
| VEV_5200 | +10.0k |
| VEV_5300 | +7.7k |
| VEV_5000 | +7.6k |
| VEV_5500 | +1.1k |

This upper bound is not a tradable target. It uses hindsight. But it is a
strong diagnostic: the missing class is dynamic inventory state, not another
thin standalone Mark wrapper.

## Greek Read

The current options schedule creates large Greek swings, not a stable
delta-neutral book.

From historical replay:

| Day | Mean Delta | Delta Range | Mean Gamma | Mean Vega |
|---|---:|---:|---:|---:|
| 1 | +213 | -1,795 to +1,752 | +0.86 | +120k |
| 2 | -123 | -1,825 to +1,777 | +0.75 | +83k |
| 3 | +1,109 | -1,796 to +1,775 | +2.64 | +257k |

So the strategy is not simply "long gamma" or "short skew." It oscillates
between materially different regimes. Future VELVET research should optimize
the option book as a state machine: target delta/gamma/vega by regime and
strike, not just static per-product thresholds.

## Mark / Counterparty Status

Counterparty IDs are real and visible in both historical and official logs.
However, prior actionable tests found no robust standalone Mark rule after:

- one-tick delay,
- spread/entry cost,
- cross-day holdout,
- product/side/horizon filtering.

Current read:

- Mark alpha may be useful as a small modifier.
- It is not yet proven as a primary engine.
- It should be integrated inside schedule/inventory decisions, not bolted on as
  an aggressive-cross overlay.

## Have We Maximized The Current Wrapper Layer?

Mostly yes for the wrapper layer, no for the base strategy.

Already strong / useful:

- TTE correction to `4`.
- HYDROGEL terminal flatten at 995k for hidden-FV risk.
- VEV_5500 disabling/sell-only diagnostics.
- VEV_5500 `sell7` identified as a better structural probe.
- Diagnostic split between HYDROGEL-only and VELVET/options-only.

Not maximized:

- Static VELVET/voucher schedule thresholds.
- Strike-level option inventory recycling.
- Greek-aware state control.
- HYDROGEL intraday adaptation.
- Mark-aware quote/inventory skew.

## Phase 1 Conclusion

The current strategy is not close to theoretical max. It is a strong baseline
because the R3 static schedule happens to align well with R4 regimes, but it is
structurally capped:

1. It fills early.
2. It hits limits.
3. It carries inventory through the long flat region.
4. It does not recycle capacity selectively.
5. It does not control the option book by Greeks.

The next research should split into:

- HYDROGEL isolation: better alpha/risk engine and terminal policy.
- VELVET complex isolation: strike schedule, recycling, Greek state machine.
- Mark thread: use IDs as conditional modifiers only if robust across
  historical and official evidence.

## Immediate Candidate Read

Current safe baseline remains `submission_r4_safer_hydflat995.py`.

Best experimental upgrade candidate is now:

`outputs/submissions/r4/submission_r4_exp_flat995_vev5500_sell7.py`

Why:

- It removes bad `VEV_5500` buys.
- It would have captured the official early `VEV_5500` bid-7 opportunity.
- It improves local 3-day replay by about +1,013 versus `flat995`.
- It dominates disabled locally and should dominate disabled in official probe
  if bid 7 appears again.

