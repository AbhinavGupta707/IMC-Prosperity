# PEPPER mechanism memo (v2) — core-long + opening + overlay

One-page update to the v1 memo. What's the same, what's new, and
why the new layer (opening acquisition) is the single most important
addition.

## What PEPPER is

**A drift asset with book noise around the drift — NOT a mean-
reverting asset.**

Observable on the three local days and the one official day:

1. **Upward drift ≈ +0.1 per tick.** ~+1 000 price units per 10 000
   ticks; continuous across day boundaries. `linear_drift` estimator
   is a good fit once it has enough samples.
2. **Spread 11–16 ticks.** Two-sided book with roughly symmetric noise
   around the drift fair.
3. **No reversal** on any bucket of any day we've observed.
4. **Buy-and-hold at +50 scored +4 559 PEPPER PnL officially** — ~2.1×
   the best market-making result. The MM-vs-hold gap is the slice of
   PnL we forfeit by not staying long.

## Why symmetric mean-reversion is the wrong chassis

Every shipped MM variant uses `position_ratio × inventory_skew` —
which implicitly says **position = 0 is home**. On an asset that
only drifts up, that anchor:

1. **Penalises the correct position.** Correct rest state is +N long;
   symmetric skew treats +30 as "needs trimming" and emits sells
   that leak drift PnL.
2. **Generates unintended shorts.** When price rises, symmetric skew
   + default taker edges cross the sell side. On the official day,
   baseline hit −17; promoted / alt / H1 / F5 each dipped to −8.

F5 papered over (2) by widening the sell edge asymmetrically
(`taker_edge_sell=3.0`), moving PEPPER PnL from +1 797 to +2 135.
That is a **first-order asymmetric fix applied inside the symmetric
chassis** — it still treats position=0 as the anchor.

## What the v1 core-long + overlay family did

```
target_position(t) = base_long + overlay(residual(t))
     residual(t)   = price(t) − drift_fair(t)
     drift_fair    = linear_drift estimator (unchanged)
```

- Rest state is long (base_long ≥ 0) — matches the drift direction.
- Overlay is asymmetric: add above base on negative residual (easy),
  trim below base on positive residual (harder).
- `floor ≥ 0` prevents flipping net short on a mild positive residual.
- Adjustment rate-limited by `step` per tick.
- `linear_drift` reused verbatim — no new fair-value method.

**v1 result:** `B_base50` beat F5 locally by ~5 % on PEPPER PnL. But
v1 itself flagged the decisive issue: **v1 did not close the early-
day gap.** First-25k PEPPER PnL was +111 for every MM and v1 core-
long variant; only buy-and-hold captured the +814 early drift PnL.

v1's conclusion: *"The only way to meaningfully fix the early-day gap
is a tick-0 seed — take an aggressive taker intent at t=0 regardless
of estimator warm-up. That's a different family."*

## What v2 adds

**The opening-acquisition layer.** v2 extends the target:

```
target_position(t) =
    opening_core(t)          # t ≤ open_window: target = open_seed_size
  + persistent_core          # else: target = base_long
  + tactical_overlay(residual(t))
  − protection_adjustment    # optional, Layer 5
```

The opening_core branch is not additive — it **overrides** the
persistent + overlay target for the duration of `open_window`. Inside
the window:

- Target is pinned at `min(open_seed_size, effective_ceiling)`.
- Taker is **always eligible** regardless of residual magnitude or
  `exec_style` — this is the point of the seed: acquire without
  waiting for the estimator.
- If `open_no_short = True` (the safe default), all sell-side intents
  are suppressed until the window closes. This protects the seed
  from residual-overlay noise while the estimator is still warm-
  ing up.

The rate-limit `step` still applies, so a large `open_seed_size` with
a small `step` still takes several ticks to fill. v2 treats the pair
`(open_seed_size, open_window)` as the actual tunable — not a hard
tick-0 commit like buy-and-hold.

**Why this is the right shape:**

1. The problem is a signal-timing gap, not a parameter-tuning gap.
   v1 proved no combination of `base_long`, `add_thresh`, `trim_thresh`,
   `step`, or `exec_style` recovers the first-25k edge.
2. Buy-and-hold ships the full +50 at tick 0 and ignores the rest of
   the day. That captures the early drift but takes no spread capture
   and has extreme tail risk on a reversing day.
3. A parametrised opening seed — "commit `seed` at `tick ≤ window`,
   then trade around it normally" — is the continuous interpolation
   between `B_base50` (no seed) and `buy-and-hold` (seed = limit, no
   overlay). The whole 5-point interpolation is in scope for Layer 1.

**Behavioural properties in one sentence each:**

- **Opening seed.** Captures early drift without waiting for estimator.
- **Persistent core.** Captures mid/late drift at a capped inventory.
- **Asymmetric overlay.** Harvests residual dips and shaves rally peaks.
- **Floor.** Prevents net-short from transient positive residuals.
- **Step.** Smooths per-tick adjustment; avoids paying full spread on
  every signal tick in the simulator.

## What v2 is NOT

- Not a new fair-value method. `linear_drift` still.
- Not a new ProductConfig surface. `CoreLongParams` stays outside the
  live engine config — same pattern as `ash_target_position`.
- Not a new submission bundle. No upload, no promoted-config mutation.
- Not a broad optimisation cycle. One family; ~125 candidate-runs
  total via layered search (not a ~26k brute-force cross-product).

## What's still uncertain

1. **Drift specificity.** The whole family assumes the observed +0.1-
   per-tick drift holds. Every metric is on data where it did. On a
   flat / reversing day, `base_long + seed` is an unhedged directional
   bet. `C_corelong_no_open` (seed=0 and overlay disabled) is the
   defensive floor; v1 showed it never shorts on any of the 3 local
   days.
2. **Official-to-local fill ratio for seeded candidates.** v1's 10-11×
   calibration is based on continuous MM fills, not a tick-0 seed.
   Seeded fills may have a different ratio if the official environment
   clears the top of the book differently than the local simulator.
   Flagged; will note in v2 shortlist.
3. **Ramp-in cost below the seed target.** `step=8` with `open_seed_size=50`
   takes 7 ticks at 100-tick cadence to fill from 0 to 50 (≈700 ticks
   = 7 % of session). A large `step` speeds acquisition but grows the
   per-tick taker-cross cost. Layer 4 explores this.
4. **Maker-only execution under-fills locally.** v1 showed the local
   simulator does not match maker quotes inside the book reliably.
   Same limitation in v2 — the maker-only Layer 4 candidate cannot be
   reliably evaluated locally. Flagged as a simulator limitation, not
   a strategy verdict.
5. **Overlay contribution is small at official cadence.** v1 showed 9
   of 22 overlay candidates produced bit-identical results because
   the residual never left the dead zone at the (mis-described)
   proxy cadence. v2 uses the **corrected 100-tick cadence** proxy,
   which has 10× more samples per ms of market time — the overlay
   should fire more often. But if it still barely contributes under
   the corrected cadence, v2 will report that plainly rather than
   hiding it in the score.

## The single biggest v2 uncertainty

**Does an opening seed that doesn't commit to the full 50 close enough
of the buy-and-hold gap to be worth the early capacity?** If the
answer at the corrected cadence is "most of it" — then v2 has the
shortlist it wants. If "not enough" — the answer is either (a) seed
is fine but the remaining gap is execution-model driven (fill model
divergence) and not a strategy problem, or (b) we need to revisit
the seed's post-window behavior. Both outcomes are reportable.
