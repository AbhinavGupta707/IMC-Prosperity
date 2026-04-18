# Review: phase5_ewma

> STALE: This pack predates the day-aware timestamp fix for combined
> multi-day review artifacts. Use
> `outputs/review_packs/20260411T222629Z_phase5_ewma/` instead.

- **Run ID:** 20260411T185706Z_phase5_ewma
- **Generated:** 2026-04-11T18:57:06.176011+00:00
- **Commit:** cbadb43

Phase 5 challenger pack — TOMATOES on `ewma_mid` with `ewma_alpha=0.20`,
same Phase 3 tuned execution params as the incumbent. Companion
incumbent pack: `outputs/review_packs/20260411T185701Z_phase5_weighted/`.

## Decision
**discard** for the current tutorial baseline (Phase 5 outcome:
`ewma_mid` evaluated and kept out of production per the promotion
rules). The estimator remains registered and available for future
rounds.

## What looked good
- `summary.txt` TOMATOES line: PnL +1301, 115 trades, 0 near-limit,
  final position 7. 4.7x incumbent PnL on the same replay with
  inventory discipline unchanged.
- `charts/price_vs_fair_TOMATOES.png` shows EWMA tracking a genuinely
  smoothed anchor when the mid spikes, and the trade markers cluster
  where the mid is noticeably away from fair. Visibly different
  behaviour from the incumbent's flat fair-value line.
- Timestamp drilldown `drilldowns/timestamp_TOMATOES_141800/` captures
  three taker fills in a 40-step window around the top Phase 5
  divergence timestamp: ts=140200 buy 6 @ 4991 (fair 4992.74, mid
  4988.5), ts=140900 buy 8 @ 5003 (fair 5005.09, mid 5000.5), ts=141700
  sell 8 @ 4997 (fair 4995.67, mid 5000.0). All three trades fade the
  mid back toward the smoothed anchor, which is exactly the pattern
  the EWMA is designed to surface. The incumbent pack's same drilldown
  window shows zero trades — weighted_mid did not see edge there.
- `avg_entry_edge +1.002` (vs incumbent +0.683) is the clearest
  single-number evidence that EWMA picks decision points with more
  favourable edge at fill time.
- `charts/position_over_time_TOMATOES.png` stays well away from
  position limit throughout. `steps_near_limit=0`.

## What looked bad
- `charts/markouts_TOMATOES.png`: per-trade markouts at +1/+5/+20 are
  `+1.77 / +1.86 / +2.22` versus the incumbent's `+4.06 / +3.63 /
  +3.23`. On a per-unit basis each challenger trade captures less
  than half the edge of each incumbent trade — the challenger trades
  more aggressively with smaller edges. Fails Phase 5 rule 5 on the
  letter.
- Stage 1 fit-quality metrics: EWMA α=0.20 `mae_n1=0.895` is 13.3%
  worse than the best non-anchor estimator (`mid=0.790`) and 9.8%
  worse than the incumbent (`weighted_mid=0.815`). Only `mae_n5`
  (`1.227` vs incumbent `1.187`, +3.4%) clears the 5% band. Fails
  Phase 5 rule 1 on `mae_n1`.
- `charts/maker_taker_TOMATOES.png`: 825 of 827 traded units were
  taker — the EWMA baseline is essentially a taker strategy. Any
  maker quote the execution layer posted was not filled. That's a
  structural shift away from "market making" toward "aggressive
  fading," which is a different product archetype than the Phase 3
  doctrine promised.
- Stage 2 alpha plateau is narrow. Contiguous grid points `α=0.18`
  (PnL 1171) and `α=0.20` (PnL 1301) clear the 10%-of-peak rule with
  0 near-limit, but `α=0.22` collapses to 957 (-26% from peak) and
  `α=0.16` re-enters the near-limit regime (163 steps). Two grid
  points is a thin plateau — doctrine §8 prefers "broad parameter
  plateaus over peak settings."
- All four observations are single-replay signals. The tutorial
  replay is 20k steps on one day's book; Phase 6 robustness work
  (not yet started) is the honest place for a multi-replay re-check.

## Most important chart to inspect
`charts/price_vs_fair_TOMATOES.png` around the `141800` window, with
the `drilldowns/timestamp_TOMATOES_141800/` summary open alongside.
That pair of artifacts is the clearest single-location evidence of
why EWMA trades more (fading short-term mid dislocations) and why
those trades individually earn less per unit (each fade is small).

## Next change to test
Not in Phase 5. The disciplined next step is:
1. Phase 6 multi-replay robustness: re-run the Phase 5 Stage 2 and
   Stage 3 comparison across a second day's data before considering a
   promotion.
2. Investigate whether a slightly smoother configuration (e.g. α≈0.18,
   or a different seeding rule) widens the plateau to three or more
   grid points without losing the headline PnL.
3. If the plateau stays narrow on a second replay, leave `ewma_mid`
   as a registered estimator and accept that the tutorial does not
   reward the trading style this estimator unlocks.
