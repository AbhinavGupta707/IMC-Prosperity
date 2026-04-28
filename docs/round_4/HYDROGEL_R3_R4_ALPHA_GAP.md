# HYDROGEL R3 vs R4 Alpha Gap

Date: 2026-04-27

## Headline

HYDROGEL is not suddenly dead. The low R4 official HYD number is mostly a
regime/slice problem:

- R3 official 100k paths had full mean-reversion cycles: sell high, buy the
  breakdown, sell/recycle the rebound.
- R4 official 100k is a high-regime continuation path. The current R3-derived
  strategy sells too early, then gets paid only by the lower terminal mark.
- R4 historical 1M replay is still strong: `flat995` is about `162k` across
  three days, or about `54k/day`, with low terminal exposure.

So the question is not "why did HYD vanish?" It is "how do we classify and
trade the official high-regime path without overfitting it?"

## R3 100k Simulator Geometry

Representative R3 official HYD-only runs:

| run | HYD PnL | final pos | abs qty | avg buy | avg sell | comment |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `aggressive_new_418798` | 19,880 | 0 | 948 | 9944.45 | 9986.39 | realized/flat |
| `v2_guarded_426894` | 39,295.6 | +200 | 1,936 | 9953.86 | 9997.76 | larger terminal long residual |
| `r3_32_436360` | 28,097.6 | +200 | 1,028 | 9940.11 | 9998.47 | publicguard-ish |

R3 official path landmarks:

| timestamp | mid |
| ---: | ---: |
| 5,000 | 10027 |
| 24,400 | 9993.5 |
| 50,000 | 9952 |
| 53,800 | 9935.5 |
| 68,800 | 9997 |
| 91,100 | 9915 |
| 99,900 | 9960 |

This is perfect for the R3 publicguard/cycle idea. The path gives cheap buys
after the early sell and then multiple exits/recycles. The flat `aggressive`
run made about `19.9k` by buying around `9944` and selling around `9986`.

## R4 Official 100k Geometry

R4 official path landmarks:

| timestamp | mid |
| ---: | ---: |
| 5,000 | 10019 |
| 22,300 | 10029 |
| 24,400 | 10034 |
| 50,000 | 10042 |
| 53,800 | 10048.5 |
| 60,000 | 10056 |
| 68,800 | 10047.5 |
| 91,100 | 10044 |
| 99,900 | 10017 |

This path starts with a vaguely R3-like prefix, then diverges exactly where R3
had the tradable breakdown. At `24.4k`, R3 is `9993.5`; R4 is `10034`. That is
not a small parameter drift. It is a different path regime.

Current official results:

| candidate | official total | HYD PnL | final pos | avg sell |
| --- | ---: | ---: | ---: | ---: |
| old `flat995` | 66,586.9 | 1,680 | -200 | 10025.15 |
| width28 | 65,794.9 | 888 | -200 | 10021.19 |
| cap40 60k | 70,048.9 | 5,142 | -200 | 10042.34 |
| no-short 60k | 68,418.9 | 3,512 | -200 | 10034.52 |

The cap40 result proves the direction: delay cheap early shorts. It does not
prove a general 20k HYD edge in this slice.

## Why R4 Is Lower Than R3

1. R3 had realized recycling. R4 mostly has terminal exposure.
   - R3 `aggressive_new`: flat, cash PnL `19,880`.
   - R4 old `flat995`: cash `2,005,030`, terminal component about
     `-2,003,350`, net `1,680`.

2. The R3 public-prefix guard is stale on R4 official.
   - The early path no longer breaks down to the publicguard mean.
   - It sells early because the inherited anchor treats `10020-10035` as rich.

3. Width is the wrong control.
   - Width28 sold earlier and cheaper.
   - This loses money in high continuation paths.

4. The missing official 100k alpha is the long/flat-before-short leg.
   - The L1 terminal-mark oracle is about `18,017`.
   - cap40 captures `5,142`.
   - The gap is mostly dynamic inventory timing: avoid/own the rising leg, then
     flip short at high prices, then manage terminal/cover risk.

5. Local 1M HYD remains strong.
   - Current `flat995` local 3x1M HYD is `162,139`.
   - The R4 official 100k slice is not representative of the whole local 1M
     path distribution. It is a calibration slice.

## Prototype Harness

Script:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.evaluate_hydrogel_alpha_prototypes
```

Output:

`outputs/round_4/hydrogel_probes/alpha_prototype_summary.csv`

Official-log proxy results:

| candidate | proxy HYD PnL | final pos | avg buy | avg sell | comment |
| --- | ---: | ---: | ---: | ---: | --- |
| baseline flat995 | 1,816 | -200 | | 10026.08 | current mechanism |
| cap40 60k filter | 5,541 | -200 | 10027.00 | 10044.62 | matches official direction |
| hard flat until 60k | 6,626 | -200 | | 10050.13 | remove inner HYD leakage |
| hard long40 until 60k | 7,370 | -200 | 10029.65 | 10049.82 | adds small rising-leg long |
| hard long80 until 60k | 7,867 | -200 | 10031.51 | 10049.24 | higher upside, more path risk |

These are not upload guarantees. The official `noshort_60k` result already
showed that soft wrappers can differ from the proxy. But the ranking tells us
where the next hypothesis lives.

## Best Next Alpha Direction

Use a two-regime HYD state machine:

1. Public/R3-breakdown mode
   - If the path breaks down by the public checkpoints, keep the R3-style
     publicguard/cycle reset. That is where the old 20k+ realized alpha came
     from.

2. High-continuation mode
   - If HYD is still above about `10020` during `20k-30k`, stop treating the
     9988/9955 anchors as immediately tradable shorts.
   - Before release: hard override HYD to flat or a small long target.
   - Release: short only when price is actually high enough, or after a
     confirmed turn. In the official path, `bid >= 10048` and `60k` coincide.
   - Terminal: keep explicit flat/mark-risk variants.

The next upload-calibrated probes should be:

1. `hard_flat_until_60k`
   - Purpose: test whether a hard HYD override fixes the leakage seen in
     official `noshort_60k`.
   - Proxy HYD: `6,626`, versus official cap40 `5,142`.
   - File:
     `outputs/submissions/r4/submission_r4_probe_hyd_highregime_hardflat_60k.py`

2. `hard_long40_until_60k`
   - Purpose: test the missing rising-leg alpha with modest size.
   - Proxy HYD: `7,370`.
   - Upload only after hard-flat calibrates, because this intentionally takes
     more path-regime risk.
   - File:
     `outputs/submissions/r4/submission_r4_probe_hyd_highregime_hardlong40_60k.py`

Do not chase `cap80` or `width28` for alpha. They answer weaker questions.

## Pushback

The dream target is not "make R4 official HYD 20k by tuning width." The R3 20k
came from realized cycles that the R4 official 100k path does not offer. In
this R4 slice, a robust next step is probably worth a few thousand more, not
the full R3 number, unless we intentionally bet on a high-regime trend/turn
state. The true 20k+ opportunity in R4 official exists in hindsight, but it
requires long/short dynamic timing, not the current static mean-reversion
sleeve.
