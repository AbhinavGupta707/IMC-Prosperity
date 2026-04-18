# PEPPER core-long + residual-overlay — final recommendation

One-screen answer, then a numbered breakdown of the user's six final
questions, then the uncertainty flags.

## One-screen answer

| Question | Answer |
|---|---|
| Best core-long + residual-overlay candidate? | **`B_base50`** (base_long=50, default overlay, step=8, exec=hybrid). Cleanest combination of lift + low near-limit exposure. |
| Does it clearly beat current PEPPER references **locally**? | **Yes** on both views. Beats F5 by +5 % on official-cadence PEPPER and +17 % on local full-replay PEPPER. But the absolute projected official lift over F5 is ~+150 to +450 — a meaningful but modest improvement. |
| Does it fix the early-day weakness? | **No.** First-25k PEPPER is +111 for every MM and core-long variant (the `linear_drift` estimator does not fit enough samples at 1000-cadence before the first quarter ends). Only buy-and-hold captures early drift PnL, by construction. This pass **does not close the early-day gap**. |
| What ASH leg should it be paired with? | The **frozen H1/F5/Alt wall-based leg** (`wall_mid, t=0.5, m=1.5, skew=4.0, flat=0.7, h=48`). No ASH dimension was explored; this is the input contract of the pass. |
| Prepare a new upload candidate now? | **Not yet** — at least not without a second eye. The expected official lift is small (~+150 to +450 PEPPER PnL) and lives within the single-day measurement noise of F5. See §5 for the recommended next step. |
| What remains uncertain? | See §6. Biggest: (i) drift-day specificity; (ii) ramp-in cost we can't remove without a tick-0 seed; (iii) the overlay contribution to real official PnL is minimal at the official cadence. |

## 1. Best core-long + residual-overlay candidate

**`B_base50`** is the answer.

Params:

```python
CoreLongParams(
    base_long=50,
    add_thresh=3.0,
    trim_thresh=5.0,
    add_gain=3.0,
    trim_gain=1.0,
    floor=0,
    ceiling=80,
    step=8,
    exec_style="hybrid",
    hybrid_threshold=2.0,
)
```

Paired with the H1/F5/Alt wall-based ASH leg, run via
`PepperCoreLongStrategy` (research-only; not registered in
`STRATEGY_REGISTRY`).

Evidence (raw metrics, primary):

| Metric | C_promoted | C_f5 | **B_base50** | C_buyhold (ref) |
|---|---:|---:|---:|---:|
| Official-cadence PEPPER | +19 225 | +25 055 | **+26 367** | +79 076 |
| Local full-replay PEPPER | +78 101 | +144 232 | **+169 189** | +239 423 |
| First-50k PEPPER (official) | +2 260 | +2 692 | **+3 204** | +39 471 |
| Bucket 3 PEPPER (official) | +10 582 | +13 564 | **+14 010** | +19 880 |
| Near-limit snapshots (/1000) | 0 | 78 | **2** | 998 |
| Max long (official) | +49 | +61 | +63 | +80 |
| First-half short (official) | 0 | 0 | **0** | 0 |

B_base50 has the best lift-to-tail-risk ratio among all 22 family
candidates. H_upside40_agg and H_upside50_agg tie on PEPPER PnL
(+26 844 vs +26 367, ≈ +1.8 %) but at the cost of **80 near-limit
snapshots** vs B_base50's 2 — a 40× cost for a 1.8 % gain.

## 2. Does it clearly beat current PEPPER references locally?

**Yes on rank, modestly on magnitude.**

Rank (official-cadence PEPPER, 22 family candidates + 5 controls):

1. C_buyhold — +79 076 (directional upper bound, not a candidate)
2. H_upside50_agg / H_upside40_agg — +26 844 (tie)
3. **B_base50 — +26 367**
4. C_f5 — +25 055 (current shipped best)
5. B_base40 — +24 802
6. ...

Magnitude:

- Official-cadence PEPPER lift over F5: +1 312 local = ~+120 to +180 official at 10-11× calibration.
- Local full-replay PEPPER lift over F5: +24 957 = ~+2 300 over 3 days = ~+770 per day at the same calibration.

At the one-day official scale, the gap sits at **the edge of
measurement noise** (F5 officially was +2 135; a repeat F5 run could
easily be ±300 from that). The 3-day lift signal is stronger.

## 3. Does it fix the early-day weakness?

**No. The early-day weakness in the F5 family is almost entirely a
cadence / estimator-warm-up effect, not a strategy defect.**

First-25k PEPPER at official cadence:

| Candidate | First-25k PEPPER | Mechanism |
|---|---:|---|
| C_promoted | +111 | No PEPPER trades in the first quarter at 1000-cadence |
| C_f5 | +111 | Same |
| C_alt | +111 | Same |
| B_base50 | +111 | Same (strategy wants to buy but can't — `linear_drift` has only 25 samples by t=25 000 and the intent is `hybrid` with `hybrid_threshold=2.0` which requires residual to move) |
| C_buyhold | **+19 470** | Crosses at tick 0 and holds; drift accrues linearly |

The only way to meaningfully fix the early-day gap is a **tick-0
seed** — take an aggressive taker intent at t=0 regardless of
estimator warm-up. That's a different family from "residual overlay
around a drift fair" and is not tested in this pass.

Flag this as the single biggest unresolved problem: **all the MM /
core-long variants leave ~+19 k of local first-quarter PnL on the
table that buy-and-hold captures**. Beating buy-and-hold's early
capture requires changing the fill profile at t=0, not changing the
residual-overlay parameters.

## 4. ASH leg to pair with

**H1/F5/Alt wall-based leg, unchanged:**

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

No ASH dimension was explored. Local ASH PnL on day 0 was +41 for
every candidate (it's the same leg), matching the
`controls.md` record of official ASH PnL = +982.81 for H1/F5/Alt/
buy-and-hold (this pass measured local-cadence ASH which is a 24×
undersample of the official day — the +41 local vs +983 official
mismatch is consistent with cadence-driven spread-capture loss,
**not** a change in ASH leg quality).

## 5. Prepare a new upload candidate now?

**Recommend: not yet.** The case for uploading is thin:

1. **Projected official PEPPER lift is small** (~+150 to +450 PEPPER PnL over F5's +2 135). Within the noise of a single-day measurement.
2. **The overlay barely fires at official cadence** (B_base30 = D_trim3 = D_trim5 = D_trim7 = E_floor00 = E_floor10 = E_floor20 = F_step04 = F_step08 = F_step16, all +21 529 PEPPER). That's 9 out of 22 family candidates producing bit-identical results because the residual never leaves the dead zone on the drift day at 1000-cadence.
3. **The real upside is early-day fill, which this family does not address.** The gap from C_f5 (+25 055) to C_buyhold (+79 076) is +54 k locally = ~+5 000 official-equivalent. A strategy that captures just half of that early drift would be worth two B_base50 uploads.

**If we decide to upload anyway, the right candidate is B_base50**
(not H_upside50_agg): 40× less near-limit exposure for a 1.8 %
official PnL trade-off.

**Better next step — build a tick-0-seeded core-long.** That is, a
strategy that:

1. On tick 0, emits a taker buy intent up to `base_long` (like
   buy-and-hold to +N instead of to +position_limit).
2. Thereafter, trades around that position using the same residual-
   overlay rules.

This can be implemented as a minor extension of
`PepperCoreLongStrategy` (a `seed_at_tick_0: int` param) or as a
composition of `BuyAndHoldStrategy` (one tick only) + `PepperCoreLong-
Strategy`. Either way, it keeps the frozen ASH leg, keeps the drift-
fair family, but closes the estimator-warm-up gap that this pass
cannot close with parameter tuning alone.

## 6. What remains uncertain

1. **Drift specificity.** The whole family assumes a +0.1-per-tick
   upward drift. Every metric above was measured on data where that
   drift held. A flat / reversing day would make any core-long
   position an **unhedged directional bet**. Our strongest robustness
   signal — `C_corelong_only` never going net short across any of
   the 3 local days — suggests the drift is approximately consistent
   across the training set, but Round 2 data is unknown.

2. **Ramp-in cost we cannot remove here.** Core-long at step=8 takes
   7 ticks at 1000-cadence to reach +50 from flat (~7 % of a
   session). At step=16 the ramp is halved but we don't see that in
   the local results because the simulator's fills are already
   step-constrained by `max_aggressive_size=20`. A bigger
   `max_aggressive_size` might change the picture — but also moves
   us closer to the buy-and-hold failure mode (all-in at tick 0).

3. **Overlay contribution to official PnL is minimal at official
   cadence.** C_corelong_only (+17 826, no overlay) → B_base30
   (+21 529, nominal overlay) is +3 703 local = ~+360 official
   projection from the overlay. That is a real gain — but it's
   small relative to the drift-carry gain from raising `base_long`
   (B_base30 → B_base50 = +4 838 local = ~+470 official). The overlay
   is a modest add, not a transformative lever.

4. **Local simulator does not fill maker-only strategies.** G_maker
   (`exec_style=maker`) produced **zero PEPPER trades** in both
   views. The local fill model does not match maker quotes inside
   the book consistently. This is a known divergence from the
   official environment; it does not invalidate the shortlist (all
   three shortlisted candidates are hybrid), but it means **we
   cannot locally evaluate the maker-only variant** that the user
   asked us to test under Dimension G. Flagged as a simulator
   limitation, not a strategy verdict.

5. **Local-to-official ratio is a single-point calibration.** The
   10-11× ratio is derived from 3 controls (promoted, alt, F5)
   against their one official run each. That is 3 data points. The
   ratio for a structurally different strategy (core-long) may be
   different by ±30 %; we are extrapolating.

6. **The simulator clips at `max_aggressive_size=20` for PEPPER in
   this pass** (bumped from the shipped 8). That is a deliberate
   choice so the strategy's `step` is the effective rate limit, but
   it means B_base50 takes fewer ticks to fill than any of the
   shipped variants at their shipped `max_aggressive_size`. If the
   official environment runs the strategy at `max_aggressive_size=20`
   (which it would, because the shipped bundle would encode this),
   the behavior is fully predicted; if it runs at 8, B_base50 would
   fill slower than predicted here.

## 7. Scope compliance

This pass:

- Did **not** reopen full Round 1 optimization.
- Did **not** change any `round1_*_engine_config` factory.
- Did **not** register `pepper_core_long` in `STRATEGY_REGISTRY`.
- Did **not** export any submission bundle.
- Did **not** upload anything.
- Did **not** silently change promoted/default configs.
- Did **not** build a giant grid. 26 candidates (5 controls + 21 family entries) on two views.
- Added one new research module, one test file, one research runner, and six docs. Full test suite remains green (485 / 485; up from 458).

## Deliverable files

- [controls.md](controls.md) — Phase A frozen references
- [pepper_corelong_memo.md](pepper_corelong_memo.md) — Phase B mechanism memo
- [run_search.py](run_search.py) — Phase D runner
- [pepper_candidates.csv](pepper_candidates.csv) — all 26 candidates with full metrics
- [pepper_candidates.md](pepper_candidates.md) — same as markdown
- [shortlist.md](shortlist.md) — the three-candidate shortlist + a non-shortlisted defensive observation
- [final_recommendation.md](final_recommendation.md) — this file
