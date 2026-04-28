# HYDROGEL Abortgate Long80 Upload Decision

Date: 2026-04-27

## Question

Should we spend more upload budget on HYDROGEL after selecting
`abortgate15_long40_60`, and is there a plausible non-overfit marginal PnL
increase?

## Short Answer

Yes, but only one HYD upload is still rational:

`outputs/submissions/r4/submission_r4_final_sell7_hyd_abortgate18_long80_60.py`

This is a probe, not the current final default. It tests whether the same
high-regime abortgate structure can carry `+80` instead of `+40`.

## Why This Is Not Random Tuning

Rejected ideas:

- width / mean changes: already worse on official calibration;
- flat95k / terminal flatten probes: diagnostic only, not alpha;
- soft no-short: leaks shorts and underperforms;
- cap40 / cap80: useful mechanism checks but dominated;
- slopegates: too delayed; lose official-path alpha;
- post-release recycler: fragile/negative;
- Mark/counterparty HYD: not yet strong enough to replace the regime model.

The only remaining structural question is size:

```text
If early high-regime passes the abort gate, should target inventory be +40 or +80?
```

This is a controlled risk question, not a new path oracle.

## Local Replay Comparison

HYD-only local replay after generating the new files:

| candidate | official-proxy HYD | hist day3 1M HYD | hist all 1M HYD | official-proxy min HYD | official-proxy max DD |
|---|---:|---:|---:|---:|---:|
| abortgate15 long40 | 7,370 | 56,320 | 167,693 | -1,030 | -4,100 |
| abortgate18 long40 | 7,370 | 56,320 | 167,693 | -1,030 | -4,100 |
| abortgate18 long80 | 7,867 | 56,817 | 168,190 | -1,161 | -4,100 |

Local replay says `abortgate18_long80_60` adds about `+497` HYD where the high
regime passes. It does not change the tested max drawdown, but it does make the
opening long exposure larger.

## Rolling Stress

Approximate rolling high-trigger stress from the slope-grid diagnostics:

| policy | rolling overlay mean | worst window | p10 | positive rate | official-like overlay |
|---|---:|---:|---:|---:|---:|
| abortgate18 long40 | -2,657 | -16,800 | -8,400 | 24.8% | +7,400 |
| abortgate18 long80 | -2,895 | -16,800 | -8,648 | 23.9% | +7,800 |

The added size costs roughly `-238` in rolling mean and about `-248` at p10,
while buying about `+400-500` on the official-like high path.

## Interpretation

This is the first extra HYD probe that is still defensible:

- upside is meaningful enough: about `+500` HYD, not just noise;
- it keeps the same abort framework as the robust long40 candidate;
- it is not raw `hardlong80`, which has much worse false-trigger stress;
- but it is still more path-risky than long40 because it doubles early long size.

## Upload Plan

If upload budget is available:

1. Upload `submission_r4_final_sell7_hyd_abortgate18_long80_60.py`.
2. Optional control: upload `submission_r4_final_sell7_hyd_abortgate18_long40_60.py`.

Decision rule:

- If official `abortgate18_long80_60` improves HYD by roughly `+400` to `+600`
  versus `abortgate15_long40_60`, with similar HYD drawdown and no weird fill
  slippage, it becomes a serious final candidate.
- If the gain is much smaller, or drawdown/fill path worsens, keep
  `abortgate15_long40_60` as final.
- Do not promote `long80` just because it is higher on the 100k score. Promote
  it only if the attribution confirms it is the same high-regime cash edge,
  not a new terminal-mark or fill artifact.

## Current Final State

Before this upload, final HYD remains:

`abortgate15_long40_60`

After a clean positive long80 upload, final HYD may become:

`abortgate18_long80_60`

