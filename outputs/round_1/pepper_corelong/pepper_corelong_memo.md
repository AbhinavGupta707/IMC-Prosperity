# PEPPER mechanism memo — why core-long + residual overlay

One-page memo. Rationale for the family of strategies tested in this
pass. Not a dossier.

## What PEPPER looks like

PEPPER (INTARIAN_PEPPER_ROOT) is a **drift asset with book noise
around the drift**, not a mean-reverting asset.

Observable facts (dossier + local replay + 1 official day):

1. **Upward drift of ~+0.1 per timestamp** (i.e. ~+1 000 price units
   per 10 000-tick day; ~+0.001 per tick on the fair-value scale).
   The drift runs across day boundaries: the memory at day-start is
   seeded from the day-end mid of the previous day, and the observed
   drift is approximately continuous across days (see
   `outputs/round_1/research/intarian_pepper_root_dossier.md`).
2. **Spread of 11–16 ticks** around the drift fair, with a two-sided
   book. Roughly symmetric noise around the `linear_drift` fair.
3. **No observed reversal** over any bucket on the one official day
   or on the three local training days. The drift slope fitted by
   `linear_drift` is stable.
4. **Buy-and-hold at +50 scored +4 559 PEPPER PnL** on the official
   day (see `controls.md` §A1). That is ~2–3× the best
   market-making PEPPER result. The delta between buy-and-hold and
   the best MM variant is the slice of PnL that the MM variants
   forfeit by NOT staying long.

## Why symmetric mean-reversion is wrong for this product

Every MM variant we have shipped so far uses symmetric inventory
skew (`position_ratio × inventory_skew`) as its primary position
control. The model implicitly assumes **position = 0 is the
preferred rest state**. On a drifting asset with no reversal, this
preference is actively harmful in two ways:

1. **It penalises the correct position.** The correct rest state on
   a drift-up day is `+N` long, not `0`. Symmetric skew treats `+30`
   as "needs to be trimmed," producing sell quotes that leak drift
   PnL.

2. **It creates unintended shorting.** When price runs up, symmetric
   skew plus the default taker edges crosses on the sell side. On
   the official day every MM variant spent time at −8 or deeper
   (baseline hit −17). Every unit of short on a rising drift is a
   direct loss.

Phase-9 F5 partially worked around (2) by **widening the sell edge
asymmetrically** (`taker_edge_sell = 3.0`). That moved the needle
from +1 797 to +2 135 PEPPER PnL. F5 is a first-order asymmetric
fix applied **inside the symmetric chassis**. It still treats
position = 0 as the anchor.

## What the core-long + overlay family does differently

It replaces the "position = 0 is home" chassis with:

```
target_position(t) = base_long + overlay(residual(t))
     residual(t)   = price(t) − drift_fair(t)
     drift_fair    = linear_drift estimator   (unchanged)
```

Behavioural properties:

- **Base long ≥ 0.** The rest state is long, not flat. Matches the
  asset's drift direction.
- **Asymmetric overlay.** Residual-below-fair opens the position
  above base long (easy); residual-above-fair trims below base long
  (harder / requires a bigger residual).
- **Position floor ≥ 0.** The bot never flips net short on a mild
  positive residual. It only surrenders long capacity, not takes
  on a short position.
- **Rate-limited adjustment.** The bot moves toward its target at
  most `step` units per tick, not instantly. This is important
  because the official cadence (1000 ticks across a day)
  overstates how fast a real bot can rotate — but the rate-limit
  is primarily about **avoiding paying the whole spread on every
  signal tick** in the simulator.
- **Drift capture comes from base_long; residual harvesting is
  additive.** A base_long of +30 with no overlay gets you ~60% of
  the buy-and-hold drift pickup. Adding a competent overlay layers
  a second source of PnL on top.

## What's still uncertain

1. **Slope stability.** If a future day's drift is flat or
   reversing, a base_long of +30 will bleed directly. Every PnL
   number in this pass was measured on data where the drift held.
   The family's **worst-case day** is a flat or reversing day; it
   is strictly worse than symmetric MM on that day.

2. **Official fill model vs local simulator.** The fastsearch
   (Phase-9) showed a local-to-official ratio of roughly 10× for
   promoted / alt, meaning a local +90 000 PnL landed at ~+1 800
   officially. This ratio is approximate and depends on
   cadence and execution assumptions. I report local numbers
   for ranking, and a projected-official number that is an
   order-of-magnitude guide only.

3. **Maker/taker mix on the official environment.** The local
   simulator emits aggressive fills readily at tight taker edges.
   The official environment may fill maker quotes at different
   rates (this is known to diverge from local — see CLAUDE.md
   Evidence Calibration).

4. **The optimal `base_long` depends on the drift magnitude.**
   We do not know whether Round-2 or an unseen Round-1 day will
   have the same slope. A small-to-medium `base_long` is a more
   defensive choice; a large one pushes closer to buy-and-hold
   upside but imports buy-and-hold's downside on a non-drift day.

5. **Regime-break guard is deferred.** The user marked this as
   optional ("do not make this a giant subproject"). If the
   strategy family passes local ranking we can revisit; this pass
   does not implement it.

## What this pass is NOT

- Not a new fair-value method. `linear_drift` is reused as-is.
- Not a new ProductConfig surface. The strategy is passed its
  parameters via a dataclass inside the research runner, same
  pattern as `src/strategies/ash_target_position.py`.
- Not a submission export. No bundle is built or uploaded.
- Not a broad new optimization cycle. One family. ~25 candidates.
