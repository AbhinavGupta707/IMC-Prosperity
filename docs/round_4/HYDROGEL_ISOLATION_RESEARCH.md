# Round 4 HYDROGEL Isolation Research

Date: 2026-04-27

## Artifacts

Script:

`src/scripts/round_4/analyze_hydrogel_isolation.py`

Run:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.analyze_hydrogel_isolation
```

Outputs:

`outputs/round_4/hydrogel_isolation/`

Key generated tables:

- `path_stats.csv`
- `hindsight_oracle.csv`
- `official_strategy_attribution.csv`
- `current_local_backtest.csv`
- `signal_edge_summary.csv`
- `candidate_family_summary.csv`
- `mark_flow_summary.csv`
- `HYDROGEL_DIAGNOSTICS_AUTOGEN.md`

## Executive Read

HYDROGEL looks like a delta-one path mean-reversion product with regime-level
mean shifts, not an option, basket, conversion, or pure terminal-mark artifact.
The best evidence is:

- historical full-day means are near the current anchor region but not
  identical: day 1 `9992.1`, day 2 `9989.4`, day 3 `10002.5`;
- returns have mild one-step reversal on all historical days
  (`ret_lag1_corr` about `-0.12`);
- deviation from the 9988 anchor is negatively correlated with forward moves,
  especially at 10k and 100k horizons;
- spread-aware static signal edges are positive across all three days when
  entries are far enough from the local anchor;
- the L1 force-flat hindsight oracle is large, so the opportunity is mostly
  tradable path recycling in hindsight, not only terminal inventory marking.

Pushback: the current official 100k HYD score is not good evidence that the
current HYD sleeve is robust. In the official slice it finishes `-200` short,
has only `+1,680` PnL, and is worth `-200` PnL per terminal tick. That is a
calibration warning, not a promotion signal.

## Hindsight Opportunity

The L1 hindsight oracle is deliberately overfit: it knows the future path and
can route top-of-book taker trades perfectly. It is useful only as an upper
bound on opportunity class.

| dataset | force-flat oracle | terminal-mark oracle | current / relevant baseline |
| --- | ---: | ---: | ---: |
| hist day 1 | 252,025 | 253,297 | `flat995` 48,959 |
| hist day 2 | 234,479 | 235,399 | `flat995` 62,414 |
| hist day 3 | 242,724 | 242,992 | `flat995` 50,766 |
| official 100k | 15,585 | 18,017 | current official 1,680 |

Interpretation:

- The historical upper bound is about `234k-252k` per 1M day versus current
  `49k-62k` per day. The current strategy captures roughly `20-27%` of this
  hindsight bound.
- Terminal-mark uplift over force-flat is tiny on historical days
  (`+268` to `+1,272`) and modest on official 100k (`+2,432`). The theoretical
  opportunity is not mainly terminal exposure.
- The official current strategy captures only about `11%` of the official
  force-flat hindsight bound and does so while carrying max short exposure.

## Current PnL Attribution

Official 100k:

- final HYD PnL: `+1,680`
- cash from trades: `+2,005,030`
- final position: `-200`
- implied official terminal mark: `10016.75`
- break-even terminal mark: `10025.15`
- sensitivity: `-200` PnL per terminal tick
- max drawdown: about `-8,781`

This means the official HYD result is the small residual between a huge short
cash balance and a huge negative terminal mark. If terminal were 25 ticks
higher, the same position would be about `-3,370` instead of `+1,680`.

Local 3x1M HYD-only replay:

| variant | PnL | final position | terminal tick sensitivity | comment |
| --- | ---: | ---: | ---: | --- |
| no terminal guard | 165,728 | +128 | +128/tick | locally higher, terminal-risk inflated |
| `flat995` | 162,139 | +12 | +12/tick | best safe baseline |
| `cap50_990` | 163,670 | +50 | +50/tick | small local gain for much more residual risk |

Per-day `flat995` is important: day 1 and day 2 finish flat, while day 3 ends
with only `+12`. So the safe variant is not just terminal-mark mining locally;
it realizes meaningful path PnL and cuts the hidden-fair sensitivity.

## Mean, Width, Flatten, Cap

The current final anchor `9988` is defensible but not sacred.

- Full-day means support the 9988/9995 region on days 1 and 2.
- Day 3 and the official 100k slice are high-mean windows
  (`10033.5` mean for the first 100k), so re-anchoring to the official slice
  would be overfit.
- Static signal tests show robust buy edges at very low entries and robust
  sell edges at higher anchors. That suggests a banded mean-reversion geometry,
  not a single exact fair.

The take width is structurally conservative. In lightweight candidate tests,
`mean=9988,width=28,flat990/995` slightly improves worst-day behavior versus
the current `width=32` family, but the evidence is not yet strong enough to
replace the production sleeve. It needs a full-engine variant and an official
calibration upload.

Flattening is structurally right. The local unguarded sleeve is inflated by
terminal inventory. `flat995` costs local PnL versus unguarded but converts a
large hidden-fair bet into a small residual. `cap50_990` is not recommended as
the safe candidate: the extra local PnL is too small for `+50/tick` terminal
sensitivity.

## Mark / Counterparty Read

HYD historical and official logs mostly expose `Mark 38` flow. A simple
aggressor-follow test does not support Mark flow as a primary HYD engine:

| source | Mark | side | events | 30k follow edge |
| --- | --- | --- | ---: | ---: |
| historical | Mark 38 | buy | 515 | -6.86 |
| historical | Mark 38 | sell | 507 | -9.40 |
| official | Mark 38 | buy | 54 | +2.27 |
| official | Mark 38 | sell | 140 | -16.81 |

The negative follow edges are consistent with Mark 38 often trading at
mean-reversion extremes or with a role/confounding effect. They are not enough
to justify an aggressive standalone Mark strategy. A Mark fade/recycler may be
worth a small probe only after the base HYD regime is controlled and only with
a negative control of similar frequency.

## What HYDROGEL Actually Is

Best classification:

`delta-one mean-reversion with regime-shifted anchors and terminal inventory risk`

Not supported as the primary classification:

- pure trend/path-regime: trend/path-fade candidate families did not dominate
  the static cycle tests;
- pure counterparty/Mark-driven: Mark flow is role-confounded and not robust
  as a standalone follow signal;
- pure terminal-mark artifact: hindsight force-flat opportunity is large, and
  local `flat995` still makes strong PnL with low final exposure.

The subtlety is that the current official 100k result itself is terminal-mark
dependent even though the asset opportunity is not. That distinction matters.

## Recommendation

Safe candidate: keep `submission_r4_safer_hydflat995.py` as the HYD sleeve for
now.

Why:

- It is positive on all three local 1M days.
- It reduces terminal sensitivity to about `+12/tick` in local replay.
- It avoids promoting the official 100k short-position artifact.
- The alternatives with higher local PnL (`unguarded`, `cap50_990`) are worse
  risk trades.

Do not promote a Mark-conditioned HYD strategy yet. Do not re-anchor HYD to the
official 100k mean.

## Next Upload-Calibrated Probes

Implemented probe details are recorded in
`docs/round_4/HYDROGEL_PROBE_IMPLEMENTATION.md`.

1. `HYD_OFFICIAL_FLAT95K`

Purpose: isolate realized official HYD edge from terminal exposure.

Design: start from the current HYD-only or full base, but force HYD flat from
`95,000` in the 100k simulator probe. This is an official calibration artifact,
not a final 1M candidate. If realized PnL collapses, the official score was
mostly terminal mark. If it stays positive, the official slice has actual
round-trip HYD edge that the final strategy can try to recycle.

2. `HYD_WIDTH28_FLAT995_OR_990`

Purpose: test whether the current `take_width=32` is too conservative.

Design: preserve the same static-cycle geometry and terminal flattening, but
run a full-engine HYD variant with final take width around `28`. Local
lightweight tests prefer this neighborhood on robust score, but only weakly.
Promote only if it improves cross-day replay and does not worsen official
drawdown/exposure.

3. Optional negative-control Mark probe: `HYD_MARK38_FADE_MICRO`

Purpose: check whether Mark 38 is real or just coincident with price extremes.

Design: very small HYD-only fade/recycler around Mark 38 aggressor flow,
paired with a frequency-matched non-Mark trigger. Reject if the negative
control performs similarly.
