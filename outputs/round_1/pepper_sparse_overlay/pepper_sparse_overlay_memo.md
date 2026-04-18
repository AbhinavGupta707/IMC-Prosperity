# PEPPER mechanism memo — near-buy-and-hold + sparse overlay

One-page memo. Sharper than the v2 memo because the evidence is
sharper.

## What the official numbers now say

After 6 uploaded variants at the true `position_limit=80`:

| Variant | PEPPER PnL (official) | PEPPER family |
|---|---:|---|
| promoted     | +1 797 | symmetric MM |
| alt          | +2 057 | symmetric MM, looser flatten |
| f5           | +2 135 | asymmetric-taker MM |
| V2_clean     | +5 426 | opening-seeded core-long, base=50 |
| **buy_hold_80** | **+7 286** | pure directional, pin +80 at tick 0 |

**Two facts dominate the picture:**

1. **buy-hold is almost perfectly linear in PnL vs time** after the
   first ~5 000 ticks (R² = 1.000000 on the hold phase, slope
   +0.08 per tick = +80 units × +0.001 per tick drift in price units).
   The whole day is drift carry; the only cost is the one-time
   ~706-unit spread pay at the open.
2. **V2_clean's PEPPER PnL is +5 426, buy-hold's is +7 286.** Gap is
   **−1 860 PEPPER PnL** and breaks down as:
   - ~−387 in bucket 0 (seed=60, not 80)
   - ~−456 / −320 in buckets 1 / 2 (trim/rebuy cycles)
   - **~−697 in bucket 3** (finished at +50, not +80 — 30 units of
     carry surrendered for the last quarter)

## Why V2_clean gives up too much carry

V2_clean was designed as a balanced core-long at `base_long=50`,
with an overlay that buys below fair and trims above. That made
sense when we didn't know how far buy-hold would outperform MM
variants. Now we do.

Problems this family has:

1. **The default rest state is +50, not +80.** When residual returns
   to the dead zone after any trim or reload, target snaps back to
   `base_long=50`. 30 units of long exposure × ~0.001 drift per tick
   × whatever fraction of the session spent near target = a real
   fraction of the gap.
2. **The overlay's add branch can't push above 80.** It's clipped at
   the ceiling. So when price is below fair, target IS 80, but the
   rest of the time target is 50. The overlay helps, but the base
   is the dominant effect.
3. **Trim fires too easily.** `trim_thresh=5.0` with `trim_gain=1.0`
   means a residual of +10 pulls target to 45 (below floor=0 so
   clipped at 0). The trim side is the mechanism by which V2_clean
   ends the day below +80.

## What the next family does differently

**Pin the default state at +80. Make trims sparse and small. Let
reloads back to +80 happen automatically.**

```
target_position =
    opening_seed(t)                                  # t <= open_window
  | clip(80 + trim_overlay(residual), floor, 80)     # otherwise
      trim_overlay(r) = 0                       if r <= trim_thresh
                      = -trim_gain * (r - trim_thresh)  if r > trim_thresh
```

Behavioural properties:

- **Default target = 80.** Any time price is not meaningfully above
  fair, target is 80 and the bot wants to be at +80.
- **Trims are sparse (trim_thresh ∈ {6, 8, 10, 12})** — roughly the
  spread width. Price has to be materially rich for a trim to fire
  at all.
- **Trims are small (trim_gain ∈ {1.0, 2.0, 3.0})** — even when a
  trim fires, it pulls target down by a small amount (e.g. a residual
  of +10 with `trim_thresh=8, trim_gain=2.0` pulls target from 80 to
  76, not to 50).
- **Floor is high (floor ∈ {40..70})** — even a huge positive
  residual can't pull the bot below the floor.
- **Reloads are automatic.** As soon as residual falls below
  `trim_thresh`, target snaps back to 80 and the `step` + `exec_style`
  combination drives a fast re-accumulation toward the ceiling.
- **The opening seed reaches +80 (or very close).** `open_seed_size ∈
  {60..80}` with `open_window ∈ {0..2000}` — faster and deeper than
  V2_clean's seed=60.
- **`open_no_short=True`** on every candidate. No short exposure.

## What this family does NOT try to do

- It does NOT try to beat buy_hold_80 by very much. In the best case,
  a trim-on-rich-price discipline captures a small edge on top of
  pure carry; in the worst case it matches buy_hold and just justifies
  the execution complexity.
- It does NOT protect against a reversing day. Same exposure as
  buy-hold; same tail risk.
- It does NOT try to close the last ~700 first-bucket spread cost.
  That's a structural cross-cost; only a smarter opening execution
  can close it, not a different overlay.
- It does NOT explore new fair-value methods. `linear_drift`
  unchanged.

## Why buy_hold_80 is now the reference, not the ceiling

Historically v1 and v2 treated buy_hold as an "upper bound that we
could approach but never match" because it ignored all
spread-capture edge. The new numbers show the spread-capture edge on
PEPPER is dominated by the drift carry: MM variants buy the spread
but sell the carry. The correct frame is:

> **Buy_hold_80 is the reference case. Any variant that doesn't
> capture at least its carry is unnecessarily complex.**

The task is no longer "get most of buy_hold_80's PnL" — V2_clean
already captured 75 % of it. The task is "stay as close to
buy_hold_80's PnL as possible **while** adding a small trim-on-rich
edge, **and** preserving the optionality of recovering from an
unexpected reversal."

## What's still uncertain

1. **Drift specificity.** Same as v2 memo: all data is on drift-up
   days. A reversing day penalises any near-+80 strategy by +80 ×
   the reversed magnitude. This family has the same exposure as
   buy-hold.
2. **Trim-on-rich edge is small.** On the one official day we have,
   price had no meaningful excursions above drift-fair that persisted
   long enough for a useful trim-then-reload cycle. A sparse-overlay
   family might match buy-hold but not beat it on this specific
   data. The edge shows up on days where price briefly spikes above
   drift before resuming the ascent — which we haven't observed yet.
3. **Trim floor vs `max_aggressive_size`.** V2_clean runs with
   `max_aggressive_size=20` (bumped from the shipped 8). Trims of
   15 units in one tick are only possible with that bump. Preserved
   here for the same reason.
4. **Overlap with buy_hold_80 at the extreme.** The limiting case of
   this family is `trim_thresh=∞` (trim never fires) + `floor=80` —
   which is byte-identical behavior to buy_hold_80. The pass should
   detect that degenerate and not pretend it's an "improved variant".

## The single biggest question this pass will answer

**Can an opening-seeded +80 hold with a sparse trim-on-rich edge
beat buy_hold_80 on the proxy at all?**

If the answer is a clear +200 to +500 PEPPER PnL over buy-hold, the
family justifies a calibration upload. If it's +0 to +100, the
correct recommendation is to upload a plain `base_long=80` variant
with no overlay (functionally equivalent to buy_hold_80 but
expressed through the core-long strategy for future optionality).
If it's negative, stay with buy_hold_80 as the upload.
