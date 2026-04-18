# PEPPER core-long + opening + overlay v2 — final recommendation

One-screen answer, then six answers to the prompt's final questions,
then uncertainty flags and scope-compliance check.

## One-screen answer

| Question | Answer |
|---|---|
| Best core-long + overlay candidate? | **`V2_clean`** (base_long=50, add_thresh=3.0, trim_thresh=5.0, add_gain=5.0, trim_gain=1.0, step=8, exec=hybrid, **opening seed=60, window=1000, no_short=True**). Cleanest combination of proxy PnL, first-half capture, and near-limit discipline. |
| Does it clearly beat current PEPPER references locally? | **Yes, on both views and by a material margin.** V2_clean PEPPER proxy +5 472.5 vs F5 +3 911.5 (+40 %); V2_clean first-25k PEPPER +1 204 vs F5 +302 (+298 %). Projected official lift **≈ +900 to +2 080 PEPPER PnL**, well outside single-day noise. |
| Does it fix the early-day weakness? | **Yes, substantially.** v1 could not close the first-25k gap; V2_clean captures **76 %** of buyhold's first-25k edge; V2_upside captures **88 %**. This is the decisive change vs v1. |
| What ASH leg should it be paired with? | The **frozen H1 / F5 / Alt `wall_mid` leg** (`taker=0.5, maker=1.5, skew=4.0, flat=0.7, h=48`). No ASH dimension was explored; that is the input contract of this pass. |
| Prepare a new upload candidate now? | **Yes — but only after one calibration-confirmation upload.** The projected lift is outside noise this time, but the 1.3×-to-1.8× calibration is a 4-point extrapolation and seeded candidates may behave differently. See §5. |
| What remains uncertain? | See §6. Biggest: (i) calibration of a seeded candidate vs MM reference; (ii) drift specificity; (iii) whether the tick-0 fill profile matches the official environment. |

## 1. Best core-long + overlay candidate

**`V2_clean`** is the answer.

```python
CoreLongParams(
    base_long=50,
    add_thresh=3.0,
    trim_thresh=5.0,
    add_gain=5.0,
    trim_gain=1.0,
    floor=0,
    ceiling=80,
    step=8,
    exec_style="hybrid",
    hybrid_threshold=2.0,
    # --- opening (v2) ---
    open_seed_size=60,
    open_window=1000,
    open_no_short=True,
)
```

Paired with the H1/F5/Alt `wall_mid` ASH leg, routed through
`PepperCoreLongStrategy` (research-only; NOT in `STRATEGY_REGISTRY`).

Evidence (raw metrics — primary):

| Metric | C_promoted | C_f5 | **V2_clean** | V2_upside | C_buyhold (ref) |
|---|---:|---:|---:|---:|---:|
| PEPPER proxy PnL     | +2 394.0  | +3 911.5 | **+5 472.5** | +6 212.0 | +7 279.0 |
| PEPPER first-25k     | +130.0    | +302.0   | **+1 204.0** | +1 396.0 | +1 593.5 |
| PEPPER first-50k     | +919.5    | +1 501.0 | **+2 758.0** | +3 161.5 | +3 473.5 |
| Bucket-3 PEPPER      | +480.0    | +948.5   | +1 357.0     | +1 230.5 | +1 880.0 |
| Near-limit /1000     | 0         | 144      | **373**      | 568      | 999 |
| Max long (proxy)     | +45       | +62      | +64          | +64      | +80 |
| First-half short (proxy) | −6    | 0        | **0**        | 0        | 0 |

**Why V2_clean, not V2_upside, as the single best:** V2_upside adds
~+740 PEPPER PnL (+14 %) at a 52 % increase in near-limit time
(373 → 568). The marginal lift is smaller per unit of tail risk.
V2_clean is the better lift-to-tail-risk ratio. V2_upside is
shortlisted as an alternate, not dismissed.

## 2. Does it clearly beat current PEPPER references locally?

**Yes, on both views and by a material margin.**

Rank (official-range proxy, 132 candidates):

1. C_buyhold — +7 279.0 (directional upper bound, not a candidate)
2. V2_upside (L3 narrow × mid × convex) — +6 212.0
3. **V2_clean (L3 mid × mid × medium)** — **+5 472.5**
4. L1_seed60_win01000 (opening+core only, no overlay) — +5 207.5
5. C_corelong_v1_base50 (v1 best, no opening) — +4 205.0
6. C_f5 (shipped best) — +3 911.5
7. C_promoted / C_alt — +2 394.0
8. …

Magnitudes:

- **Proxy lift over F5:** +1 561 PEPPER PnL (+40 %). At 1.5×
  calibration, projects to **≈ +1 040 official** (range +865 to
  +1 200). **Well outside** F5's single-day measurement noise (±~300).
- **Local 3-day lift over F5:** +35 335 PEPPER PnL (+25 %). Local view
  confirms the ordering independently of the proxy.
- **First-25k lift over F5:** +902 proxy PnL (+298 %). This is the
  gap that NO v1 candidate could close. Projected official first-
  25k contribution: ≈ +490 to +690 official.

## 3. Does it fix the early-day weakness?

**Yes, substantially.** This is the decisive v2 change vs v1.

First-25k PEPPER proxy PnL:

| Candidate | First-25k PEPPER | % of buyhold's +1 594 |
|---|---:|---:|
| C_promoted  | +130.0     | 8 % |
| C_alt       | +130.0     | 8 % |
| C_f5        | +302.0     | 19 % |
| C_corelong_v1_base50 | +307.0 | 19 % |
| **V2_clean** | **+1 204.0** | **76 %** |
| V2_upside   | +1 396.0   | 88 % |
| C_buyhold   | +1 593.5   | 100 % |

v1's final recommendation said: *"the only way to meaningfully fix
the early-day gap is a tick-0 seed … that's a different family."*

That family is what v2 built. The opening seed (`open_seed_size=60,
open_window=1000`) + the corrected `_OPENING_TAKE_ANY_ASK` crossing
threshold together deliver a first-25k PEPPER capture of **76–88 %**
of buy-and-hold, while the persistent_core + overlay keep trading
for the rest of the day.

**Remaining first-25k gap is ~24 % for V2_clean and ~12 % for
V2_upside.** That residual gap is structural — the strategy's
`step=8` caps fills at 8 per tick, so reaching +60 takes 8 ticks
(≈800 local ticks ≈8 % of the session). Buy-and-hold reaches +50 in
one tick with no rate limit. Closing the last 12-24 % would require
a larger step (explored in Layer 4 — but `step` was tied across
{4, 8, 12} in hybrid mode because the simulator cap of
`max_aggressive_size=20` dominates) or a larger `max_aggressive_size`
in the engine config.

## 4. ASH leg to pair with

**H1/F5/Alt `wall_mid` leg, unchanged:**

```python
ASH_COATED_OSMIUM = dict(
    fair_value_method="wall_mid",
    fair_value_fallbacks=("mid", "microprice"),
    taker_edge=0.5,
    maker_edge=1.5,
    inventory_skew=4.0,
    flatten_threshold=0.7,
    history_length=48,
)
```

Not explored in v2 (explicit input contract). Proxy-measured
ASH PnL for every candidate in this pass: **+523.0** (consistent,
identical across all rows). Official H1/F5/Alt/buyhold ASH PnL:
+982.81. Ratio: ~0.53×. That ratio is more favourable than the
PEPPER ratio (1.33–1.83×) — consistent with ASH being the "solved"
product where the local simulator under-fills maker quotes compared
to official.

Recommended combined total projections:

| Candidate | Projected total (proxy/1.5 + official ASH) |
|---|---:|
| V2_clean + wall_mid ASH  | **≈ +3 650 PEPPER + +983 ASH = +4 633 total** |
| V2_upside + wall_mid ASH | **≈ +4 140 PEPPER + +983 ASH = +5 123 total** |
| F5 official total        | +3 117.72 |

## 5. Prepare a new upload candidate now?

**Yes — but only with one calibration-confirmation upload.**

The case for uploading is now strong:

1. Projected PEPPER lift (≈ +900 to +2 080 over F5's +2 135) is
   clearly outside single-day measurement noise, unlike v1 where
   the lift sat inside it.
2. The projected total (V2_clean ≈ +4 633; V2_upside ≈ +5 123)
   exceeds F5's observed official total (+3 117.72) with
   substantial margin — enough that even a 30 % calibration error
   leaves the lift positive.
3. First-25k capture improvement is structural (76-88 % of buyhold),
   not a noise artefact.
4. Near-limit profile (373 / 1000) and never-short behaviour
   (max_short_fh=0) are clean.

**But two sources of calibration uncertainty warrant one
measurement upload before an all-in upload:**

1. **Seeded candidate calibration is unknown.** The 1.3–1.8× ratio
   is measured on MM / buyhold references. A candidate that fires
   one large tick-0 taker intent and then transitions to MM-style
   trading has a different fill profile. The simulator is permissive
   with `_OPENING_TAKE_ANY_ASK`; the official environment may have
   tighter order-book depth.
2. **Drift specificity.** Everything in v2 is measured on data
   where the +0.1-per-tick drift held. Round-2 data is unknown.
   The L5 protection test was a no-op on training data — that does
   NOT prove protection is unnecessary; it only proves it was
   unneeded on drift days.

**Recommended sequence:**

1. **Upload V2_clean first** (single candidate, single calibration
   measurement). If official PEPPER PnL lands ≥ +3 000, the 1.5×
   calibration holds for seeded candidates and V2_upside becomes
   the natural next-best upload.
2. **If V2_clean comes in substantially below projection** (e.g.
   ≤ +2 500), the seeded candidate is calibrating differently from
   MM references. In that case, fall back to F5 and treat v2 as
   a measurement tool, not a production candidate.
3. **Do NOT bundle V2_clean and V2_upside in one upload.** That
   wastes one of our calibration data points.

## 6. What remains uncertain

1. **Seeded-candidate calibration.** Core uncertainty. See §5.
   Mitigation: one-shot V2_clean upload for calibration before
   V2_upside.

2. **Drift specificity.** v2's gains come from (a) seeding long
   at tick 0 and (b) the overlay's add branch firing on small
   negative residuals. Both assume the drift direction holds. On a
   flat or reversing day, V2_upside imports more downside than
   V2_clean, and both import more than F5. `C_corelong_no_open`
   (pure core, no opening, no overlay) is the family's defensive
   floor but it only does +2 779 PEPPER proxy — worse than F5.

3. **Protection layer is a training-data no-op.** L5 variants all
   tied because the trim branch never fires on the drift-up
   training data. Protection remains unimplemented in a real-
   behavior sense; the current L5 stand-in was a floor bump. If a
   Round-2 day reverses, v2 has no concrete guard.

4. **Simulator fill model divergence.** Maker-first exec_style
   produced +0.0 PEPPER on the proxy but +209 173 on the 3-day
   view. The local simulator doesn't match maker quotes inside the
   book consistently on short windows. Hybrid is the recommended
   exec_style and was the winner; this is not a gate but it is a
   reminder that the local fill model is not the official
   environment.

5. **The 1.5× calibration is 4 data points.** Promoted 1.33×, Alt
   1.16×, F5 1.83×, buyhold 1.60×. The variance across this small
   sample (±30 %) is the dominant source of projection error on
   official PnL.

6. **Overlay convex variant's near-limit time.** V2_upside spends
   56.8 % of the session near the position limit (568 / 1000).
   That's materially more than V2_clean (37.3 %) or F5 (14.4 %).
   If the official environment penalises near-limit exposure
   differently than the simulator (e.g. through fill rejection
   rules or position-ratio priority), V2_upside could under-deliver
   more than V2_clean.

7. **`max_aggressive_size=20` choice.** v1 and v2 both bump PEPPER's
   `max_aggressive_size` from the shipped 8 to 20 so the strategy's
   `step` is the rate limit. A real upload would encode this in the
   engine config for the shipped bundle — we would need a new
   engine-config factory (not in scope for this pass). Flagged as
   a one-line config change needed before upload.

## 7. Scope compliance

This pass:

- **Did NOT** reopen full Round 1 optimisation.
- **Did NOT** mutate any shipped `round1_*_engine_config` factory.
- **Did NOT** register `pepper_core_long` in `STRATEGY_REGISTRY`.
- **Did NOT** export any submission bundle.
- **Did NOT** upload anything.
- **Did NOT** silently change promoted / default configs.
- **Did NOT** run a giant cross-product grid. 132 candidate
  evaluations × 2 views = 264 simulator runs, structured into 5
  layers with top-2 carry-forward between layers (see
  `pepper_candidates.md` per-layer winner table).
- **Did NOT** do meaningful ASH work. ASH leg frozen at H1/F5/Alt
  `wall_mid` in every row.
- **Did NOT** ship a new fair-value estimator. `linear_drift` reused
  verbatim.
- **Added** the `open_seed_size`, `open_window`, `open_no_short`
  knobs to `CoreLongParams` + the corresponding opening branch to
  `PepperCoreLongStrategy.generate_intent`, plus 13 new unit tests
  (11 for opening logic, 2 for the tick-0 cross regression). Full
  test suite: **498 / 498 green** (up from 485 in v1).
- **Fixed** the v1 mis-described official-cadence proxy. v2 uses
  the corrected official-range proxy (day 0, `[0, 99_900]`, native
  100-tick cadence, verified at 1000 snapshots).
- **Fixed** a latent bug in the opening logic discovered in the
  first v2 run: `buy_below` was using the default
  `fair_price - config.taker_edge` threshold, which stays well
  below the best ask → zero opening fills. Replaced during the
  opening window with `_OPENING_TAKE_ANY_ASK = 1e9`, matching the
  pattern used by `BuyAndHoldStrategy`.

## Deliverable files

- [controls.md](controls.md) — Phase A frozen references (official
  numbers unchanged; added in-family anchor `C_corelong_v1_base50`).
- [pepper_corelong_memo.md](pepper_corelong_memo.md) — Phase B
  mechanism memo (adds the opening-layer rationale on top of v1).
- [run_search.py](run_search.py) — Phase D layered runner with
  corrected proxy.
- [run_search.log](run_search.log) — full stdout of the final run.
- [pepper_candidates.csv](pepper_candidates.csv) — 132 candidates
  with full per-metric columns and the disclosed score.
- [pepper_candidates.md](pepper_candidates.md) — same as markdown
  with per-layer winner table.
- [shortlist.md](shortlist.md) — 3 candidates (C_f5, V2_clean,
  V2_upside) + non-shortlisted observations.
- [final_recommendation.md](final_recommendation.md) — this file.
