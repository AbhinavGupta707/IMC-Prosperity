# HYDROGEL Abortgate Long120 Official Readout

Date: 2026-04-27

## Uploaded Run

Uploaded zip:

`r4 Sim Results/abortgate120.zip`

Extracted official log:

`r4 Sim Results/abortgate120/518758.log`

Submission:

`outputs/submissions/r4/submission_r4_final_sell7_hyd_abortgate18_long120_60.py`

## Official Result

| run | total PnL | HYD PnL | non-HYD PnL | touch-liquidated HYD | final HYD pos | HYD min PnL | HYD max DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| abortgate15_long40_60 | 74,126.81 | 7,151 | 66,975.81 | 5,501 | -200 | -942 | -4,038.75 |
| abortgate18_long80_60 | 74,632.81 | 7,657 | 66,975.81 | 6,007 | -200 | -1,489 | -4,038.75 |
| abortgate18_long120_60 | 75,027.81 | 8,052 | 66,975.81 | 6,402 | -200 | -2,292 | -4,038.75 |

Official deltas:

| comparison | HYD delta | touch-liquidated delta |
|---|---:|---:|
| long80 - long40 | +506 | +506 |
| long120 - long80 | +395 | +395 |
| long120 - long40 | +901 | +901 |

## Attribution

| run | HYD cash | terminal mark component | final pos | final mark |
|---|---:|---:|---:|---:|
| long80 | 2,011,007 | -2,003,400 | -200 | 10,017 |
| long120 | 2,011,402 | -2,003,400 | -200 | 10,017 |

The `+395` improvement versus long80 is entirely cash. Final inventory and
terminal mark exposure are unchanged.

## Trade Path

Long80:

- buys to `+80` by `22.2k`;
- sells to `-200` by `62.2k`;
- average buy `10,031.84`, average sell `10,047.73`.

Long120:

- buys to `+120` by `22.5k`;
- sells to `-200` by `62.5k`;
- average buy `10,033.33`, average sell `10,047.60`.

| run | buy qty | sell qty | avg buy | avg sell | last HYD fill |
|---|---:|---:|---:|---:|---:|
| long80 | 92 | 292 | 10,031.84 | 10,047.73 | 62,200 |
| long120 | 132 | 332 | 10,033.33 | 10,047.60 | 62,500 |

The extra `+40` long from long80 to long120 earns about `+395`, or about `9.9`
ticks per unit after worse entry/exit prices.

## Local Calibration

Before upload:

- local official-proxy HYD for long120: `8,346`;
- official HYD: `8,052`;
- official - local: `-294`.

The local model remained directionally correct, but optimism increased versus:

- long40: about `-219`;
- long80: about `-210`;
- long120: about `-294`.

This is mild evidence that higher size starts paying more slippage than the
local proxy captures.

## Risk Read

The official max drawdown number is unchanged, but the early HYD minimum worsens:

| run | official HYD min |
|---|---:|
| long40 | -942 |
| long80 | -1,489 |
| long120 | -2,292 |

Rolling false-trigger stress also worsens:

| target | rolling mean | worst window | p10 | official-like overlay |
|---:|---:|---:|---:|---:|
| 80 | -2,895 | -16,800 | -8,648 | 7,800 |
| 120 | -3,133 | -18,600 | -9,448 | 8,200 |
| 160 | -3,371 | -22,600 | -10,000 | 8,600 |
| 200 | -3,609 | -26,600 | -10,320 | 9,000 |

Long120 is still defensible. Long160/200 are not attractive on risk-adjusted
grounds: marginal official-like upside shrinks while tail risk worsens sharply.

## Interpretation

This is a positive but diminishing-return result.

What it proves:

- The high-regime size edge continues through `+120` on the official path.
- The gain is cash-realized, not terminal-mark inflation.
- The fill path does not break; it simply pays worse marginal entry and exit
  prices.

What it warns:

- Marginal gain fell from `+506` for long40 -> long80 to `+395` for long80 ->
  long120.
- HYD minimum worsened by about `803` versus long80.
- Rolling p10 worsened by about `800`; worst-window stress worsened by `1,800`.

## Final HYD Decision

Updated HYD ranking:

1. **Max EV / higher risk:** `abortgate18_long120_60`
2. **Best risk-adjusted:** `abortgate18_long80_60`
3. **Safer fallback:** `abortgate15_long40_60`

For HYD in isolation, `abortgate18_long120_60` is now the leading expected-PnL
candidate.

For a robustness-first full portfolio, `abortgate18_long80_60` remains cleaner.

Do not continue to long160/long200 unless intentionally making a higher-variance
path bet.

