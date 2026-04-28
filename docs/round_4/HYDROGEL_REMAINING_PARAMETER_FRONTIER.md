# HYDROGEL Remaining Parameter Frontier

Date: 2026-04-27

## Question

After the clean `abortgate18_long80_60` official result, is there any other
parameter direction that can add HYD PnL without becoming pure overfit?

## Answer

There is no new independent HYD alpha family left in the tested evidence.

The only remaining plausible knob is the same high-regime inventory size:

```text
abortgate18 target: +80 -> +120 -> +160 -> +200
```

This is not a different signal. It is a risk frontier on the same signal.

## Size Frontier

Local HYD-only replay with the `abortgate18` structure:

| target | official-proxy HYD | hist day3 1M HYD | hist all 1M HYD | official-proxy min HYD | official-proxy max DD |
|---:|---:|---:|---:|---:|---:|
| 0 | 6,626 | 55,576 | 166,949 | -1,774 | -4,100 |
| 20 | 7,026 | 55,976 | 167,349 | -1,374 | -4,100 |
| 40 | 7,370 | 56,320 | 167,693 | -1,030 | -4,100 |
| 80 | 7,867 | 56,817 | 168,190 | -1,161 | -4,100 |
| 120 | 8,346 | 57,296 | 168,669 | -1,892 | -4,100 |
| 160 | 8,596 | 57,546 | 168,919 | -2,843 | -4,800 |
| 200 | 8,776 | 57,726 | 169,099 | -3,842 | -6,000 |

Official-like PnL keeps rising with size, but the early inventory path gets
worse rapidly after `+120`.

## Rolling False-Trigger Stress

Approximate rolling high-trigger stress with gate `40k`, slope threshold `18`,
short cap `0`:

| target | rolling mean | worst window | p10 | positive rate | official-like overlay |
|---:|---:|---:|---:|---:|---:|
| 0 | -2,419 | -16,800 | -8,200 | 24.8% | 7,000 |
| 20 | -2,538 | -16,800 | -8,400 | 24.8% | 7,200 |
| 40 | -2,657 | -16,800 | -8,400 | 24.8% | 7,400 |
| 80 | -2,895 | -16,800 | -8,648 | 23.9% | 7,800 |
| 120 | -3,133 | -18,600 | -9,448 | 22.2% | 8,200 |
| 160 | -3,371 | -22,600 | -10,000 | 22.2% | 8,600 |
| 200 | -3,609 | -26,600 | -10,320 | 22.2% | 9,000 |

The `+120` point is the last remotely defensible frontier probe. `+160` and
`+200` materially worsen early drawdown and tail stress for shrinking marginal
gain.

## Parameter Families Rejected

- Mean / width tuning: weaker official calibration; no structural reason to
  improve hidden 1M.
- Earlier/later simple release: tested via hardflat/hardlong/bid-release probes;
  fixed 60k release remained cleaner.
- Slopegates: delayed too much and gave up official-path alpha.
- Post-release recycler: negative/fragile in replay and can damage the base HYD
  position state.
- Mark/counterparty HYD: role-confounded and not strong enough to replace the
  regime model.
- Terminal flatten changes: diagnostic/risk-control, not a new PnL source.

## Upload Recommendation

If one more HYD upload is available:

`outputs/submissions/r4/submission_r4_final_sell7_hyd_abortgate18_long120_60.py`

Decision rule:

- If official HYD improves by about `+300` to `+500` versus long80 and max
  drawdown remains close, `long120` is a high-EV but higher-risk final candidate.
- If the official gain is smaller or the HYD path becomes visibly worse, stay
  with `abortgate18_long80_60`.
- Do not upload `long160` or `long200` unless the goal changes from robust final
  1M EV to an explicit high-variance path bet.

## Official Long120 Update

The official `abortgate18_long120_60` upload landed at:

| candidate | official HYD | touch-liquidated HYD | HYD min | HYD max DD |
|---|---:|---:|---:|---:|
| abortgate18 long80 | 7,657 | 6,007 | -1,489 | -4,038.75 |
| abortgate18 long120 | 8,052 | 6,402 | -2,292 | -4,038.75 |

This confirms the frontier shape: `+120` adds real cash PnL, but with worse
early inventory pain and worse rolling-tail stress.

## Current Default

Default max-EV HYD after the current official evidence:

`abortgate18_long120_60`

Cleaner risk-adjusted HYD:

`abortgate18_long80_60`
