# HYDROGEL Hardlong80 Official Readout

Date: 2026-04-27

## What Was Added

New official simulator results were added for:

- `hardlong8060k`: high-regime trigger, hard target `+80` until `60k`.
- `bid 70k`: high-regime trigger, hard target `+40` until `bid >= 10052` or
  `70k` fallback.
- `probe/513378`: non-HYD stack probe; HYD behavior is the old `flat995`.

Batch summary output:

- `outputs/round_4/hydrogel_probes/official_hydrogel_probe_batch_summary.csv`

Analyzer:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.analyze_hydrogel_official_probe_batch
```

## Official Results

Other-product PnL is unchanged at `64,906.9` for the HYD high-regime probes,
so their deltas are clean HYD deltas.

| run | total PnL | HYD PnL | HYD delta vs `flat995` | final HYD pos | avg buy | avg sell | min HYD PnL |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `flat995` | 66,586.9 | 1,680 | 0 | -200 | | 10025.15 | -7,086.62 |
| `hardflat60k` | 71,340.9 | 6,434 | +4,754 | -200 | 10029.00 | 10047.79 | -2,028.38 |
| `hardlong40_60k` | 72,057.9 | 7,151 | +5,471 | -200 | 10030.25 | 10047.91 | -942.12 |
| `bid10052_70k` | 71,957.9 | 7,051 | +5,371 | -200 | 10030.25 | 10047.52 | -883.62 |
| `hardlong80_60k` | 72,563.9 | 7,657 | +5,977 | -200 | 10031.84 | 10047.73 | -1,488.62 |

Mechanism read:

- `hardlong80_60k` is the best official HYD result so far.
- It adds `+506` HYD over `hardlong40_60k`.
- `bid10052_70k` loses `-100` HYD versus `hardlong40_60k`, confirming that
  later structural release does not improve this path.
- `probe/513378` improves total PnL by changing non-HYD products; its HYD PnL
  remains exactly `1,680`.

## Realized Versus Terminal Mark

All high-regime winners end `-200` HYD. That means the 100k official HYD PnL is
still terminal-mark sensitive.

| run | marked HYD PnL | stress PnL if cover at final ask | stress haircut |
| --- | ---: | ---: | ---: |
| `flat995` | 1,680 | 30 | -1,650 |
| `hardflat60k` | 6,434 | 4,784 | -1,650 |
| `hardlong40_60k` | 7,151 | 5,501 | -1,650 |
| `bid10052_70k` | 7,051 | 5,401 | -1,650 |
| `hardlong80_60k` | 7,657 | 6,007 | -1,650 |

Interpretation:

- The improvement is not purely terminal mark, because all these probes have
  the same final `-200` exposure and the same final-touch stress haircut.
- The improvement is mostly better inventory path and better short-entry price.
- But the absolute level remains terminal sensitive: if final marking or forced
  cover were less favorable, all `-200` variants lose about `1.65k` on this
  100k slice.

## Capture Of Hindsight Opportunity

Prior official HYD hindsight estimates:

- force-flat L1 oracle: `15,585`
- terminal-mark L1 oracle: `18,017`

Capture:

| run | HYD PnL / terminal oracle | final-touch-stressed PnL / force-flat oracle |
| --- | ---: | ---: |
| `flat995` | 9.3% | 0.2% |
| `hardflat60k` | 35.7% | 30.7% |
| `hardlong40_60k` | 39.7% | 35.3% |
| `hardlong80_60k` | 42.5% | 38.5% |

On local full historical 1M days, `hardlong80_60k` captures about `23.1%` of
the force-flat hindsight oracle. That is only slightly above `hardlong40_60k`
at about `23.0%` and `flat995` at about `22.2%`, because the hardlong overlay
only changes the day-3 style opening regime.

## Overfit Assessment

This is a good mechanism, but not a fully robust final theorem.

Robust evidence:

- Early static shorts are bad in the high-continuation prefix.
- Hard order replacement is better than soft no-short filtering.
- Carrying some long inventory before the high short flip is beneficial on the
  official prefix.
- Official results match local mechanism expectations directionally.

Overfit evidence:

- The official 100k HYD book path matches public day-3 first 100k in the local
  workspace, so this is not an independent price-path validation.
- Rolling historical 100k windows show that `mid >= 10020` in relative
  `20k-30k` is usually not enough to justify long-until-60k:
  - `long40_to_fixed` mean: `-1,231.8`
  - positive rate: `12.8%`
  - worst case: `-3,840`
- The size ramp keeps adding PnL on this path, which is exactly what a
  path-fit rising-leg bet should do.

Local fixed-60k size ramp:

| target | official-log proxy HYD | local min HYD PnL |
| ---: | ---: | ---: |
| 0 | 6,626 | -1,774 |
| 40 | 7,370 | -1,030 |
| 80 | 7,867 | -1,161 |
| 120 | 8,346 | -1,892 |
| 160 | 8,596 | -2,843 |
| 200 | 8,776 | -3,842 |

This says more alpha probably exists on the uploaded 100k path by increasing
long target further. It does not say that larger target is robust for unseen
1M.

## Recommendation

Current strategy family is still right:

`regime-conditioned mean reversion / inventory timing`

For final unseen 1M:

- `hardlong80_60k` is the highest official-EV HYD candidate so far.
- It is also more path-fit than `hardlong40_60k`.
- `hardlong40_60k` is the cleaner risk-adjusted high-regime overlay.
- `hardflat60k` remains the cleaner conservative variant.

Do not interpret the `hardlong80` win as proof that we should keep scaling
blindly. The next possible upload if maximizing this 100k path would be a
`+120` target, but that is a deliberate overfit probe, not a robustness probe.

The next robust-alpha work should target recycling after the first short fill.
Right now the strategy reaches `-200` by about `62.2k` and stops. The remaining
oracle gap is mostly dynamic path recycling, not first-entry timing.
