# Phase E — Final recommendation (ASH target-position pass)

## One-screen answer

| Question | Answer |
|---|---|
| Best ASH target-position candidate found? | **D7_deep_dz** (`dead_zone d=4, α=5, cap=30, hybrid, threshold=4.0`) on the official-cadence view; L5_mild / D6_mild as softer siblings. |
| Does it beat the current best ASH leg (C_h1_alt)? | **Not conclusively.** Beats H1/Alt by **+346** on the single-day 1000-cadence view but **loses by −364** on 3-day local. One data point each; split signal. |
| Best version: maker / taker / hybrid? | **Hybrid** (with a high dead zone and a high threshold). Taker-first saturates the position; pure maker can't fire enough under the local fill model. |
| Should this family go in the next upload candidate? | **No.** Evidence is split and the robustness case is weak; no new upload bundle is justified from this pass. |
| Current shipped ASH leg? | **C_h1_alt** (`wall_mid, maker=1.5, taker=0.5, skew=4.0, flatten=0.7, h=48`) stays the reference. |
| Current Promoted / H1 / Alt / F5 configs? | **Unchanged.** No shipped engine factory was modified by this pass. |

## 1. Headline numbers

(ASH-only PnL. PEPPER held at Promoted leg in every row.)

| Candidate | Off-cadence ASH | Δ vs C_h1_alt (off) | Off near-limit / 1 000 | 3-day local ASH | Δ vs C_h1_alt (3-day) | 3-day near-limit / 30 000 | Composite score |
|---|---:|---:|---:|---:|---:|---:|---:|
| C_promoted (control)         |   +357 | +145 |   0 | +6 447 | −1 300 |     4 | +481.6 |
| C_h1_alt (control, current best) | +212 | 0    |   0 | +7 747 | 0      |   110 | +355.8 |
| C_baseline (control)         |   +248 | +36  |   0 | +7 301 | −446   |   100 | +385.9 |
| **D7_deep_dz (target family)** | **+558** | **+346** | **0** | +7 383 | −364 | 1 001 | +683.2 |
| L5_mild (target family)      |   +523 | +311 |   0 | +6 751 | −996   |     0 | +640.5 |
| D6_mild (target family)      |   +514 | +302 |   0 | +6 459 | −1 288 |     0 | +625.2 |
| L1/L2/L3/D1/D2/D4/D5/V1/V2 (saturated) | +605 | +393 | **334** | +7 966 .. +8 252 | +219 .. +505 | 5 995 .. 11 556 | +404..+410 |
| W1_wall_dz1 (wall-mean)      |   +38  | −174 |   0 | +8 735 | +988   | 1 596 | +203.6 |
| W2_wall_dz0 (wall-mean)      |   +98  | −114 |   0 | +8 453 | +706   |   405 | +259.5 |
| L4_maker / D3_maker (maker-only) | 0 | −212 | 0 | 8 / 12 | ≈−7 740 | 0 | 0.2 |

Composite score formula (documented in `ash_candidates.md`):

```
score = off_ash
      + 0.20 * min(off_b0..b3)
      + 0.02 * local_ash
      - 0.5  * |off_final_pos|
      - 1.0  * off_near_limit
```

## 2. Why **not** promote the target family for upload

1. **Split signal between the two views.** The mild target variants
   (D6 / D7 / L5) beat C_h1_alt on the 1 000-cadence view by
   +300–346 but lose by −364 to −1 288 on the 3-day local view.
   With one official data point, we cannot tell which view extrapolates.
2. **Negative short-horizon markouts.** Every target-family winner
   shows markouts of roughly **−4 / −3 / −2** at t+1, t+5, t+20.
   Realized PnL is positive because the mean reversion pays off over
   the whole horizon, but we are systematically selling into rising
   prices and buying into falling ones on the short edge — the
   opposite of the positive +1.7 / +1.6 / +3.0 markouts C_h1_alt
   earns. If the official environment's fill quality is sensitive
   to the short-horizon markout sign, the projected official PnL
   advantage could reverse.
3. **Fill-model sensitivity.** `C_h1_alt` earns +7 747 on 3-day local
   from **757 taker fills and 9 maker fills**. On the official day
   the same leg earns +983 from **56 maker and 25 taker fills**.
   The simulator's fill model is aggressively taker-biased relative
   to the official environment; an extra taker trade is nearly free
   in local but costs a half-spread in live. A strategy whose local
   advantage comes from additional taker trades is **not** a safe
   bet for the official day. The target-position family fits this
   description (D4_taker captures +8 252 local via 470 taker trades
   vs C_h1_alt's +7 747 via the same taker-heavy mix — but pays with
   7 852 near-limit steps).
4. **Saturation in the high-α variants.** Nine of thirteen new
   candidates hit **334 / 1 000 near-limit snapshots on the
   1 000-cadence view** — roughly **33 %** pinned. The flatten
   valve opens only after the position has already blown past the
   threshold in one taker step. That is ~15× more tail-risk than
   Alt's already-flagged 2.2 % near-limit exposure on the official
   day. We cannot propose a variant with this failure mode for
   upload.
5. **Wall-mean variants are structurally degenerate.** W1 / W2 use
   `target_mean_source = "fair"` with `wall_mid`, which makes the
   residual near-zero by construction. They score the way they do
   because the target logic rarely engages — they are effectively
   passive market-makers with wider quote edges, not a test of the
   target-position hypothesis.

## 3. What to keep from this pass

- **`AshTargetPositionStrategy`** is a clean, research-only
  implementation of target inventory as a function of residual. It
  is **not** registered in the live `STRATEGY_REGISTRY` and is not
  in `LIVE_MODULE_ORDER`, so no shipped bundle sees it. Adding a
  future candidate later only requires flipping the runner.
- **Three shapes, three exec styles, two mean sources** is enough
  structure to decide *qualitatively* that the family is not ready.
  Adding more candidates on the anchor-mean / high-α axis is a
  waste of budget; any further work should either change the
  mechanism (see §6) or run an official check of D7 / L5 / D6.
- **Controls reproduce known ranking on 3-day local**
  (`C_h1_alt +7 747 > C_baseline +7 301 > C_promoted +6 447`) so
  the simulator plumbing is validated.

## 4. Execution-style verdict

For the target-position mechanism as specified here:

- **Taker-first** — best raw PnL on 3-day local, but *all* variants
  saturate at 334 near-limit on cadence view. Tail-risk catastrophic.
  Not usable.
- **Maker-first** — fires zero fills on cadence view and ~10 fills
  on 3-day local because the simulator's passive fill path is very
  thin on ASH. The logic could in principle beat H1/Alt with proper
  passive fills, but we cannot test that here.
- **Hybrid (with high dead zone and high threshold)** — the only
  style that produces usable *and* bounded behavior. D7_deep_dz
  (threshold=4.0, d=4) hits 0 near-limit on cadence view. This is
  the only target-family cluster worth any further attention.

## 5. Action items (none taken)

Per the scope rules of this pass:

- **No engine factory changes.** `round1_promoted_engine_config`,
  `round1_h1_engine_config`, `round1_alt_engine_config`,
  `round1_f5_engine_config`, and `round1_baseline_engine_config` are
  unchanged. `git diff src/core/config.py` is empty.
- **No submission bundle change.** No new `.py` was built in
  `outputs/submissions/`. No `export_round1_submission.py` variant
  was added.
- **Research surface isolated.**
  - `src/strategies/ash_target_position.py` — new, research-only
  - `tests/test_ash_target_position.py` — 15 tests, all green
  - `outputs/round_1/ash_target/run_ash_target.py` — runner
  - `outputs/round_1/ash_target/{controls.md, ash_target_memo.md,
    ash_candidates.{csv,md}, final_recommendation.md}` — artifacts

  The full test suite (452 tests) is green.
- **No upload.** Current IMC shortlist stays:
  A. Promoted (shipped)
  B. H1 hybrid (shipped, current best at +2 780)
  C. F5 `buy1.5_sell3` + Alt ASH (already proposed in the fastsearch
     pass; independent of this ASH research)

## 6. What remains uncertain

1. **Whether the target-position mechanism would beat C_h1_alt on a
   second official day.** The only way to resolve the split signal
   between the 1 000-cadence and 3-day local views is to run one of
   D6 / D7 / L5 through the official environment and read the real
   result. Budgeting this against the PEPPER-side F5 upload is a
   next-round decision; the ASH family is not a strong enough
   candidate to claim an upload slot today.
2. **Whether a different target-position definition avoids the
   saturation + markout drag.** The current shape is simple enough
   to be diagnostic — what we learned is that a discrete
   (residual, target) map driven off a fixed anchor is too blunt for
   ASH's 1–1.4 tick residual dispersion. A future pass could try:
   - anchor = EWMA(mid) instead of the hard 10 000
   - target that clips to `flatten_threshold × limit` rather than a
     separate `cap`, so flatten engages *before* a single-step
     overshoot
   - target that scales with *realized* residual volatility (σ-
     aware) rather than a fixed α
   None of those are in scope for this pass.
3. **Whether the observed pattern — target family wins on sparse
   sampling, loses on dense sampling — is a fill-model artefact or
   a real effect.** The strongest signal is that the official
   environment samples at 1 per 1 000 timestamps, which matches the
   sparse view; but we only have one official data point to
   calibrate with.
4. **Maker-only behavior.** We cannot assess it without denser
   passive fills. The one positive local number on a maker-only leg
   (L4 = +8 over 30 000 steps) is indistinguishable from noise.

## 7. Engine surface added by this pass

Research-only, none of it ships:

```
src/strategies/ash_target_position.py         — new file (~220 lines)
tests/test_ash_target_position.py             — 15 unit tests

outputs/round_1/ash_target/run_ash_target.py  — runner
outputs/round_1/ash_target/controls.md        — Phase A
outputs/round_1/ash_target/ash_target_memo.md — Phase B
outputs/round_1/ash_target/ash_candidates.csv — Phase D / E
outputs/round_1/ash_target/ash_candidates.md  — Phase D / E
outputs/round_1/ash_target/final_recommendation.md — Phase E
```

Zero changes to:

- `src/core/config.py` (no new `ProductConfig` fields)
- `src/core/signals.py`
- `src/core/execution.py`
- `src/strategies/__init__.py` (no new registry entry)
- `src/scripts/export_submission.py` (no `LIVE_MODULE_ORDER` change)
- Any `round1_*_engine_config` factory
- Any submission bundle under `outputs/submissions/`

Full test suite: **452 passed**.
