# Review: phase5_weighted

> STALE: This pack predates the day-aware timestamp fix for combined
> multi-day review artifacts. Use
> `outputs/review_packs/20260411T222602Z_phase5_weighted/` instead.

- **Run ID:** 20260411T185701Z_phase5_weighted
- **Generated:** 2026-04-11T18:57:01.443587+00:00
- **Commit:** cbadb43

Phase 5 incumbent pack — TOMATOES on `weighted_mid` with the Phase 3
tuned execution config (`maker_edge=1, taker_edge=1, inventory_skew=3.0,
flatten_threshold=0.7`). Companion challenger pack:
`outputs/review_packs/20260411T185706Z_phase5_ewma/`.

## Decision
**keep** (Phase 5 outcome: TOMATOES baseline remains `weighted_mid`).

## What looked good
- `charts/price_vs_fair_TOMATOES.png` shows the four-sample weighted mid
  tracking the TOMATOES mid closely, with small visible lag only when
  the mid moves several ticks between steps.
- `charts/markouts_TOMATOES.png` — all three horizons (`+1`, `+5`, `+20`)
  have positive mean markout (`+4.06`, `+3.63`, `+3.23`), the incumbent
  only trades on clearly favourable edge and each trade remains
  profitable over the 20-step horizon.
- `charts/position_over_time_TOMATOES.png` stays well inside the
  `flatten_threshold=0.7` band. `steps_near_limit=0` confirms the
  inventory discipline the current baseline is built around.
- `summary.txt` TOMATOES line: PnL +276, avg_entry_edge +0.683, 0 near
  limit, final position 6. Small trade count (16) but every trade is
  high-quality.

## What looked bad
- `charts/price_vs_fair_TOMATOES.png` on drifting stretches (e.g.
  140000-142000) shows the four-sample weighted mid lagging the mid by
  only a tick or two, which means the incumbent misses most
  short-horizon mean-reversion trades the market offers. This is
  visible as long quiet stretches with no trade markers.
- `charts/maker_taker_TOMATOES.png` shows the incumbent is 94% taker
  (83 of 88 units) with only 5 maker fills. That's ok for the Phase 3
  baseline but it tells us the maker quote layer is contributing almost
  nothing on this replay.
- Total PnL 276 is a fraction of what a more responsive estimator would
  extract (see the companion EWMA pack, PnL 1301). The incumbent is
  conservative, not optimal.

## Most important chart to inspect
`charts/price_vs_fair_TOMATOES.png` — compare the quiet 140000..142000
drifting stretch against the same window in the companion
`phase5_ewma` pack. That is the regime where the incumbent sits on its
hands.

## Next change to test
None under Phase 5 discipline. `ewma_mid` was the challenger considered
in Phase 5 and was kept out of production because it failed fit-quality
and per-trade decision-quality rules on a narrow alpha plateau. Revisit
in a later phase against a multi-day replay, or once Phase 6
robustness testing adds a second replay.
