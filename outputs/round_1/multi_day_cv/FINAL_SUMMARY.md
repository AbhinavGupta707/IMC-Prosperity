# Round-1 PEPPER — Multi-Day CV / Stress / Calibration: Final Findings

**Scope:** Phases 0, 2, 3, 4, and Calibration executed end-to-end without
any further IMC uploads. All evaluation rebuilt around the **3-day
1M-tick** harness (`cv_harness.py`) and synthetic stress tapes
(`stress_tapes.py`). Calibration cross-references the 8 official
results we already paid for.

**Bottom line:** On the real PEPPER tape, **`buy_hold_80` is at the
ceiling.** Every additional axis we exercised — opening seed/window,
exec_style, step, overlay trim — produced edge that is statistically
indistinguishable from noise vs `buy_hold_80` (Δ ≤ +33 PEPPER on a
mean of +79,351, fold std ≈ 145). The optionality only appears on a
**stress tape** (`high_vol`), where V3-class strategies extract
+7,000–7,500 over `buy_hold` because the residual overlay finally
bites. Both lose −80,000 on a `reversed` drift day; nothing in the
candidate pool currently protects against that.

---

## 1. What was actually executed

| Phase | Inputs | Output | Cost |
|---|---|---|---|
| **0** Baseline 3-day CV | `buy_hold_80`, `V3_nearhold`, `V2_clean` | `phase2_sweep.log` rows for controls | 3 sims |
| **2** Opening-seed sweep | 53 candidates × {seed, win, exec, step} grid | `phase2_opening_sweep.csv`, `phase2_sweep.log` | 168 sims (303.6 s) |
| **3** Overlay diagnostics | trim_thresh ∈ {2,3,4,5,6,8,10,12} on real days | `phase3_overlay.log` | per-tick scan, no sims |
| **4** Stress tapes | 4 candidates × 7 scenarios (3 real + 4 synth) | `phase4_stress.log`, 4 stress CSVs in `data/raw/round_1_stress/` | 28 sims (50.0 s) |
| **Calibration** | All 8 already-uploaded variants vs proxy | `phase_calibration.log` | re-replay only |

Total: ~6 minutes of sims + ~1 minute of analytic scan. Zero IMC
upload spend, zero dependence on day-0 100k proxy as the primary
yardstick.

---

## 2. Phase 0 — buy_hold_80 sets the ceiling

Across days −2 / −1 / 0 (each 1M ticks at 100-tick cadence):

| Strategy | Mean | Min | Max | Std |
|---|---:|---:|---:|---:|
| `C_buyhold_80` | **+79,351.3** | +79,192 | +79,543 | 145.1 |
| `C_v3_nearhold` | +79,381.3 | +79,204 | +79,549 | 141.0 |
| `C_v2_clean` | +59,333.2 | +58,752 | +60,033 | 529.5 |

- V3 beats buy_hold by **+30 mean PEPPER** — i.e. ~0.04 % of the
  total. That is well inside the per-day fold std (±145).
- V2_clean's seed=60/floor=0 design surrenders ~20,000 on every day —
  the worst result in the entire pool. Its only justification was the
  proxy; on 1M ticks it is dominated.
- Theoretical max position-only PnL ≈ 80 × (mean drift over day) ≈
  +80,000. Buy_hold captures **99.2 %**.

**Sense check:** The 3-day fold std (145) is the same order as the V3
edge (30). Any strategy that simply varies opening behaviour cannot
clear noise on these tapes. This is the single most important
finding of the whole pass.

---

## 3. Phase 2 — Opening-seed grid: top of pool is noise

56 opening-axis candidates (seeds 60/65/70/75/80, windows
0/200/500/1000, exec ∈ {taker, hybrid}, step ∈ {4, 8, 12, 16}). Top
candidate `P2_s65_w0500_hybrid` and 3 ties: **+79,384.7 mean**, +33
above buy_hold and +3 above V3. Same per-day fingerprints (+79,558 /
+79,205 / +79,391) — all tied groups share the same equilibrium
position, just reached via different opening choices.

Useful gradients:

- **`win=0` is bad.** Forces the seed to fire on tick 1 at the worst
  available ask. Mean drops by ~1,300 PEPPER vs `win=500/1000`.
- **`hybrid` ≥ `taker`** by 3 PEPPER on the top candidates (within
  noise). Both work; hybrid avoids one or two unnecessary aggressions
  on day 0.
- **step ∈ {8, 12}** equivalent within noise; **step=4** unchanged
  (saturated by limit); **step=16** identical when seeded, slightly
  worse without a seed because the strategy can't level back up
  inside the day.
- **seed ∈ {65, 70}** marginally beats {75, 80}: a +3 to +6 PEPPER
  edge on day 0 only, again inside fold std. The mechanism is that
  smaller seeds leave headroom for the residual scaler to add into
  shallow dips before saturation.

**Sense check:** Bottom-5 list is dominated by `win=0` runs that
trigger market-order seeding into the open. The signed gradient is
exactly what we would predict mechanically — confidence in the
harness is high.

---

## 4. Phase 3 — Tactical overlay is dead on real data

Counted, per real day, how often signed_residual (`mid − wall_mid`)
exceeded ±trim_thresh, and the gross capture if every fire collected
the |residual| in PnL minus a fixed 2-tick round-trip cost. Higher
thresholds → fewer fires → less noise penalty.

| trim_thresh | Fires (3 days, 27,600 ticks) | Fire-rate | Net capture (3 days) |
|---:|---:|---:|---:|
| 2 | 1,220 | 4.42 % | **−12,503** |
| 3 | 996 | 3.61 % | −12,219 |
| 4 | 910 | 3.30 % | −14,318 |
| 5 | 420 | 1.52 % | −7,366 |
| 6 | 92 | 0.33 % | −1,624 |
| **8** | **0** | **0.00 %** | **0** |
| 10 | 0 | 0.00 % | 0 |
| 12 | 0 | 0.00 % | 0 |

- The PEPPER residual distribution on real days simply **does not
  reach ±8 ticks** within the 100-tick scanning cadence.
- Every threshold ≤ 6 loses money once you charge a realistic
  round-trip cost: gross capture is dwarfed by gross spend.
- V3's `trim_thresh = 8.0` is therefore equivalent to "overlay off"
  on real days — which is **exactly why V3 ≈ buy_hold ≈ pool ceiling**.

**Sense check:** Re-derives V3's headline result from a different
angle. The overlay is a free option only because it never fires on
real data; it neither helps nor hurts.

---

## 5. Phase 4 — Stress tapes reveal latent optionality

4 candidates × 4 synthetic 1M-tick tapes built by mutating only the
mid trajectory of day −2 (book structure preserved exactly). The
stress functions are in `stress_tapes.py`.

| Candidate | real d−2 | real d−1 | real d0 | flat | reversed | high_vol | stepped |
|---|---:|---:|---:|---:|---:|---:|---:|
| `buy_hold_80` | +79,543 | +79,192 | +79,319 | **−457** | **−80,450** | +79,697 | −457 |
| `V3_nearhold` | +79,549 | +79,204 | +79,391 | −451 | −80,431 | **+86,838** | −451 |
| `P2_top_hybrid` (seed=65, w=500) | +79,558 | +79,205 | +79,391 | −451 | −80,431 | +86,638 | −441 |
| `V_defensive_floor70` (V3 + floor=70) | +79,549 | +79,204 | +79,391 | −451 | −80,431 | +86,734 | −451 |

Reading:

- **Real days:** V3-family ≈ buy_hold (within noise). Confirms
  Phase 0/2 finding.
- **`flat`** (drift component subtracted): all candidates land
  near 0. The position-only PnL channel is the dominant source of
  edge — confirmed.
- **`reversed`** (slope inverted): catastrophic for everything.
  Buy_hold loses −80,450; V3 loses −80,431. The 19-PEPPER difference
  is V3's overlay scratching a few ticks back; nothing in the pool
  reverses, hedges, or floors. This is the single real risk of the
  whole strategy family.
- **`high_vol`** (residual ×3, drift unchanged): V3-family extracts
  **+7,141** over buy_hold. V3 specifically is the best of the three
  overlay variants tested. This is the one regime where the overlay
  is positively load-bearing.
- **`stepped`** (drift +slope first half, −slope second half): all
  candidates effectively round-trip to ~−450 because the position
  channel cancels. V3-family loses 0–10 PEPPER vs buy_hold to overlay
  noise.

**Sense check:**
- Buy_hold's `flat` and `stepped` results agree (both −457, since
  drift is symmetrically annulled in both).
- `reversed` matches expectation for a position-long strategy at
  +80 against a −1,000-point move (≈ 80 × −1,000 = −80,000 plus
  carry).
- The `high_vol` boost magnitude (~+7,000 PEPPER) is consistent with
  3× residual amplification firing the V3 trim_thresh=8 overlay
  thousands of times instead of zero.

---

## 6. Calibration — proxy → official mapping by family

8 already-uploaded variants. Day-0 [0..99,900] proxy vs official
PnL:

| variant | proxy | official | Δ | ratio | family |
|---|---:|---:|---:|---:|---|
| baseline | +2,394 | +1,444 | −950 | 0.60 | MM |
| promoted | +2,394 | +1,797 | −597 | 0.75 | MM |
| alt | +2,394 | +2,057 | −337 | 0.86 | MM |
| h1 | +2,394 | +1,797 | −597 | 0.75 | MM |
| f5 | +3,912 | +2,135 | −1,777 | 0.55 | MM |
| **v2_clean** | +5,473 | +5,426 | **−47** | 0.99 | SEEDED |
| **buy_hold** | +7,279 | +7,286 | **+7** | 1.00 | BUYHOLD |
| **v3** | +7,351 | +7,259 | **−92** | 0.99 | SEEDED |

Per-family linear regression `official = slope × proxy + intercept`:

- **MM (n=5):** `official = 0.238 × proxy + 1,204`. Mean |residual|
  132, max 330. Slope < 1 — the local replay over-credits MM-family
  fills.
- **SEEDED (n=2):** `official = 0.976 × proxy + 86`. Both points lie
  exactly on the line (n=2; see warning below). Slope ≈ 1.
- **BUYHOLD (n=1):** ratio 1.001. Treat as 1:1.
- **Global (n=8):** `0.115 × proxy − 224`. Mean |residual| 336, max
  1,189. The pooled fit is misleading; **always split by family.**

**Implications:**
- For seeded/buy_hold candidates, the **3-day 1M-tick mean is
  directly comparable to expected official PnL** at 1:1 ± a few
  hundred. We do not need to re-uploadto rank seeded variants —
  that is the entire reason this pass was worthwhile.
- For MM-family candidates, the proxy is broken (slope 0.24): any
  future MM tweak must be tested against actual upload, not proxy.
- The SEEDED n=2 fit is fragile by definition. A third seeded
  upload (e.g. `P2_top_hybrid` if we choose to spend a slot) would
  collapse or confirm the linearity. We do not need to spend it
  unless we want to ship that variant.

---

## 7. Shortlist and what to ship next

We have three meaningfully distinct candidates, all within fold noise
of each other on real data:

| Rank | Candidate | 3-day mean | Real-data risk | Stress optionality | Bundle ready? |
|---:|---|---:|---|---|---|
| 1 | **`buy_hold_80`** (already uploaded) | +79,351 | None beyond reversed-drift catastrophe | None — flat on `high_vol` | Yes (`trader_round1_test.py`) |
| 2 | **`V3_nearhold`** (already uploaded) | +79,381 | Indistinguishable from buy_hold on real | **+7,141 vs buy_hold on `high_vol`** | Yes (`trader_round1_v3_nearhold.py`) |
| 3 | `P2_top_hybrid` (seed=65, win=500, hybrid, step=8) — NOT shipped | +79,385 | +3 vs V3 (noise) | +6,941 vs buy_hold on `high_vol` (−200 vs V3) | No |

**Recommendation: do not spend another upload slot.**

Reasoning:

1. Both `buy_hold_80` and `V3_nearhold` are already on the IMC
   leaderboard at known PnLs (+7,286 and +7,259 respectively on
   day 0; ~+8,200 total). The 1M-tick test is a different tape, but
   the proxy↔official calibration confirms the seeded family scores
   ~1:1, so our 1M-tick estimates **are** the expected-final-score
   estimates.
2. `P2_top_hybrid` would be a third seeded data point worth +3 PEPPER
   on the mean — unequivocally inside fold noise. We would burn an
   upload slot for nothing observable in the official scoring
   resolution.
3. The only reason to upload anything else is to **buy a third
   seeded calibration point** (collapse the n=2 fit risk). Worth
   doing only if more uploads are cheap; not worth doing for PnL.
4. **No candidate in the pool defends against `reversed` drift.** No
   upload of the current shortlist can change that. If the IMC test
   tape contains a true reversal we are −80k on PEPPER regardless of
   which of these we ship.

If forced to choose **one** for the final test:

- **If you weight upside / believe day-of test will have at least
  some elevated-vol regime: ship `V3_nearhold`.** It dominates
  buy_hold on `high_vol` by +7,000 and ties on real days. Its
  overlay is provably inert on real-tape statistics, so the
  optionality is free downside-wise.
- **If you weight purity / minimum surface area: ship `buy_hold_80`.**
  Cleaner code, no overlay regret, identical real-day PnL.

V3 strictly dominates buy_hold on the candidate-vs-candidate matrix
across {real-3, flat, reversed, high_vol, stepped}, by 0 to +7,000
PEPPER and never by less than 0. **`V3_nearhold` is the recommended
final shipment.**

---

## 8. Risks and known limitations

1. **n=2 SEEDED calibration.** The 1:1 mapping is true for V2_clean
   and V3 only. A 1M-tick test that triggers different mid behaviour
   could change the slope. Mitigation: the candidate sits at a
   stable equilibrium (+80) for >99 % of ticks, so most of its PnL is
   position-channel, not fill-channel; the dominant component is
   exactly what scales linearly.
2. **Reversed-drift catastrophe.** −80k on a 1,000-point reversal,
   no protective mechanism in the shortlist. **No upload slot will
   change this** with the current strategy family. A meaningful fix
   requires a directional regime detector and a position floor that
   actually goes negative — a separate research arc, not part of
   this pass.
3. **Stress tapes are mid-mutations of day −2 only.** Book volume,
   spread, and order-arrival timing are the day −2 tape. The
   stressed scenarios stress price-path only. A genuine regime
   change in liquidity is not modelled.
4. **Proxy MM family is broken.** Any future MM-family edit needs
   either a 3-day 1M-tick run or an actual upload; the day-0 100k
   proxy underestimates MM PnL by 14–45 %.
5. **Fold std ≈ 145 PEPPER.** Anything claiming a smaller edge on the
   3-day mean is noise. The strategy-search resolution floor is
   higher than every gradient in the Phase 2 grid.

---

## 9. What we did NOT do (and why)

- **Phase 1 (full hyperparameter sweep beyond opening axis).** Phase
  3's null result on the overlay axis collapsed the strategy space:
  there is no overlay setting on real data that separates from
  buy_hold within the candidate frame. A wider hyperparam sweep
  would only have re-scored the noise band.
- **Cross-day generalisation tests beyond LOOCV.** All 3 training
  days are structurally identical (same drift slope, R²=1.000000
  per the day fits). Leave-one-out is not informative.
- **New strategy families.** Mean-reversion / scaling-out / regime
  detectors not in scope for "complete in one go without uploading".
  These are genuinely the next frontier if we get a new round of
  data with a different drift regime.

---

## 10. Files written by this pass

- `outputs/round_1/multi_day_cv/cv_harness.py` — 3-day evaluator with
  Candidate dataclass, base_engine() factory, per-family CSV emitter.
- `outputs/round_1/multi_day_cv/stress_tapes.py` — synthetic tape
  generator (flat / reversed / high_vol / stepped).
- `outputs/round_1/multi_day_cv/phase2_opening_sweep.csv` — 56-row
  candidate table sorted by 3-day mean PEPPER PnL.
- `outputs/round_1/multi_day_cv/phase2_sweep.log` — full sweep log
  with top-20 / bottom-5 / fixed-axis slice.
- `outputs/round_1/multi_day_cv/phase3_overlay.log` — per-day
  threshold scan + 3-day totals + fire-rate per threshold.
- `outputs/round_1/multi_day_cv/phase4_stress.log` — 4×7 stress
  matrix.
- `outputs/round_1/multi_day_cv/phase_calibration.log` — proxy /
  official table + per-family OLS fits.
- `data/raw/round_1_stress/prices_{flat,reversed,high_vol,stepped}.csv`
  — 4 synthetic 1M-tick tapes used by Phase 4.

No source-code changes outside `outputs/round_1/multi_day_cv/`. No
new submission bundles. No new tests required (the harness is a
research script that imports already-tested modules).

---

## 11. Single-paragraph summary

Buy-and-hold at the position cap captures 99.2 % of the available
1M-tick PEPPER edge on every training day. Every variation we tested
on the opening axis lands within fold noise (±145 PEPPER) of that
ceiling, including the V3_nearhold variant we have already uploaded.
The tactical overlay V3 carries does not fire on real data (the
residual distribution never crosses ±8), so V3 is functionally
equivalent to buy_hold on real days — but the same overlay scoops
+7,141 PEPPER over buy_hold on a synthetic high-volatility tape, so
V3 is a strict superset. Calibration over 8 already-uploaded variants
shows seeded-family local PnL maps to official ~1:1, so our 3-day
1M-tick estimates are the expected final scores. Recommendation:
**ship `V3_nearhold` as the final-test candidate**; do not spend
further upload slots on the current shortlist; accept that no member
of this pool defends against a reversed-drift regime.
