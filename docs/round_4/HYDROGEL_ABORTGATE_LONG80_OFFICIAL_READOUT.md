# HYDROGEL Abortgate Long80 Official Readout

Date: 2026-04-27

## Uploaded Run

Uploaded zip:

`r4 Sim Results/abortgate18long8060.zip`

Extracted official log:

`r4 Sim Results/abortgate18long8060/518320.log`

The run corresponds to:

`outputs/submissions/r4/submission_r4_final_sell7_hyd_abortgate18_long80_60.py`

## Official Result

| run | total PnL | HYD PnL | non-HYD PnL | touch-liquidated HYD | final HYD pos | HYD max DD |
|---|---:|---:|---:|---:|---:|---:|
| abortgate15_long40_60 | 74,126.81 | 7,151 | 66,975.81 | 5,501 | -200 | -4,038.75 |
| abortgate18_long80_60 | 74,632.81 | 7,657 | 66,975.81 | 6,007 | -200 | -4,038.75 |
| hardlong80_60k | 72,563.90 | 7,657 | 64,906.90 | 6,007 | -200 | -4,038.75 |

The official HYD delta versus abortgate-long40 is:

`+506`

This is exactly the hardlong80 HYD result on this path. The abort gate passes,
so the uploaded strategy collapses to the same HYD behavior as hardlong80 while
keeping an abort escape hatch for failed high-regime paths.

## Attribution

| run | HYD cash | terminal mark component | final pos | final mid | final bid/ask |
|---|---:|---:|---:|---:|---:|
| abortgate15_long40_60 | 2,010,501 | -2,003,400 | -200 | 10,017 | 10,009 / 10,025 |
| abortgate18_long80_60 | 2,011,007 | -2,003,400 | -200 | 10,017 | 10,009 / 10,025 |

The improvement is cash, not terminal mark. Both variants carry the same final
`-200` HYD and the same terminal mark component.

The touch-liquidated haircut is also identical:

`-1,650`

So the long80 improvement is not from hiding a larger terminal exposure.

## Trade Path

The long40 candidate buys to `+40` between `21.5k` and `21.8k`, then sells to
`-200` from `60.0k` to `61.9k`.

The long80 candidate buys to `+80` between `21.5k` and `22.2k`, then sells to
`-200` from `60.0k` to `62.2k`.

| run | buy qty | sell qty | avg buy | avg sell | last HYD fill |
|---|---:|---:|---:|---:|---:|
| abortgate15_long40_60 | 52 | 252 | 10,030.25 | 10,047.91 | 61,900 |
| abortgate18_long80_60 | 92 | 292 | 10,031.84 | 10,047.73 | 62,200 |

The extra `+40` long inventory earns roughly `+506`, or about `12.65` ticks per
unit, after paying the later-entry and later-exit prices.

## Local Calibration

Before upload, local official-proxy HYD estimates were:

| candidate | local official-proxy HYD | official HYD | official - local |
|---|---:|---:|---:|
| abortgate15_long40_60 | 7,370 | 7,151 | -219 |
| abortgate18_long80_60 | 7,867 | 7,657 | -210 |

The local fill model remains consistently optimistic by about `200` HYD on this
family. That is good calibration.

## Robustness Cost

Approximate rolling high-trigger stress:

| policy | rolling overlay mean | worst window | p10 | positive rate | official-like overlay |
|---|---:|---:|---:|---:|---:|
| abortgate18 long40 | -2,657 | -16,800 | -8,400 | 24.8% | +7,400 |
| abortgate18 long80 | -2,895 | -16,800 | -8,648 | 23.9% | +7,800 |

The added size costs about `-238` in rolling mean and about `-248` at p10, while
buying about `+500` on the official path. Worst-window stress is unchanged in
the approximate grid.

## Interpretation

This is a clean positive readout.

What it proves:

- `+80` is not just terminal-mark inflation; the gain is realized HYD cash.
- The local proxy predicted the direction and magnitude well.
- The official fill path did not introduce new slippage large enough to erase
  the expected gain.

What it does not prove:

- It does not prove the final 1M hidden path will be high-regime.
- It does not prove long80 is globally robust; it is still more path-risky than
  long40.
- It does not show the abort gate's value on the official path, because the gate
  passes and never rejects.

## Final HYD Decision

After this upload, HYD ranking changes:

1. **Higher-EV / moderate extra risk:** `abortgate18_long80_60`
2. **Safer robust default:** `abortgate15_long40_60`
3. **Conservative fallback:** `abortgate15_long20_60`

If we are selecting HYD in isolation and want maximum expected PnL without
accepting raw path-oracle behavior, `abortgate18_long80_60` is now the leading
candidate.

If the full non-HYD stack is already very path-risky, `abortgate15_long40_60`
remains the safer portfolio-level HYD sleeve.

