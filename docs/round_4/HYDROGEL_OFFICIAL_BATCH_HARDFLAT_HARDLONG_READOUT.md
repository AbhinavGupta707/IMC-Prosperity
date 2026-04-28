# HYDROGEL Official Batch Readout: Cap80, Hardflat, Hardlong40

Date: 2026-04-27

Official logs analyzed:

- `r4 Sim Results/cap8060k/512331.log`
- `r4 Sim Results/hardflat60k/512637.log`
- `r4 Sim Results/hardlong4060k/512695.log`

## Headline

This is the cleanest HYD evidence so far. Other sleeves are unchanged at
`64,906.9`, so total deltas are exactly HYD deltas.

| run | official total | HYD PnL | delta vs old | HYD cash | final pos | avg buy | avg sell | last HYD fill |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| old `flat995` | 66,586.9 | 1,680 | 0 | 2,005,030 | -200 | | 10025.15 | 23,600 |
| cap80 60k | 69,200.9 | 4,294 | +2,614 | 2,007,644 | -200 | 10040.00 | 10038.30 | 61,000 |
| cap40 60k | 70,048.9 | 5,142 | +3,462 | 2,008,492 | -200 | 10040.80 | 10042.34 | 61,300 |
| hardflat 60k | 71,340.9 | 6,434 | +4,754 | 2,009,784 | -200 | 10029.00 | 10047.79 | 61,600 |
| hardlong40 60k | 72,057.9 | 7,151 | +5,471 | 2,010,501 | -200 | 10030.25 | 10047.91 | 61,900 |

Ranking:

1. `hardlong40_60k`
2. `hardflat_60k`
3. `cap40_60k`
4. `cap80_60k`
5. soft `noshort60k`
6. old `flat995`

## What We Learn

### 1. The high-regime diagnosis is confirmed

The monotonic cap result is exactly what the theory predicted:

- cap80: `4,294`
- cap40: `5,142`
- hardflat: `6,434`

More cheap early short inventory is worse. The R3-derived static anchor is not
wrong for the whole product, but it is wrong during this high-continuation
official slice.

### 2. Hard override beats soft filtering

Soft `noshort60k` officially landed at `3,512`, far below its local proxy.
Hardflat landed at `6,434`, close to the hard-prototype proxy.

Mechanism:

- soft wrapper still leaked sells before `60k`, filling `-200` from
  `54.5k-56k` around average `10034.52`;
- hardflat forcibly flattened early inventory at `21.5k`, then emitted no HYD
  orders until `60k`;
- hardflat sold the main short from `60.0k-61.6k` around average `10047.79`.

The likely lesson is implementation-level as much as strategy-level: filtering
orders by projected inventory is fragile when the inner strategy emits mixed
buy/sell or passive orders. For HYD regime overrides, hard replacement is
safer than soft filtering.

### 3. The missing alpha was a rising-leg position, but only modestly

Hardlong40 adds a controlled `+40` long target before release:

- buys to `+40` from `21.5k-21.8k` around `10030.25`;
- sells through `60.0k-61.9k` around `10047.91`;
- ends `-200`, same terminal mark.

The official gain over hardflat is `+717`, which is the rising-leg alpha. This
is real, but it is not a 20k breakthrough. The bigger improvement came from
not being short early and from selling the final short at high prices.

### 4. Terminal mark still matters

Every profitable high-regime variant ends `-200`, with the same implied
terminal mark `10016.75`. The official score is still:

`cash - 200 * terminal_mark`.

Hardlong40 is better because it improves cash, not because it removes terminal
risk. It remains `-200 PnL/tick` terminal-sensitive.

### 5. R3-style 20k realized HYD is not available in this 100k slice

R3 made 20k+ when the path gave a sell-high / buy-crash / resell-rebound cycle.
This R4 official slice does not give that cycle. It gives high continuation,
then a terminal fall. The best tested official extraction is now `7,151`, and
the remaining gap to the `18,017` terminal-mark oracle is dynamic turn timing,
not static width.

## Drawdown / Inventory

| run | min HYD PnL | peak HYD PnL | max drawdown | max long | max short |
| --- | ---: | ---: | ---: | ---: | ---: |
| old `flat995` | -7,086.62 | 1,781.75 | -8,780.62 | -6 | -200 |
| cap80 60k | -4,192.88 | 4,395.75 | -4,432.50 | -6 | -200 |
| cap40 60k | -3,344.88 | 5,243.75 | -4,038.75 | -6 | -200 |
| hardflat 60k | -2,028.38 | 6,535.75 | -4,038.75 | 0 | -200 |
| hardlong40 60k | -942.12 | 7,252.75 | -4,038.75 | +40 | -200 |

Hardlong40 has the best official PnL path in this batch. It reduces the early
drawdown substantially versus old flat995 because it does not carry the cheap
early short while HYD rises.

## Recommendation

Current best official HYD sleeve:

`outputs/submissions/r4/submission_r4_probe_hyd_highregime_hardlong40_60k.py`

Keep hardflat as the conservative fallback:

`outputs/submissions/r4/submission_r4_probe_hyd_highregime_hardflat_60k.py`

Do not spend more uploads on cap80-style relaxation. Cap80 confirmed the
monotonic relationship: allowing more early short inventory lowers PnL.

Next research should target:

1. hardlong target size sweep: `+20`, `+40`, `+60`, maybe `+80`;
2. release condition: fixed `60k` versus `bid >= 10048` or turn-confirmed;
3. terminal risk variants: keep `-200` for official-score probe, plus force-flat
   controls to separate realized edge from terminal mark.

Pushback: hardlong40 is still an official high-path probe, not proof of a
general HYD model. It is robustly better on the tested official path, but it
must be guarded so it only activates when HYD has actually entered the high
continuation regime.
