# Phase B — ASH mechanism memo (target-position pass)

Narrow focus memo for this pass only. Complements (but does not
supersede) the deeper `outputs/round_1/fastsearch/ash_memo.md` and
`outputs/round_1/research/ash_coated_osmium_dossier.md`.

## What ASH looks like on the tape

Anchored oscillator around **~10 000**.

- **Spread:** stable ~16 ticks (wall-to-wall ≈ 16; inside spread ≈ 4–6).
- **Drift:** effectively zero on the one official day (mid moves ±~20
  over 100k timestamps with no directional bias).
- **Residual dispersion:**
  `residual_std(ewma_mid) ≈ 1.04`, `residual_std(wall_mid) ≈ 1.37` on
  the official day
  (`outputs/round_1/official_results/analysis/bucket_breakdown.md`).
- **Book depth:** always 1–2 layers each side visible; the wall level
  is visibly stable and tends to sit a tick or two inside the true
  fair value for long stretches.
- **Trade density:** ~22 filled trades per 25 000-timestamp bucket in
  C_baseline / C_h1_alt, ~20 for C_promoted — ASH is quiet but steady.

## Is ASH's edge passive spread capture, mean reversion, or hybrid?

**Predominantly passive spread capture. Mean-reversion mechanism is
real but operates at 1–3 ticks, not 10.**

Evidence:

- **Maker dominates the trade mix.** Official-day maker/taker split is
  ~56 / 25 on C_baseline and C_h1_alt. Pure spread capture — no
  directional bet — already produces ~82 % of the PnL.
- **`maker_edge` is the primary PnL lever**, not `fair_value_method`:
  the stage-A wall_mid sweep shows `taker=0.5` beats `taker=1.0` by
  ~+440 local PnL, and `maker=1.5 + taker=0.5` is the all-time-best
  combination on the official day. By contrast, swapping
  `ewma_mid → wall_mid` (fixing edges) improves PnL mainly because the
  wall-based mid sits differently relative to the 16-tick spread,
  letting the maker edge bind at more book levels.
- **Residual volatility is low.** With `residual_std ≈ 1.0–1.4` and a
  spread of ~16 ticks, the "price > fair → go short" signal only
  amounts to ~1–2 ticks of information per step. The actionable
  residual is **small relative to the spread**, which is why a
  target-position strategy should use a **dead zone** rather than
  firing on every ±0.5 tick residual.
- **Residual mean ≈ 0** for every estimator (within ±0.06). This is
  the mean-reversion signature: price returns to fair. But the
  *magnitude* of a typical excursion (1–1.4 ticks) is smaller than
  the maker edge widths we already use (1.0–1.5 ticks), so the passive
  quote already earns the mean-reversion premium without needing
  explicit target inventory — **as long as** the quote fires.

## Spread structure → execution style

**Maker-first is the default answer for ASH.** The 16-tick stable
spread is tailor-made for a patient maker.

- `taker=1.0` is too aggressive: it trades 650 times on local vs 766
  at `taker=0.5`, but ends with worse markouts and less PnL — the
  marginal taker trade in ASH is often edge-neutral at best.
- `taker=0.25` is too conservative: it under-fires the maker in the
  last bucket on the official day (C_promoted loses +227 vs C_h1_alt
  in bucket 3 with an identical FV method mechanism).
- The sweet spot for a pure market-maker is `taker=0.5, maker=1.5`
  (= C_h1_alt), which is what the current best leg uses.

For a **target-position** strategy this implies:

- **Default maker-first** — post quotes, pull toward target via the
  passive fills when the book walks toward you.
- **Taker only on strong dislocations** — if `|price − fair| ≥ ~2–3
  ticks`, a taker step saves waiting a long time for the quote to
  fill. Below that threshold the expected gain is smaller than the
  half-spread paid.
- A pure **taker-first target-position** is expected to do worse than
  C_h1_alt, because you pay the half-spread on every rebalance and
  the mean-reversion signal is only 1–1.4 ticks tall.

## Is one side stronger?

**Slightly long-biased in the data we have, but not meaningfully so.**

- End-of-day positions across variants: baseline −12, promoted −25,
  h1_alt −14 on the official day. Net short across runs.
- Bucket PnL is roughly symmetric — no single bucket dominates.
- There is no structural reason (news, drift) to expect one side to
  pay more than the other, so the default should be
  **side-symmetric target** and **side asymmetry only tested if a
  clear signal emerges from the candidates**. This memo does *not*
  propose asymmetric ASH targets.

## What is the current best ASH leg?

**C_h1_alt** (`wall_mid, maker=1.5, taker=0.5, skew=4.0, flatten=0.7,
history=48`) — PnL **+982.81** on the official day, **+7 747** on
3-day local, zero near-limit snapshots.

This is the bar for the target-position family.

## What remains uncertain

1. **One-day official sample.** The C_h1_alt advantage over C_baseline
   is only +150 on one day; on 3-day local the wall_mid stage-A sweep
   ranks `maker=1.5/taker=0.5` #1 and `maker=1.0/taker=0.5` #2 within
   +51 of each other. A target-position candidate that beats C_h1_alt
   by <100 on one day is not a confirmed win.
2. **Whether the `ewma_mid` under-fire on late-day ASH (−227 vs
   wall_mid in bucket 3) reflects a persistent pattern** or was a
   one-day artefact. The target-position family cannot answer this —
   but it *can* guard against it by maintaining symmetric quotes even
   when residual is small.
3. **Whether explicit target inventory beats implicit-via-skew.** The
   existing `inventory_skew=4.0` already pulls the bot toward flat as
   position grows. A target-position that simply shadows this
   behavior will add nothing. The target-position family must either
   (a) engage mean-reversion *before* `inventory_skew` kicks in
   (dead-zone + small α) or (b) engage late reversion harder than
   the existing flatten/skew machinery (convex).
4. **Fair value choice for the residual.** Using `anchor_price=10 000`
   is the cleanest "mean" for ASH because it is stable across days
   and is what the oscillator is visibly anchored to. `wall_mid` is
   available as a local-fair-value *reference* (what the book
   currently shows) but **should not** be used as the "mean" because
   it moves with the book — we would be cancelling the signal we
   want to trade on. Two `wall_mid`-based candidates (W1/W2) are
   included below purely as a sanity check that anchor is better.

## ASH policy for this pass

- **Freeze PEPPER at Promoted** in every candidate — this pass is
  ASH-only.
- **Control set: C_baseline, C_promoted, C_h1_alt** — unchanged
  engine legs, evaluated on the same two views as the new family so
  the comparison is apples-to-apples.
- **Target-position family**: 3 shapes (linear, dead-zone, convex) ×
  a small parameter grid, 3 execution styles, 2 mean choices. 13
  candidates. See the runner at `run_ash_target.py`.
- **Do not re-open `maker_edge` or `taker_edge` width tuning** beyond
  one wider-maker candidate (D5) to test the interaction with the
  dead zone. We already know `maker=1.5 / taker=0.5` is the best
  pure-MM envelope; any improvement from the target-position family
  has to come from *what orders we submit in which state*, not from
  re-discovering the same edge widths.
