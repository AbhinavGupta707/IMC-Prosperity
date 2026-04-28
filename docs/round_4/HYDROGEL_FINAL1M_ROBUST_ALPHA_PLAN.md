# HYDROGEL Final-1M Robust Alpha Plan

Date: 2026-04-27

## Bottom line

HYDROGEL is not behaving like a clean static mean-reverter in the official
100k slice. The useful edge is a **path-regime inventory/release effect**:
when HYD reveals a high continuation path early, the R3-derived sleeve sells
too early and carries a bad short through the rising leg. Suppressing or
reversing that short until the 60k release captures real cash PnL.

But the current best official 100k winners are not fully robust evidence. The
official HYD book path in this workspace matches historical day 3 first 100k,
so repeated upload tuning is very exposed to public-prefix overfit. The final
objective is unseen 1M ticks, so the right move is not to maximize the 100k
score with `hardlong80_60k`; it is to carry the high-regime idea only after the
path proves itself.

## What the official probes actually say

Official uploaded HYD attribution:

| run | total PnL | HYD PnL | HYD if touch-liquidated | final HYD pos | HYD max DD |
|---|---:|---:|---:|---:|---:|
| old_flat995 | 66,586.90 | 1,680 | 30 | -200 | -8,780.62 |
| cap40_60k | 70,048.90 | 5,142 | 3,492 | -200 | -4,038.75 |
| cap80_60k | 69,200.90 | 4,294 | 2,644 | -200 | -4,432.50 |
| hardflat60k | 71,340.90 | 6,434 | 4,784 | -200 | -4,038.75 |
| hardlong40_60k | 72,057.90 | 7,151 | 5,501 | -200 | -4,038.75 |
| hardlong80_60k | 72,563.90 | 7,657 | 6,007 | -200 | -4,038.75 |

Readout:

- The improvement over `flat995` is mostly real cash-path improvement, not a
  terminal-mark trick. All high-regime winners still end `-200`; the final
  touch liquidation stress subtracts about `1,650` from each.
- The official score rewards larger long exposure: `hardlong80 > hardlong40 >
  hardflat > cap40 > cap80`.
- That ranking is exactly what we would expect on the known high-continuation
  day-3 prefix. It is not enough proof for final unseen 1M.

## False-trigger stress

I evaluated 117 rolling historical 100k windows that would trigger on
`mid >= 10020` during relative `20k-30k`. This is an approximate inventory-path
stress test, not a full fill simulator. Its value is in comparing false-trigger
risk across policy shapes.

| policy | rolling overlay mean | worst window | positive rate | official-like overlay |
|---|---:|---:|---:|---:|
| hardlong80 fixed60k | -5,503 | -23,680 | 23.1% | +8,520 |
| hardlong40 fixed60k | -4,271 | -19,840 | 25.6% | +7,760 |
| hardflat fixed60k | -3,039 | -16,000 | 27.4% | +7,000 |
| cap40 fixed60k | -2,431 | -12,800 | 27.4% | +5,600 |
| slopegate15 cap40 flat60 | -2,101 | -13,440 | 23.1% | +6,640 |
| slopegate18 cap80 flat60 | -1,664 | -10,680 | 24.8% | +6,280 |

Critical interpretation:

- The robust alpha is **not** "always go longer". Long targets improve the
  official prefix but worsen false-trigger losses.
- The robust shape is **cap first, promote only on persistent high path, then
  release at 60k**.
- `slopegate18 cap80 flat60` is the most defensive of the tested candidates.
  It sacrifices 100k upside but has the best rolling false-trigger profile.
- `slopegate15 cap40 flat60` is the balanced candidate. It keeps more official
  upside and avoids choosing a threshold right on the observed official slope.

## Why R3-style HYD alpha looks lower now

The R3-derived HYD sleeve is locally decent, but in this R4 official/high path
it enters a stale short too early. Baseline `flat995` sells 200 HYD around
`10025.15` average and ends with only `1,680` HYD PnL. The high-regime wrappers
lift the average sell level toward `10047-10048`, which is where the real
official improvement comes from.

So we are not missing a totally different giant HYD mechanism yet. We are
missing a robust regime-control layer on top of a mean-reversion sleeve. Pure
mean/take-width tuning is secondary; inventory timing dominates.

## Upload probes created

Upload in this order:

1. `outputs/submissions/r4/submission_r4_probe_hyd_slopegate15_cap40_flat60.py`
   - balanced final-1M candidate
   - local official proxy HYD: `6,014`
   - rolling stress mean: `-2,101`

2. `outputs/submissions/r4/submission_r4_probe_hyd_slopegate15_cap40_long40_60.py`
   - alpha-bearing test for whether +40 long is real
   - local official proxy HYD: `6,324`
   - rolling stress mean: `-2,373`

3. `outputs/submissions/r4/submission_r4_probe_hyd_slopegate18_cap80_flat60.py`
   - defensive final-1M candidate
   - local official proxy HYD: `5,420`
   - rolling stress mean: `-1,664`

Do not upload another blind `hardlong80` variant as a final candidate unless we
explicitly decide to accept high overfit risk. It is the current 100k winner,
but its rolling false-trigger loss is the worst tested.

## Decision rule after uploads

- If `slopegate15_cap40_flat60` scores near the local proxy and keeps HYD
  drawdown near the high-regime family, it becomes the main robust HYD spine.
- If `slopegate15_cap40_long40_60` adds at least about `+400-700` HYD over
  flat without worsening drawdown materially, keep `+40`; otherwise reject the
  long overlay.
- If the defensive cap80 probe gives up only modest official PnL while keeping
  lower drawdown/stress, it is the better final-1M choice than hardlong.
- If slope-gated probes collapse officially, the simulator fill path dislikes
  the extra gate churn; fall back to `hardflat60k` or `cap40_60k`, not
  `hardlong80`, for robustness.

## Artifacts

- `src/scripts/round_4/evaluate_hydrogel_confirmation_gates.py`
- `src/scripts/round_4/evaluate_hydrogel_slope_gate_grid.py`
- `outputs/round_4/hydrogel_probes/confirmation_gate_replay_summary.csv`
- `outputs/round_4/hydrogel_probes/confirmation_gate_rolling_summary.csv`
- `outputs/round_4/hydrogel_probes/slope_gate_grid_summary.csv`
- `outputs/round_4/hydrogel_probes/probe_local_summary.csv`
