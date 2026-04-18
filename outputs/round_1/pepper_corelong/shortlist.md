# PEPPER core-long + residual-overlay — shortlist

Three candidates per the scope rules (one control, one clean
improvement, one upside alternate). A fourth "defensive" candidate is
called out at the bottom as a non-shortlisted observation.

All numbers below are from
``outputs/round_1/pepper_corelong/pepper_candidates.csv``. The
"official-cadence view" is the local replay on day 0, decimated to
`timestamp % 1000 == 0` (1000 snapshots, VERIFIED against
``outputs/round_1/official_results/h1/151053.log``). The "local
full-replay" view is all 3 days × 10 000 snapshots each.

**Primary decision inputs (per the user's scope rules): raw PEPPER
PnL, first-25k / first-50k capture, unintended shorting, near-limit
behavior, and cross-view robustness. Score is a summary only.**

Local-to-official calibration from Phase-9 fastsearch and this pass's
re-measurement of controls is **~10–11×** (e.g. C_f5 local +25 055 vs
official +2 135 = 11.7×; C_promoted local +19 225 vs official +1 797
= 10.7×; C_alt local +22 324 vs official +2 057 = 10.9×).

## The shortlist

### 1. Control — `C_f5` (shipped best PEPPER, keep as-is)

| Field | Value |
|---|---|
| Config | `round1_f5_engine_config` (already live at `limit_80`) |
| Rationale | Currently the best shipped PEPPER result (**official +2 135**). Part of the shipped F5 bundle. No change needed. |
| Official-cadence PEPPER | +25 055 (projects to ~official +2 100–2 300 at 10-11×) |
| First-25k PEPPER | +111 (estimator warm-up dominates at official cadence; same as all MM variants) |
| Near-limit snapshots | 78 / 1000 (peak +61) |
| First-half short | 0 (official-cadence) ; **−29** (local 3-day worst) |
| Why keep | All three new candidates' official projections sit within the noise band of F5's observed official PnL (±~400). No candidate clearly dominates on all dimensions. |

### 2. Clean improved candidate — `B_base50`

| Field | Value |
|---|---|
| Strategy | `PepperCoreLongStrategy` (research-only module) |
| Params | `base_long=50, add_thresh=3.0, trim_thresh=5.0, add_gain=3.0, trim_gain=1.0, floor=0, ceiling=80, step=8, exec_style="hybrid", hybrid_threshold=2.0` |
| Official-cadence PEPPER | **+26 367** (+5.2 % vs C_f5, +37 % vs C_promoted) |
| Local full-replay PEPPER | +169 189 (+17 % vs C_f5, +117 % vs C_promoted) |
| First-25k PEPPER | +111 (matches F5; estimator-warmup-limited) |
| First-50k PEPPER | +3 204 (vs F5 +2 692; **+19 %** mid-day capture improvement) |
| Near-limit snapshots | **2 / 1000** (peak +63) — **38× less** than F5's 78 |
| First-half short | 0 (official-cadence) ; **−11** (local 3-day worst) |
| Projected official PEPPER | **~+2 300–2 600** at 10-11× calibration. Best-case ~+450 above F5. |

**Why this is the clean improvement:**

- Among family candidates that never go short on the official day, it has the highest PEPPER PnL.
- Its near-limit exposure (2 snapshots out of 1000) is an **order of magnitude lower** than F5 (78) or the H_upside variants (80) — direct evidence that capping `step=8` from `base_long=50` keeps the strategy mostly in the 40–60 range rather than pinning at the hard limit.
- The trim side almost never fires at the official cadence (B_base30 = D_trim3 = D_trim5 = D_trim7 are all identical at +21 529 PEPPER — the trim band is deep enough that the residual never reaches it on the drift day). This means on a drift-up day the strategy behaves almost like a pure "ramp to +50 and hold" variant — identical to C_corelong_only but with `base=50` instead of `base=30`.
- Local full-replay 3-day short excursion (−11) is worse than pure-corelong (0) but on par with F5 (−29).

### 3. Higher-upside alternate — `H_upside50_agg`

| Field | Value |
|---|---|
| Strategy | `PepperCoreLongStrategy` |
| Params | `base_long=50, add_thresh=2.0, trim_thresh=8.0, add_gain=4.0, trim_gain=0.5, floor=20, ceiling=80, step=12, exec_style="hybrid", hybrid_threshold=2.0` |
| Official-cadence PEPPER | **+26 844** (+7.1 % vs C_f5, +40 % vs C_promoted) |
| Local full-replay PEPPER | **+183 127** (+27 % vs C_f5, +134 % vs C_promoted) — **highest robustness-view PEPPER in the entire pass excluding buy-and-hold** |
| First-50k PEPPER | +3 204 (same as B_base50) |
| Near-limit snapshots | **80 / 1000** (peak +65, held for ~8 % of the session) |
| First-half short | 0 (official-cadence) ; **−16** (local 3-day worst) |
| Projected official PEPPER | **~+2 300–2 700** at 10-11× calibration |

**Why this is the higher-upside alternate:**

- Aggressive `step=12` fills to `base_long=50` in ~5 ticks at official cadence (vs 7 for B_base50). Faster drift capture.
- `add_gain=4.0` pushes target well above base when residual < −2. Peaks at +65 (compared to B_base50's +63), closer to the hard limit at +60.
- `floor=20` ensures the strategy never flattens — preserves at least +20 of drift carry even if residual swings hard positive.
- Trade-off: **80 near-limit snapshots** is in the same range as F5 (78) but the peak position is higher. Marginally more tail-risk exposure on a reversal day.

**H_upside40_agg** (same config but `base_long=40, floor=10`) is not separately shortlisted because it ties with H_upside50_agg on official-cadence PEPPER (+26 844 each) and is strictly worse on local full-replay (+163 493 vs +183 127). Its lower floor is slightly more defensive on reversing days, but that's better addressed by the non-shortlisted option below.

## Non-shortlisted observation — `C_corelong_only`

`C_corelong_only` (base=30, overlay disabled via `add_thresh=1000`)
is the **only core-long candidate in the pass that never goes net
short on any training day** (`local_pep_max_short_fh = 0`). Its
PEPPER PnL is lower (+17 826 local → ~+1 650 official projection)
but it has the cleanest robustness profile in the family.

It is not shortlisted because its projected official PnL is below
both Promoted (+1 797) and F5 (+2 135) — but it is worth noting as
the **family's defensive floor**: if a future Round 1 day has a
reversing drift, every overlay variant bleeds on the trim side
while C_corelong_only does not.

Flag: **the overlay's trim side is the source of cross-day short
exposure**. Every overlay-enabled candidate (including the MM
controls Promoted, Alt, F5) shows `local_pep_max_short_fh < 0` on
the 3-day replay; the only exceptions are `C_corelong_only` (by
construction) and `C_buyhold` (also by construction).

## Side-by-side comparison of the three shortlisted candidates

| Metric | **C_f5** (control) | **B_base50** (improvement) | **H_upside50_agg** (upside) |
|---|---:|---:|---:|
| Official-cadence PEPPER | +25 055 | **+26 367** | **+26 844** |
| Local full-replay PEPPER | +144 232 | +169 189 | **+183 127** |
| First-25k PEPPER | +111 | +111 | +111 |
| First-50k PEPPER | +2 692 | +3 204 | +3 204 |
| Bucket 2 (50–75 %) PEPPER | +8 798 | +9 153 | +9 153 |
| Bucket 3 (75–100 %) PEPPER | +13 564 | +14 010 | +14 487 |
| Near-limit snapshots (/1000) | 78 | **2** | 80 |
| Peak PEPPER long (official) | +61 | +63 | +65 |
| First-half short (official) | 0 | 0 | 0 |
| First-half short (local 3-day) | −29 | −11 | −16 |
| Expected official PEPPER | observed **+2 135** | projected **+2 400 ± 400** | projected **+2 450 ± 450** |
| Projected lift over F5 | — | ~+150 to +450 | ~+150 to +600 |
| Near-limit cost vs F5 | — | much lower | similar to F5 |

## What the shortlist does NOT claim

- That any new candidate clearly beats F5 on a single official run. The projected lifts are within the noise of a single-point official measurement (F5 officially was +2 135 on one day; a second F5 run could easily be ±300 from that).
- That the family matches buy-and-hold. Local buy-and-hold PEPPER at position_limit=80 is +79 076 (~3× any other candidate); no ramp-limited core-long candidate comes close, because ramp-in costs 5-10 % of the session.
- That the drift assumption holds across Round-2. Everything above is measured on data where the drift held. On a reversing or flat day, the family's expected performance degrades linearly with `base_long`.
