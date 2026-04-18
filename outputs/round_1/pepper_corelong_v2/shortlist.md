# PEPPER core-long + opening + overlay v2 — shortlist

Three candidates per the scope rules: one control, one clean
improvement, one higher-upside alternate. All numbers are from
`pepper_candidates.csv` produced by `run_search.py`.

**Primary decision inputs (per `CLAUDE.md` Evidence Calibration and
the prompt's scope rules): raw PEPPER PnL, first-25k / first-50k
capture, unintended shorting, near-limit behaviour, cross-view
robustness. Score is a summary only.**

## Calibration

Fixed in v2: the **official-range proxy** (day 0, timestamps
`[0, 99_900]`, native 100-tick cadence, 1000 snapshots) matches the
real official day's time window AND sample rate. v1's
`timestamp % 1000 == 0` filter was 10× sparser over a 10× longer day.

Proxy-to-official calibration on the four public controls:

| Variant | v2 proxy PEPPER | Official PEPPER | Ratio |
|---|---:|---:|---:|
| C_promoted | +2 394.0 | +1 797.2 | 1.33× |
| C_alt      | +2 394.0 | +2 057.4 | 1.16× |
| C_f5       | +3 911.5 | +2 134.9 | 1.83× |
| C_buyhold  | +7 279.0 | +4 559.0 | 1.60× |

Mean ≈ 1.5×, range 1.16–1.83×. **Much closer to 1× than v1's 10–11×,
confirming the v1 proxy was stretched.** Calibration is a 4-point
extrapolation so projections below use the range, not the mean.

**Note:** v1 and v2 controls were re-measured under the corrected
proxy. v2 `C_f5` proxy (+3 911.5) is a new number; it does NOT equal
v1's `C_f5` proxy (+25 055, which was on the 10× stretched day).
The official F5 PEPPER (+2 134.9) is unchanged — that's from the
real IMC log, not a proxy.

## The shortlist

### 1. Control — `C_f5` (shipped best PEPPER; keep as-is for now)

| Field | Value |
|---|---|
| Config | `round1_f5_engine_config` (live at `limit_80`) |
| PEPPER (proxy)     | +3 911.5 |
| PEPPER (official)  | **+2 134.9** |
| First-25k PEPPER   | +302.0 (proxy) |
| First-50k PEPPER   | +1 501.0 (proxy) |
| Near-limit steps   | 144 / 1000 |
| Peak long (proxy)  | +62 |
| First-half short   | 0 (official-range proxy); −29 (local 3-day) |
| Rationale | The current shipped best. All comparisons below use it as the baseline. |

### 2. Clean improved — `V2_clean` (L3 add_mid/trim_mid/size_medium + seed60/win1000)

A single run can be reproduced by any of the six tied rows; the
canonical label is **`L3_s0_add_mid_trim_mid_size_medium`**.

| Field | Value |
|---|---|
| Strategy | `PepperCoreLongStrategy` (research-only) |
| Params | See code block below |
| PEPPER (proxy) | **+5 472.5** |
| PEPPER (projected official @1.5×) | **≈ +3 650** (range +3 040 to +4 210 at 1.3×–1.8×) |
| First-25k PEPPER (proxy) | **+1 204.0** (vs F5 +302.0 → +298%; vs buyhold +1 594) |
| First-50k PEPPER (proxy) | +2 758.0 (vs F5 +1 501 → +84%; vs buyhold +3 474) |
| Bucket-3 PEPPER (proxy)  | +1 357.0 |
| Near-limit steps (/1000) | **373** (vs F5 144, buyhold 999) |
| Peak long (proxy)        | +64 |
| First-half short (proxy) | **0** |
| First-half short (local) | −11 (same as v1 B_base50) |
| Local PEPPER (3-day)     | +179 567 (+25 % vs F5; +6 % vs v1 B_base50) |

```python
CoreLongParams(
    base_long=50,
    add_thresh=3.0,     # "mid" add band
    add_gain=5.0,       # "medium" overlay size (×1.0 on gain)
    trim_thresh=5.0,    # "mid" trim band
    trim_gain=1.0,      # kept modest (asymmetric)
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

**Why this is the clean improvement:**

- Projected lift over F5 official: **≈ +900 to +2 080 PEPPER PnL**
  (+40 % to +97 %). This is well outside the single-day measurement
  noise of F5 (±~300 PnL) — unlike v1, where the projected lift
  sat inside that noise band.
- First-25k PEPPER: **+298 %** over F5 at the proxy cadence. This is
  the gap v1 could not close. The opening-seed layer closes ~76 % of
  the buy-and-hold first-25k edge while keeping residual harvesting
  for the rest of the session.
- Never goes short on the official-range proxy. Local 3-day worst is
  −11, matching v1 B_base50.
- Near-limit exposure is 373 / 1000 — elevated vs F5 (144) but far
  below the upside alternate (568) and nowhere near buyhold's 999.
  The peak position is +64, not pinned at the hard limit.

### 3. Higher-upside alternate — `V2_upside` (L3 add_narrow/trim_mid/size_convex + seed60/win1000)

Canonical label: **`L3_s0_add_narrow_trim_mid_size_convex`** (≡ `L4_s0_hybrid_step04`).

| Field | Value |
|---|---|
| Strategy | `PepperCoreLongStrategy` |
| PEPPER (proxy) | **+6 212.0** |
| PEPPER (projected official @1.5×) | **≈ +4 140** (range +3 450 to +4 780 at 1.3×–1.8×) |
| First-25k PEPPER (proxy) | **+1 396.0** — **88 % of buyhold's +1 594** |
| First-50k PEPPER (proxy) | **+3 161.5** — **91 % of buyhold's +3 474** |
| Bucket-3 PEPPER (proxy)  | +1 230.5 |
| Near-limit steps (/1000) | **568** (vs clean 373, buyhold 999) |
| Peak long (proxy)        | +64 |
| First-half short (proxy) | **0** |
| First-half short (local) | −11 |
| Local PEPPER (3-day)     | +198 882 (+38 % vs F5; +17 % vs v1 B_base50; 83 % of buyhold) |

```python
CoreLongParams(
    base_long=50,
    add_thresh=2.0,     # "narrow" add band (fires on small negative residuals)
    add_gain=6.4,       # "convex" overlay size (4.0 × 1.6)
    trim_thresh=5.0,    # "mid" trim band (unchanged from clean)
    trim_gain=1.0,
    floor=0,
    ceiling=80,
    step=4,             # L4 hybrid was tied across step ∈ {4, 8, 12}
    exec_style="hybrid",
    hybrid_threshold=2.0,
    # --- opening (v2) ---
    open_seed_size=60,
    open_window=1000,
    open_no_short=True,
)
```

**Why this is the higher-upside alternate:**

- Projected lift over F5 official: **≈ +1 315 to +2 650 PEPPER PnL**
  (+62 % to +124 %). Nearly-buyhold PEPPER capture without
  buyhold's tail risk.
- Captures **88 %** of buyhold's first-25k edge and **91 %** of its
  first-50k edge.
- Tighter add band (`add_thresh=2.0` vs 3.0) + convex gain (6.4 vs
  5.0) mean the overlay fires on smaller residuals and scales up
  faster. This is the main delta vs the clean candidate.
- Near-limit exposure 568 / 1000 (~57 % of session near +60) is
  materially more tail risk than clean (~37 %) but still well below
  buyhold's 99.9 %. Peak long is the same (+64) — the bot never
  pins at the hard limit.

## Non-shortlisted observations

### The overlay layer contributes substantially under the corrected proxy

Layer 3 added **+1 004.5 PEPPER proxy PnL** on top of the best
opening+core (+5 207.5 → +6 212.0). v1 had reported the overlay
"barely fires" at its stretched 1000-tick cadence; v2's 100-tick
proxy has 10× more samples and shows the overlay is a real lever.
This updates the v1 conclusion: **overlay is worth the near-limit
cost at the official cadence**, not a cosmetic add.

### Layer 5 protection had no effect on the current training data

All four L5 variants (no protection / mild slope / mild DD / mild
combined) tied at +6 212.0 PEPPER. The trim branch never fires in
this data because the drift holds across all three local days.
Protection will matter on a reversing day; it is a no-op on drift
days. **Flagged, not shortlisted.**

### Layer 4 maker-only is not reliably evaluable locally

`L4_*_maker_first_*` produced +0.0 PEPPER on the proxy (but
+209 173 on the 3-day local view — the local simulator fills makers
generously over long stretches but not on the short proxy window).
This is a known simulator-vs-official divergence carried over from
v1. All three shortlisted candidates are hybrid.

### Opening window size doesn't matter once it's large enough

`seed=60 win=1000` = `seed=60 win=2500` = `seed=60 win=5000` on every
metric. At `step=8` and 100-tick cadence, the seed fills in ~7 ticks
(≈700 local ticks). Any window ≥ 1000 is enough. `win=0` (only
t=0, one fill) underperforms by ~+329 PEPPER proxy.

## Side-by-side comparison

| Metric | C_f5 (control) | V2_clean (improvement) | V2_upside (upside) | C_buyhold (ref) |
|---|---:|---:|---:|---:|
| PEPPER (proxy)          | +3 911.5 | **+5 472.5** | **+6 212.0** | +7 279.0 |
| PEPPER (official)       | +2 134.9 | projected **≈ +3 040 to +4 210** | projected **≈ +3 450 to +4 780** | +4 559.0 |
| First-25k PEPPER        | +302.0   | **+1 204.0** | **+1 396.0** | +1 593.5 |
| First-50k PEPPER        | +1 501.0 | **+2 758.0** | **+3 161.5** | +3 473.5 |
| Bucket-3 PEPPER         | +948.5   | +1 357.0     | +1 230.5     | +1 880.0 |
| Near-limit steps /1000  | 144      | 373          | 568          | 999 |
| Peak long (proxy)       | +62      | +64          | +64          | +80 |
| First-half short (proxy)| 0        | 0            | 0            | 0 |
| First-half short (local)| −29      | −11          | −11          | 0 |
| Local PEPPER (3-day)    | +144 232 | +179 567     | +198 882     | +239 423 |

## What the shortlist does NOT claim

- That the projected official lift matches the proxy exactly. A
  1.3×-to-1.8× calibration band with n=4 is genuinely noisy; a
  seeded candidate may calibrate differently than MM references
  because its fill profile is different (one large tick-0 buy,
  then MM-style trading).
- That v2 performs on a non-drifting day. Every PnL number is on
  data where the drift held. On a flat / reversing day, a core-long
  seed adds direct directional exposure — and protection is a
  local no-op here, so there is no implemented defence against it
  yet.
- That the opening seed transfers identically to the official
  environment. The simulator fills opening taker intents by
  crossing any ask; official may have tighter order-book depth or
  different priority rules.
- That the buy-and-hold gap is fully closed. V2_upside captures
  88-91 % of buyhold's first-half PnL but falls short in the late
  buckets (bucket 3: +1 230 vs buyhold +1 880). This is the
  opposite of F5's problem — v2 closes the early gap but buyhold
  still wins the late-day hold.
