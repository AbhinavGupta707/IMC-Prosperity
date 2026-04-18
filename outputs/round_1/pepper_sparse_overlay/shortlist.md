# PEPPER near-buy-and-hold + sparse-overlay — shortlist

Three candidates per the scope rules. All numbers from
`pepper_candidates.csv` produced by `run_search.py`.

**Primary decision inputs: raw PEPPER PnL, first-25k / first-50k
capture, average long position, unintended shorting, near-limit
behavior. Score is a summary only.**

## Headline finding

**A seed=65 (or 70) opening on top of `base_long=80, ceiling=80`
slightly BEATS buy_hold_80 on the official-range proxy: +7 351
PEPPER vs +7 279 (a +72 lift, +0.99 %).** The mechanism is a small
spread-cost saving at the tick-0 cross — buying 65 units at the
initial best asks is cheaper per-unit than buying 80 at the deeper
book levels, and the remaining ~15 units accrue during the hold
phase when the book has refreshed.

**Every layer past L1 is essentially inert** on the one official
day's data:

| Layer | What was swept | Proxy PEPPER spread across candidates |
|---|---|---|
| L1 (opening) | seed × window | **+6 430 to +7 351** (the decisive layer) |
| L2 (floor) | 40..70 | All tied at +7 351 — trim never binds, so floor never binds |
| L3 (trim) | thresh × size | All tied at +7 351 — residual never exceeds trim_thresh=6 on the proxy |
| L4 (rebuy) | hybrid_threshold × step | +7 234 (thr=5) to +7 351 (thr≤4) |
| L5 (exec) | exec_style × step | +6 405 (maker) / +7 351 (hybrid) / +7 351 (taker, marginal score edge) |

This is a direct consequence of PEPPER's linearity: the hold-phase
PnL is R² = 1.000000 vs time (see buy_hold analysis in
`outputs/round_1/official_results/buy_hold_pepper/162376_pepper_linearity.png`).
There are no residual excursions big enough on the proxy cadence to
give an overlay anything to do. The only lever that matters is the
tick-0 fill curve.

## The shortlist

### 1. Control — `C_buyhold_80` (current best shipped reference)

| Field | Value |
|---|---|
| Config | `round1_test_engine_config` (buy-and-hold PEPPER at limit=80) |
| PEPPER (official) | **+7 286.00** (submission 162376) |
| PEPPER (proxy)    | +7 279.00 (0.999× ratio — 1:1 calibration) |
| First-25k PEPPER  | +1 294 (the reference — spread cost minus 25k ticks of carry) |
| Near-limit /1000  | 999 (pinned) |
| Avg PEPPER position | +79.9 |
| Total official PnL | **+8 245.78** |

Already uploaded. The reference every candidate in this pass is
trying to match or slightly beat.

### 2. Clean improved — `V3_nearhold` (seed=65, win=500, base=80)

Canonical label: **`L1_seed65_win00500`** (≡ `L2_s0_fl40` ≡
`L3_s0_trim8_size5` ≡ `L4_s0_h2_small` ≡ `L5_s0_taker_first_step04`
— all 27+ tied rows share this behavior; L5_taker_first edges ahead
on the score tiebreaker).

| Field | Value |
|---|---|
| Strategy | `PepperCoreLongStrategy` (research-only) |
| PEPPER (proxy)     | **+7 351.00** (+72 vs buy_hold_80; +1 879 vs V2_clean) |
| PEPPER (projected official @1:1) | **≈ +7 350 ± ~50** |
| First-25k PEPPER   | **+1 571** (+277 vs buy_hold_80 proxy +1 294) |
| First-50k PEPPER   | +3 451 (+157 vs buy_hold_80 proxy +3 294) |
| Bucket-3 PEPPER    | ~+1 900 (vs buy_hold ~+1 992 — ~matches) |
| Near-limit /1000   | 998 (essentially pinned — same as buy_hold) |
| Avg PEPPER position| +79.0 (vs buy_hold +79.9 — essentially the same) |
| Max long            | +80 |
| First-half short   | 0 (proxy) |

```python
CoreLongParams(
    base_long=80,
    ceiling=80,
    floor=40,            # inert on this data; any value 40..70 is equivalent
    add_thresh=3.0,      # inert with base=ceiling
    trim_thresh=8.0,     # inert — residual never exceeds 6 on the proxy
    add_gain=5.0,        # inert
    trim_gain=2.0,       # inert
    step=8,              # any value 4..16 is equivalent
    exec_style="taker",  # tiniest score edge vs "hybrid"; hybrid equally valid
    hybrid_threshold=2.0,
    open_seed_size=65,   # <-- the only knob that actually matters
    open_window=500,     # <-- any window >= 500 is equivalent
    open_no_short=True,
)
```

**Why this is the clean improvement:**

- **Slightly beats buy_hold_80** on proxy (+72 PEPPER PnL, +0.99 %).
  Small but real, and it comes from the correct mechanism: smaller
  first-tick spread cost.
- **Better first-25k capture** (+1 571 vs +1 294) — the seed spreads
  its acquisition across ~7 ticks instead of 1, avoiding the worst
  of the depth-walk in the ask book.
- **Same tail-risk profile** as buy_hold_80: same near-limit time
  (998 vs 999), same max long, same avg position (+79.0 vs +79.9),
  same never-short behavior.
- **Full protective overlay infrastructure is present** (floor 40,
  trim 8, etc.) but never fires on this data. The strategy retains
  the **optionality** to trim on future reversing days — at zero
  cost on the current drift-only day.

### 3. Higher-upside alternate — not justified, not shortlisted

There is no meaningful higher-upside alternate in this family. Every
candidate beyond L1 is tied at +7 351 or worse. The Layer-6
`higher_upside` variant (floor=50, aggressive trim, taker exec)
actually scored WORSE (+6 430 — its open_window=0 means only 8 units
acquired at t=0, then relying on maker-style fills).

The most aggressive upside I can construct by hand is to **increase
`open_seed_size` further** — but seed=75 and seed=80 both give
+7 330, SLIGHTLY WORSE than seed=65/70. The spread-saving
mechanism has a sweet spot; going all-in (seed=80) eats through
deeper ask levels.

**Observation instead of an upside alternate:** the
`open_seed_size ∈ {65, 70}` × `open_window ∈ {500, 1000, 2000}`
candidates are all byte-identical on every metric. Any of those 6
configurations is an equally valid upload. **Pick the smallest
`open_seed_size` (65) and shortest window that wins (500)** to
minimize the near-limit profile on a reversing day.

## Non-shortlisted observation — `C_v2_clean_ref`

V2_clean's proxy PEPPER is **+5 472.5** (official +5 426). That's
**−1 879** vs this pass's winner. The entire gap is the +30-unit
carry difference between `base_long=50` and `base_long=80`. This
confirms the v2-pass diagnosis: V2_clean was giving up ~1 860 of
drift carry. `V3_nearhold` recovers the full gap and then some.

## Side-by-side comparison

| Metric | V2_clean (official) | buy_hold_80 (official) | **V3_nearhold (proxy)** |
|---|---:|---:|---:|
| PEPPER PnL          | +5 426.00 | +7 286.00 | **+7 351.00** |
| First-25k PEPPER    | +907     | +1 294   | **+1 571** |
| First-50k PEPPER    | +2 451   | +3 294   | **+3 451** |
| Final PEPPER pos    | +50      | +80      | +80 (held) |
| Avg PEPPER position | ~+55     | +79.9    | +79.0 |
| Near-limit /1000    | ~373     | 999      | 998 |
| First-half short    | 0        | 0        | 0 |
| Full total PnL      | +6 385.78 | +8 245.78 | ≈ +8 310 (proj.) |

## What the shortlist does NOT claim

- **That the +72 PEPPER edge is guaranteed.** The proxy-to-official
  calibration for seeded candidates is 1:1 but with ±5 % noise. +72
  could come in as anywhere from −300 to +450 official. The baseline
  expectation is "match buy_hold within noise."
- **That the overlay will ever fire in production.** On this
  drift-only data the trim branch never fires. If Round 2 introduces
  reversal days, the overlay might fire — but that's unmeasured.
- **That taker beats hybrid in practice.** The proxy tie-break
  between `taker_first` and `hybrid` is noise-level (score +21 184
  vs +21 180) and driven by trade-count differences in the 3-day
  robustness view. In production the two are functionally
  identical when trim/rebuy never fires.
- **That this is a step-change over buy_hold.** It's a marginal
  improvement (+72 / +0.99 %). The primary value is **retaining
  trim optionality** for future reversing days at zero-cost on this
  day.
