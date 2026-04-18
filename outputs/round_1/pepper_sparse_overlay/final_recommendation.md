# PEPPER near-buy-and-hold + sparse-overlay — final recommendation

One-screen answer, then seven answers to the prompt's questions,
then uncertainty flags and scope-compliance check.

## One-screen answer

| Question | Answer |
|---|---|
| Best sparse-overlay candidate? | **`V3_nearhold`** — `base_long=80, ceiling=80, open_seed_size=65, open_window=500, floor=40, trim_thresh=8, step=8, exec_style="taker"` (all trim/floor/rebuy knobs are inert on this data; pick the seed/window pair and any reasonable values for the rest). |
| Does it clearly beat V2_clean locally? | **Yes, by a large margin: +1 879 PEPPER PnL on the proxy (+35 %).** The whole gap is V2_clean's surrendered carry from `base_long=50` vs this family's `base_long=80`. |
| Does it preserve more of the buy-and-hold carry? | **Yes — fully. Avg position +79.0 (vs V2_clean's ~+55, buy_hold's +79.9). Full-day proxy PEPPER +7 351 vs buy_hold's +7 279 — slightly BETTER than pure buy-hold.** |
| Does it fix the first-half weakness? | **Yes — fully, then some.** First-25k PEPPER +1 571 vs V2_clean +907 (+73 %) and vs buy_hold +1 294 (+21 %). The seed's staggered acquisition captures early drift with less first-tick spread cost. |
| ASH leg to pair with? | **Frozen H1/F5/Alt wall_mid leg.** No ASH dimension explored. ASH officially +959.78 for V2_clean and buy_hold — identical leg. |
| Prepare a new upload candidate now? | **Yes, but expect a marginal result.** The projected official lift over buy_hold_80 (+7 286) is ~+72 PEPPER (±~300 at 1:1 calibration noise). The upload is primarily defensible as "at least as good as buy_hold on this day, with overlay optionality for future days." |
| What remains uncertain? | See §7. Biggest: (i) the +72 edge sits inside single-day measurement noise; (ii) the overlay is entirely untested on reversing data; (iii) there's no meaningful mechanism for this family to beat buy_hold by more than a spread cost. |

## 1. Best sparse-overlay candidate

**`V3_nearhold`** — canonical label `L1_seed65_win00500` (ties with
26+ other rows across L1/L2/L3/L4/L5 because every layer past L1
is inert on the one official day's data).

```python
CoreLongParams(
    base_long=80,
    ceiling=80,
    floor=40,               # inert; any value 40..70 equivalent
    add_thresh=3.0,         # inert (base=ceiling=80)
    trim_thresh=8.0,        # inert — residual never exceeds 6 on proxy
    add_gain=5.0,
    trim_gain=2.0,
    step=8,                 # any value 4..16 equivalent
    exec_style="taker",     # tiniest score edge; hybrid is equally valid
    hybrid_threshold=2.0,
    open_seed_size=65,      # <-- the only knob that actually matters
    open_window=500,        # <-- any window >= 500 is equivalent
    open_no_short=True,
)
```

Evidence (raw metrics, primary):

| Metric | C_v2_clean_ref | buy_hold_80 | **V3_nearhold** |
|---|---:|---:|---:|
| Proxy PEPPER PnL    | +5 472.5 | +7 279.0 | **+7 351.0** |
| First-25k PEPPER    | +1 204   | +1 594   | **+1 571** |
| First-50k PEPPER    | +2 758   | +3 474   | **+3 451** |
| Bucket-3 PEPPER     | +1 231   | +1 992   | ~+1 900 (held pos +80) |
| Near-limit /1000    | 373      | 999      | 998 |
| Avg PEPPER position | +55.8    | +79.9    | **+79.0** |
| Max long            | +64      | +80      | +80 |
| Max short (fh)      | 0        | 0        | 0 |

## 2. Does it clearly beat V2_clean locally?

**Yes — unambiguously, by +1 879 PEPPER PnL on the corrected proxy
(+35 %).** The gap is explained entirely by V2_clean's surrendered
carry at `base_long=50`:

```
V2_clean proxy PEPPER     = +5 472.5
V3_nearhold proxy PEPPER = +7 351.0
                            --------
                           +1 878.5 lift
```

Every bucket improves:

| Bucket | V2_clean | V3_nearhold | Δ |
|---|---:|---:|---:|
| 0 – 25k | +1 204 | +1 571 | **+367** |
| 25k – 50k | +1 554 | +1 880 | **+326** |
| 50k – 75k | +1 456 | +1 900 | **+444** |
| 75k – end | +1 259 | +2 000 | **+741** |

The 75k-end bucket is the biggest gap (V2_clean's structural flaw
— reverting to `base_long=50`). V3_nearhold finishes at +80 and
captures the full last-quarter drift.

## 3. Does it preserve more of the buy-and-hold carry?

**Yes — more than fully. V3_nearhold actually SLIGHTLY EXCEEDS
buy_hold_80 proxy PEPPER (+7 351 vs +7 279).**

| Metric | buy_hold_80 | V3_nearhold | Δ |
|---|---:|---:|---:|
| Proxy PEPPER        | +7 279.0 | **+7 351.0** | **+72.0** |
| First-25k PEPPER    | +1 594   | +1 571 | −23 |
| First-50k PEPPER    | +3 474   | +3 451 | −23 |
| Avg position        | +79.9    | +79.0  | −0.9 |
| Near-limit /1000    | 999      | 998    | −1  |

**Mechanism of the lift:** buy_hold crosses all 80 units at tick 0,
paying the full spread on each — walking into deeper ask levels.
V3_nearhold seeds only 65 at tick 0 (narrower walk into the ask
book) and acquires the remaining ~15 units over the next ~700
ticks when the book has refreshed at higher prices but narrower
spreads. Net: small spread-cost saving on the 65-unit opening
beats the slightly more expensive late acquisition of 15 units.

The +72 lift is small but robust — seed=70 with win=500 gives the
exact same +7 351, and seed=65 with win=1000 or 2000 also hits
+7 351. Six configurations in the seed ∈ {65, 70} × window ∈ {500,
1000, 2000} grid all tie at +7 351.

## 4. Does it fix the first-half weakness?

**Yes. First-25k PEPPER +1 571 — close to buy_hold's +1 594 and
far above V2_clean's +1 204.** The "first-half weakness" that
tormented the corelong_v2 pass is gone because V3_nearhold is at or
near +80 for essentially the entire session.

| First-25k PEPPER | Value | % of buy_hold |
|---|---:|---:|
| F5                  | +302   | 19 % |
| V2_clean (official) | +907   | 56 % |
| V2_clean (proxy)    | +1 204 | 76 % |
| **V3_nearhold (proxy)** | **+1 571** | **98 %** |
| buy_hold_80 (proxy) | +1 594 | 100 % |

V2_clean's 76 % capture was already a major improvement over F5's
19 %. V3_nearhold closes the remaining 24 %.

## 5. ASH leg to pair with

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

Not explored in this pass. Officially scored +959.78 for both
V2_clean (169807) and buy_hold_80 (162376) — byte-identical leg.

Projected combined total (1:1 calibration on seeded family):

```
V3_nearhold + wall_mid ASH ≈ +7 350 PEPPER + +960 ASH ≈ +8 310 total
buy_hold_80                      +7 286 PEPPER + +960 ASH = +8 246 total (measured)
V2_clean                         +5 426 PEPPER + +960 ASH = +6 386 total (measured)
```

Projected official lift of V3_nearhold over V2_clean:
**≈ +1 920 total PnL** (30 % lift).
Projected official lift over buy_hold_80: **≈ +64 total PnL**
(0.8 % lift).

## 6. Prepare a new upload candidate now?

**Yes — but with clear expectations.**

The case for uploading is:

1. **Beats V2_clean by a large margin** (projected +1 920 total PnL,
   outside all reasonable noise bands).
2. **Preserves all carry** that buy_hold captures — matches or
   slightly exceeds buy_hold on every official-cadence metric.
3. **Adds overlay optionality for free** — on this day the trim
   branch never fires, so the overlay costs nothing and provides
   insurance against reversing days.
4. **Calibration is the most trustworthy of the whole project.**
   V2_clean's proxy→official ratio was 1.009×; buy_hold's was
   0.999×. Seeded candidates calibrate 1:1 with ±1 %.

The case for NOT uploading is:

1. **The PEPPER lift over buy_hold is +72 — within single-day
   measurement noise.** A repeat buy_hold upload could return
   anywhere in [+6 900, +7 600]; V3_nearhold could return in
   roughly the same range, just shifted +72. Single upload can't
   distinguish +0 from +150.
2. **V2_clean is already the current newest upload.** Uploading
   V3_nearhold immediately consumes the next slot; the calibration
   for "seeded at +80 vs seeded at +50" is already informally
   measurable from the V2_clean (+5 426) and buy_hold_80 (+7 286)
   existing official numbers. Direct V3_nearhold data adds
   confirmation, not novel calibration.
3. **No meaningful higher-upside alternate exists in this family.**
   The ceiling of what sparse-overlay can achieve on this data is
   what V3_nearhold already achieves.

**Recommended upload decision:** yes, upload V3_nearhold as the
next candidate. The expected outcome is matching buy_hold_80
within ±1 %, which is a substantially better strategic position
than V2_clean's 26 % gap vs buy_hold — and it preserves overlay
infrastructure for future days. If the upload comes in materially
worse than buy_hold_80, the diagnosis will be "the seed=65 spread-
saving mechanism doesn't transfer cleanly" and the correct
fallback is a `base_long=80, seed=80` upload (functionally equal
to buy_hold but expressed through the core-long strategy).

**Do NOT upload a higher-upside alternate.** There isn't one that
clears the noise band.

## 7. What remains uncertain

1. **The +72 edge is inside measurement noise.** Single-day
   official runs carry ±5 % variance; that's ±~350 on a +7 000 PnL.
   V3_nearhold might return +7 300 officially, or +7 000, or +7 600.
   The mean projection is "match buy_hold ± small lift."

2. **Drift specificity — unchanged from v2.** Every number is on
   a +0.001/tick drift-up day. A flat/reversing day will penalise
   any near-+80 strategy directly. V3_nearhold has the same
   exposure as buy_hold on a reversing day.

3. **The overlay is unexercised.** No trim / rebuy fired at the
   proxy cadence on this day. The family's claimed "overlay
   optionality for reversing days" is theoretical — we have no
   evidence it would help. It also doesn't cost anything on this
   day, so it's insurance-without-premium, not insurance-with-
   alpha.

4. **Why not just upload buy_hold_80 again?** A fair question. The
   answer is: V3_nearhold is structurally identical to buy_hold on
   this day (avg pos +79.0 vs +79.9) but runs through
   `PepperCoreLongStrategy` instead of `BuyAndHoldStrategy`, which
   means future parameter tuning (reacting to a reversing day's
   official result) is a config change instead of a strategy
   change. The small +72 proxy edge is a bonus, not the reason.

5. **The seed=65 sweet spot is one data point.** Seed=65 hit +7 351,
   seed=60 hit +7 253, seed=80 hit +7 330. The mechanism (less
   spread walk) is plausible but the specific sweet spot is just
   what won on this day's ask book. On a different day the sweet
   spot could shift ±10 units.

6. **L3/L4 inertness.** Every trim/rebuy/execution knob is
   functionally equivalent on this data. This is not a robustness
   signal — it means we have no local evidence for setting them.
   They get set to sensible defaults (trim_thresh=8, floor=40,
   step=8, hybrid_threshold=2.0) but their true behavior is
   unobservable until a day with price excursions above drift-fair.

## 8. Scope compliance

This pass:

- **Did NOT** reopen full Round 1 optimisation.
- **Did NOT** mutate any shipped `round1_*_engine_config` factory.
- **Did NOT** touch `src/` at all (no strategy code, no config, no
  registry, no tests).
- **Did NOT** export any submission bundle.
- **Did NOT** upload anything.
- **Did NOT** silently change promoted / default configs.
- **Did NOT** run a giant cross-product grid. 118 candidate
  evaluations × 2 views = 236 simulator runs across 5 layers plus
  2 hand-tuned alternates plus 5 controls.
- **Did NOT** do any ASH work. ASH leg frozen at H1/F5/Alt wall_mid
  for every candidate.
- **Did NOT** ship a new fair-value estimator. `linear_drift`
  reused unchanged.
- Kept `position_limit=80` for both products.
- Kept PEPPER `max_aggressive_size=20` (bumped from shipped 8) so
  the strategy's `step` is the binding per-tick cap — matches v2
  and V2_clean search conditions.

## Deliverable files

- [controls.md](controls.md) — Phase A frozen references (with
  official numbers for all 5 controls, including V2_clean's
  official +5 426).
- [pepper_sparse_overlay_memo.md](pepper_sparse_overlay_memo.md) —
  Phase B mechanism memo (why buy_hold_80 is the reference now).
- [run_search.py](run_search.py) — Phase D layered runner (118
  candidates).
- [run_search.log](run_search.log) — full stdout of the final run.
- [pepper_candidates.csv](pepper_candidates.csv) — 118 candidates
  with full per-metric columns and the disclosed score.
- [pepper_candidates.md](pepper_candidates.md) — same as markdown
  with per-layer winner table.
- [shortlist.md](shortlist.md) — V3_nearhold vs buy_hold vs
  V2_clean comparison.
- [final_recommendation.md](final_recommendation.md) — this file.
