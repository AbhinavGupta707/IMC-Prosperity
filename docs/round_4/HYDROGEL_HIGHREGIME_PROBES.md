# HYDROGEL High-Regime Probe Readout

Date: 2026-04-27

## Why This Probe Family Exists

The official `flat95k` and width28 uploads answered two narrow questions:

- `flat95k` showed that the current official HYDROGEL PnL is not realized
  round-trip edge. It is mainly a short inventory position marked at a lower
  terminal price.
- width28 showed that simply selling earlier is worse in the official 100k
  path. The bot gets the same `-200` terminal exposure but with cheaper entry
  cash.

The next plausible source of PnL is therefore not another static width tweak.
It is high-regime inventory timing: when HYD is still elevated in the
`20k-30k` discovery window, do not let the R3-derived static anchor fill the
short book too early.

## Uploadable Probe Files

All files are full-strategy submissions based on `submission_r4_safer_hydflat995.py`.
Only the HYDROGEL sleeve is wrapped.

| file | mechanism | intent |
| --- | --- | --- |
| `outputs/submissions/r4/submission_r4_probe_hyd_highregime_noshort_60k.py` | if HYD mid >= `10020` during `20k-30k`, suppress HYD shorts until `60k` | highest-upside probe |
| `outputs/submissions/r4/submission_r4_probe_hyd_highregime_cap40_60k.py` | same trigger, cap HYD short inventory at `-40` until `60k` | safer mechanism check |
| `outputs/submissions/r4/submission_r4_probe_hyd_highregime_cap80_60k.py` | same trigger, cap HYD short inventory at `-80` until `60k` | lower-upside cap sensitivity |
| `outputs/submissions/r4/submission_r4_probe_hyd_highregime_noshort_50k.py` | same trigger, suppress HYD shorts until `50k` | early-release control |

The trigger does not fire on historical day 1 or day 2 in the current replay.
It fires on historical day 3, which matches the official 100k HYD path.

## Main Replay Results

Script:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.evaluate_hydrogel_probe_submissions
```

Output:

`outputs/round_4/hydrogel_probes/probe_local_summary.csv`

| candidate | hist 3x1M HYD PnL | official-log HYD PnL | official-log min PnL | official-log max drawdown | final pos |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline `flat995` | 162,139 | 1,816 | -6,984 | -8,800 | -200 |
| width28 `flat995` | 162,922 | 942 | -7,858 | -8,800 | -200 |
| highregime no-short 50k | 163,830 | 3,507 | -5,293 | -5,293 | -200 |
| highregime cap80 60k | 164,925 | 4,602 | -4,060.5 | -4,632.5 | -200 |
| highregime cap40 60k | 165,864 | 5,541 | -2,859 | -4,100 | -200 |
| highregime no-short 60k | 166,936 | 6,613 | -1,787 | -4,100 | -200 |

The high-regime wrappers improve the official-like path by improving short
entry cash, not by changing the terminal mark. Final position remains `-200`
in the 100k proxy.

## Timing Grid

Script:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.evaluate_hydrogel_highregime_grid
```

Output:

`outputs/round_4/hydrogel_probes/highregime_grid_summary.csv`

Official-log release timing for no-short variants:

| release | HYD PnL | avg sell | min PnL | max drawdown |
| ---: | ---: | ---: | ---: | ---: |
| baseline | 1,816 | 10026.08 | -6,984 | -8,800 |
| 45k | 1,939 | 10026.70 | -6,861 | -6,861 |
| 50k | 3,507 | 10034.50 | -5,293 | -5,293 |
| 55k | 3,862 | 10036.26 | -4,938 | -4,938 |
| 60k | 6,613 | 10049.95 | -1,787 | -4,100 |
| 65k | 4,452 | 10039.20 | -2,748 | -4,100 |
| 70k | 3,210 | 10033.02 | -3,990 | -3,990 |
| 75k | 3,682 | 10035.37 | -3,518 | -3,518 |

Cap sensitivity at `60k`:

| early short cap | HYD PnL | avg sell | min PnL | max drawdown |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 6,613 | 10049.95 | -1,787 | -4,100 |
| -40 | 5,541 | 10044.62 | -2,859 | -4,100 |
| -80 | 4,602 | 10039.95 | -4,060.5 | -4,632.5 |
| -120 | 3,615 | 10035.03 | -5,085 | -6,088 |
| -160 | 2,725 | 10030.61 | -6,075 | -7,536 |

The local optimum is specific: releasing at `60k` sells into the `60k-61.6k`
price spike. Releasing earlier leaves money on the table; releasing later
misses the spike.

## Mechanism

In the official-log proxy:

- baseline sells `200` units from `22.3k` to `23.8k` at average `10026.08`;
- no-short 60k sells mostly from `60.0k` to `61.6k` at average `10049.95`;
- terminal mark is unchanged at `10017`;
- final position is unchanged at `-200`.

So the improvement is:

`201 * (roughly 10050 sale price) - 200 * (roughly 10026 baseline sale price)`

net of one small buy/sell maker interaction around `38.6k-38.7k`.

This is better evidence than width tuning because it changes the inventory
path in the direction predicted by the path diagnosis. It is still not proof
of a general HYD alpha.

## Professional Read

Current HYD is not a robust standalone mean-reversion asset under this slice.
It is a path-regime plus terminal-mark instrument:

- in low/normal paths, the static R3 anchor can still make money;
- in high paths, early static-anchor shorts are bad;
- the official 100k result rewards ending short only because the terminal mark
  is lower than the high-regime sale prices.

The high-regime cap/no-short family is a good official calibration family, not
yet a final theorem. It is conditionally path-aware but still path-conditioned:
only one public/official-like high-regime slice validates the trigger and the
release timing.

## Official Upload Results

Added official simulator logs:

- `r4 Sim Results/cap4060k/512019.log`
- `r4 Sim Results/noshort60k/512110.log`

| candidate | official total | official HYD PnL | HYD cash | HYD final pos | avg HYD sell | last HYD fill |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| old `flat995` | 66,586.9 | 1,680 | 2,005,030 | -200 | 10025.15 | 23,600 |
| highregime cap40 60k | 70,048.9 | 5,142 | 2,008,492 | -200 | 10042.34 | 61,300 |
| highregime no-short 60k | 68,418.9 | 3,512 | 2,006,862 | -200 | 10034.52 | 56,000 |

Other sleeves are unchanged at `64,906.9`; the total deltas are HYD deltas.

The official `cap40_60k` result is the important positive readout. It improved
HYD by `+3,462` versus old `flat995` while keeping the same terminal mark and
ending `-200`.

The official `noshort_60k` result did not match the local proxy. It behaved
much closer to the early-release/no-short-50k proxy, with the main short filled
around `54.5k-56k` at average `10034.52` instead of the local proxy's
`60k-61.6k` average `10049.95`. Treat this as evidence that aggressive
no-short is less reliably calibrated in the official simulator than the cap
variant.

## Updated Upload Recommendation

Current best official HYD sleeve:

1. `submission_r4_probe_hyd_highregime_cap40_60k.py`

Do not prioritize `cap80_60k` or `noshort_50k` for leaderboard improvement:

- `cap80_60k` is expected to sit below `cap40_60k` because it allows more
  cheap early short inventory.
- `noshort_50k` is now mostly redundant because official `noshort_60k` already
  behaved like an early-release variant and landed well below `cap40_60k`.

Do not spend another upload on width28 unless the goal is only to confirm the
already observed negative result.

## Next Serious Model

If the upload confirms this, the next model should replace timestamp release
with a structural high-regime state:

- detect high path from early observed mids;
- suppress or cap short inventory while the high path is rising;
- release shorts on a volatility/turn condition or when bid levels enter a
  high enough percentile;
- keep terminal exposure explicit, with separate force-flat and terminal-mark
  variants.

The remaining oracle gap is still large: official terminal-mark oracle is
about `18,017`, versus `5,142` for cap40 60k. The missing edge is dynamic
long/short recycling and better turn timing, not just a better static cap.
