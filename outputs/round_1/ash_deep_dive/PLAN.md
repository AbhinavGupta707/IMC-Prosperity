# ASH Edge-Extraction — Deep Dive Plan

**Owner:** this pass is ASH-only. PEPPER is frozen.
**Author / author-date:** 2026-04-16, round-1 research branch.
**Status:** plan, not started. Supersedes nothing; parallel to the Phase-10
`outputs/round_1/ash_target/` pass (which is closed with a "no-ship"
verdict — see its `final_recommendation.md`).

This plan spells out exactly what will be built, which candidates
will be evaluated, how they will be measured, and which will be
promoted to official upload. Every surface named here is
research-only — no edits to any shipped `round1_*_engine_config`
factory, no changes to `STRATEGY_REGISTRY` or `LIVE_MODULE_ORDER`.

---

## 0. Ground rules

### 0.1 Pins

- **PEPPER leg**: `BuyAndHoldStrategy`, `max_aggressive_size=80`,
  `position_limit=80`, via `round1_test_engine_config()`-equivalent.
  This is the observed upper envelope (+7 286 official, +79 351 on
  3-day CV mean per `outputs/round_1/multi_day_cv/FINAL_SUMMARY.md`).
  Every ASH candidate in this plan is evaluated **with this exact
  PEPPER leg**, so the PEPPER-side PnL is constant across runs and
  the ASH delta is clean.
- **ASH reference**: `C_h1_alt` — `wall_mid`, fallbacks `(mid,
  microprice)`, `anchor_price=10000` (fallback only), `maker_edge=1.5`,
  `taker_edge=0.5`, `quote_size=5`, `max_aggressive_size=10`,
  `inventory_skew=4.0`, `flatten_threshold=0.7`, `history_length=48`,
  `position_limit=80`. Target to beat: **+982** on the official
  day (100k ticks), **+7 747** on the 3-day 1M-tick local CV.

### 0.2 No-live-engine policy

- No edits to `src/core/config.py`'s shipped `round1_*` factories.
- No edits to `STRATEGY_REGISTRY`, `LIVE_MODULE_ORDER`, or any
  `export_round1_*` bundle builder.
- Every new strategy lands in `src/strategies/ash_*.py` and is only
  wired up by the phase-specific runners under
  `outputs/round_1/ash_deep_dive/`. This mirrors the Phase-10
  protocol that kept `ash_target_position.py` isolated from the
  live path.
- New analysis module at `src/analysis/ash_calibration.py`. New test
  files at `tests/test_ash_*.py`. Every research strategy gets
  unit tests before any sim run.

### 0.3 Acceptance thresholds

- **Keep** (eligible for further optimization / hybridization):
  candidate's 3-day CV mean ASH PnL is within **−150 of C_h1_alt**
  *and* loses on at most one fold by more than −300, *or* beats
  C_h1_alt on ≥2/3 folds regardless of mean.
- **Flag-before-ship**: candidate loses by ≥ −300 on *any* Phase-E
  stress tape or has markout sign opposite to C_h1_alt's at t+20.
  Flagged candidates still ship (uploads are unlimited) but their
  Phase-F memo documents the risk.
- **Auto-kill**: candidate's 3-day CV mean ASH PnL is ≤ −500 vs
  C_h1_alt *and* at least one fold is ≤ −600. Drop from the tree.

### 0.4 Evidence calibration (per `CLAUDE.md`)

No categorical claims from local replay. Every phase memo uses the
"under current local replay" language. Large aggregate improvements
trigger the cross-slice + timestamp-visual sanity check before
parameter refinement.

---

## 1. Scope: the six open levers

Recap from the 2026-04-16 conversation:

| # | Lever | Paper backing | Why ASH |
|---|---|---|---|
| L1 | **Fair-value primary** | Stoikov 2009 (microprice) | wall_mid is the Phase-1 winner; may be dominated by a microprice-family estimator on a narrow-residual regime |
| L2 | **Symmetric edge widths** | (empirical) | Phase-6/8.5 explored a small neighborhood; re-visit with the Phase-A calibration prior |
| L3 | **Inventory-skew shape** | Avellaneda–Stoikov 2008 | AS gives a *quadratic* reservation-price term `q·γ·σ²·(T−t)` where our engine uses a *linear* one; there is a closed-form replacement available |
| L4 | **Flatten mechanism** | AS + OU control | Hard-at-0.7 is a discontinuity; AS/OU give a continuous target |
| L5 | **Quote-size skew** | AS inventory risk | Size-side skew is independent of price-side skew; untested |
| L6 | **History length** | (model-hygiene) | `history_length` caps all rolling estimators; re-screen given current FV is wall_mid |

Plus two cross-cutting overlays that don't fit "one lever":

| # | Overlay | Paper | Why ASH |
|---|---|---|---|
| O1 | **Residual alpha-skew** | Cartea–Jaimungal | The −0.6 residual→fwd-return correlation in the dossier IS an alpha signal; adding it additively on top of a symmetric base is a standard CJ result |
| O2 | **Book-imbalance (OFI) gating** | Cont–Stoikov–Talreja 2010 | OFI was not tested in any Round-1 phase; book has 1–2 visible layers so the signal is structurally measurable |
| O3 | **Target-position on residual (Phase-10 v2)** | OU / Avellaneda–Lee | Phase-10's failure modes were (a) saturation at high α, (b) wrong anchor, (c) missing σ scaling. v2 addresses all three |

---

## 2. Phase A — Calibration & diagnostics

**Purpose**: replace parameter guesses with data-measured priors.
**Engineering**: ~300 lines new analysis code + 1 JSON output + 1
memo. **Write fully — no shortcuts** per user direction.

### 2.1 Deliverables

`src/analysis/ash_calibration.py` — new module with these functions:

1. `fit_ou(mid_series, dt=100) -> OUParams` — maximum-likelihood fit of
   `ds = θ·(μ − s)·dt + σ·dW` per day; exports θ (1/ticks), σ
   (ticks/√tick), μ (price-level), half-life, residual RMSE.
2. `fit_fill_intensity(snapshots, fills, offsets) -> FillIntensity` —
   at a grid of maker-edge offsets δ ∈ {0.5, 1.0, 1.5, 2.0, 3.0, 4.0},
   measure hit rate λ(δ) = trades/tick for each offset (via
   simulating the maker-only intent at that offset against the
   historical book). Fit `λ(δ) = A·exp(−k·δ)`; export A, k, R².
3. `fit_ofi_signal(snapshots, horizon_ticks=(1, 5, 20)) -> OFIFit` —
   compute OFI = (Δbid_vol − Δask_vol) as per Cont-Stoikov-Talreja.
   Regress next-H-tick Δmid on OFI; export slope, intercept, R²,
   residual σ for each H.
4. `fit_residual_markout(snapshots, fv_method) -> MarkoutCurve` — for
   each of {wall_mid, microprice, ewma_mid, depth_mid}, bucket
   residuals into deciles and measure mean forward return at t+1/
   t+5/t+20/t+50. Export the curve and the per-estimator σ of
   residuals.
5. `measure_fill_reality(c_h1_alt_local, c_h1_alt_official)` — run
   C_h1_alt on 3-day local, extract maker-fill-count, taker-fill-
   count, fill-size distribution. Compare to the official day's
   56/25 split on ASH (data at
   `outputs/round_1/official_results/analysis/bucket_breakdown.md`).
   Emit a "local-to-official fill-scale multiplier" for each fill
   type. This is what we use to down-weight claimed PnL gains that
   are concentrated in a fill type the official environment
   under-fires.

### 2.2 Output

`outputs/round_1/ash_deep_dive/phase_a/calibration_report.md` with:

- Per-day OU params (θ, σ, μ, half-life) for all 3 days + 1 official.
  Expected ranges per Phase-1 dossier: θ⁻¹ = 3–20 ticks (half-life
  2–14 tick units of 100-step), σ ≈ 4–5 ticks/day, μ ≈ 10 000.
- Fill intensity curve `λ(δ)`: expected shape monotone-decreasing
  in δ, with A ≈ fills/bucket and k ≈ 0.5–1.5.
- OFI R² per horizon: expected small-positive (CST-style R² 0.1–0.3
  even on equities; may be lower on synthetic books with only 1–2
  layers). **If R² < 0.02 at every horizon the OFI lever is
  deprioritized.**
- Markout curve per FV: expected monotonic with residual sign for
  wall_mid, microprice, depth_mid; ewma_mid flatter.
- Fill-reality multiplier: expected local-maker ≈ 0.2× official,
  local-taker ≈ 30× official, given the Phase-10 memo's note on
  fill-model bias.

`outputs/round_1/ash_deep_dive/phase_a/fits.json` — machine-readable
same data, used as a parameter source by Phase-B/C/D runners.

### 2.3 Tests

`tests/test_ash_calibration.py` with synthetic fixtures:
- OU fit on a generated OU path with known (θ, σ, μ) returns params
  within ±5 %.
- Fill-intensity fit on a known Poisson-exponential trace recovers
  k within ±10 %.
- OFI regression on a constructed series with planted signal
  returns R² matching the planted fraction within ±0.03.

### 2.4 Commands

```bash
PYTHONPATH=. .venv/bin/python -m src.analysis.ash_calibration \
    --days -2 -1 0 \
    --fv-methods wall_mid microprice ewma_mid depth_mid \
    --out outputs/round_1/ash_deep_dive/phase_a/
```

**Time**: 1 session.
**Blocking for**: every downstream phase.

---

## 3. Phase B — Single-lever isolation screens

**Purpose**: find each lever's best *shape* (not best parameter);
reject levers whose best setting doesn't meaningfully move the
needle. Every screen holds the other 5 levers at C_h1_alt defaults.

### 3.1 B1 — Fair-value primary

Strategies: pure `MarketMakingStrategy`, only FV method varies.

| Cell | fair_value_method | fallbacks | Notes |
|---|---|---|---|
| B1.1 | `wall_mid` (ref) | `(mid, microprice)` | C_h1_alt baseline |
| B1.2 | `microprice` | `(wall_mid, mid)` | Stoikov 2009 |
| B1.3 | `ewma_mid` | `(wall_mid, mid)` | Phase-6 Promoted default |
| B1.4 | `depth_mid` | `(wall_mid, mid)` | Phase-1 best markout |
| B1.5 | `hybrid_wall_micro` | `(wall_mid, mid)` | Phase-1 |
| B1.6 | `filtered_wall_mid` | `(mid, microprice)` | Phase-1 twin |
| B1.7 | `weighted_mid` | `(wall_mid, mid)` | Phase-1 near-tie |
| B1.8 | `rolling_mid` | `(wall_mid, mid)` | Phase-1 near-tie |

8 cells. Expected runtime: ~25 min on 3-day CV.

### 3.2 B2 — Symmetric edge widths

Hold FV at `wall_mid`.

| maker_edge | taker_edge |
|---|---|
| 1.0, 1.5, 2.0, 2.5 | 0.25, 0.5, 1.0, 1.5 |

4×4 = 16 cells, including C_h1_alt as (1.5, 0.5). Expected runtime:
~50 min.

### 3.3 B3 — Inventory-skew shape

Replace `inventory_skew` scalar with a shape. Requires a tiny
`BaseStrategy` wrapper `ash_skew_shape.py` that only changes the
skew term; everything else delegates to `SignalEngine` defaults.

| Cell | Shape | Parameter |
|---|---|---|
| B3.1 | linear (ref) | coef ∈ {2, 4, 6, 8} |
| B3.2 | AS reservation-price | `r = s − q·γ·σ²·(T−t)`; γ ∈ {0.05, 0.10, 0.20}, σ & T from Phase A |
| B3.3 | tanh-saturating | `skew = coef · tanh(2·q/limit)`; coef ∈ {2, 4, 8} |
| B3.4 | quadratic | `skew = coef · sign(q) · (q/limit)²`; coef ∈ {4, 8, 16} |

4 + 3 + 3 + 3 = 13 cells.

### 3.4 B4 — Flatten mechanism

Hold everything else at C_h1_alt.

| Cell | Mechanism |
|---|---|
| B4.1 | hard-at-0.7 (ref) |
| B4.2 | hard-at-0.6 (tighter) |
| B4.3 | hard-at-0.8 (looser) |
| B4.4 | soft target: add `target = −flat_k·q` continuous term on top of skew; flat_k ∈ {0.2, 0.5, 1.0} |
| B4.5 | AS-continuous: flatten engaged via the AS reservation-price term itself (no discontinuity); the hard threshold is *off* |

1 + 2 + 3 + 1 = 7 cells.

### 3.5 B5 — Quote-size skew

Currently quote_size is constant and only *price* is skewed with
inventory. Test size-side skew.

| Cell | Mechanism |
|---|---|
| B5.1 | constant = 5 (ref) |
| B5.2 | linear: `bid_size = 5·(1 − q/limit)`, `ask_size = 5·(1 + q/limit)`, clipped to [1, 10] |
| B5.3 | AS-optimal: per-side size ∝ `1/(γσ²(T−t))` capped at `max_aggressive_size` |
| B5.4 | step-wise: if `|q/limit| > 0.5`, shrink the "adding" side to 1, grow the "unwinding" side to `max_aggressive_size` |

4 cells.

### 3.6 B6 — History length

Only meaningful for FV estimators that use history. Test with
wall_mid (shallow user) and ewma_mid (deeper user).

| Cell | history_length | FV |
|---|---|---|
| B6.1 | 16 / 32 / 48 / 64 / 96 | wall_mid |
| B6.2 | 16 / 32 / 48 / 64 / 96 | ewma_mid |

10 cells.

### 3.7 B summary

| Lever | Cells |
|---|---|
| B1 | 8 |
| B2 | 16 |
| B3 | 13 |
| B4 | 7 |
| B5 | 4 |
| B6 | 10 |
| **Total** | **58** |

Runtime estimate: ~3.5 hours across the 3-day CV for all cells +
markout analysis. Runs one-shot via
`run_ash_research.py --phase b`.

### 3.8 Phase-B memo deliverable

`outputs/round_1/ash_deep_dive/phase_b/PHASE_B_MEMO.md`:

- Best *shape* per lever (not best parameter). Ties noted.
- Cross-lever redundancy flag: e.g., if B2's best is (1.5, 0.5) and
  B3's AS shape dominates linear, then Phase-C's AS composite
  should NOT also re-sweep edges.
- Markout-sign sanity: reject any Phase-B winner whose t+20 markout
  sign is opposite to C_h1_alt's.
- Fill-mix sanity: weight every Phase-B winner's "gain" by the
  Phase-A fill-reality multiplier, emit "local-gain" vs
  "expected-official-gain" columns side by side.

**Time**: 2 sessions (1 to build + implement, 1 to analyze + memo).

---

## 4. Phase C — Academic composite candidates

Five named, paper-faithful strategies. Each is one new file under
`src/strategies/`, each gets unit tests, each goes through the
3-day CV + stress matrix in Phase E.

### 4.1 C1 — `AshAvellanedaStoikov`

**File**: `src/strategies/ash_avellaneda_stoikov.py`.

Reservation price:
```
r(t, q) = s(t) − q · γ · σ² · (T − t)
```
Optimal half-spread:
```
δ*(t) = γ · σ² · (T − t) / 2 + (1 / γ) · ln(1 + γ / k)
```
Maker bid = `r − δ*`, maker ask = `r + δ*`. Taker thresholds
derived symmetrically from `r`. All else identical to C_h1_alt.

Parameters (all from Phase A):
- γ ∈ {0.05, 0.10, 0.20} (risk aversion)
- σ = day-fitted OU σ
- k = Phase-A fill-intensity exponent
- T = 100 000 - t (remaining episode)

Grid: 3 γ values × 1 (k, σ, T from calibration) = **3 cells**.

### 4.2 C2 — `AshGueant`

**File**: `src/strategies/ash_gueant.py`.

Mean-reversion-aware spread. Guéant-Lehalle-Fernandez-Tapia 2013
shows that under OU dynamics, the AS half-spread shrinks by a
factor involving the mean-reversion speed θ:

```
δ*_MR(t) = δ*_AS(t) · φ(θ · (T − t))
```
where φ is a decreasing function of its argument (faster mean
reversion → tighter spread because inventory risk decays).

Parameters:
- γ ∈ {0.05, 0.10, 0.20}
- θ = Phase-A OU fit
- σ, k, T as C1

Grid: 3 cells.

### 4.3 C3 — `AshCarteaSkew`

**File**: `src/strategies/ash_cartea_skew.py`.

Baseline = C_h1_alt (`wall_mid`, maker=1.5, taker=0.5). Add the
alpha-skew on top:

```
α(t) = (fair(t) − mid(t)) / σ_residual    (z-scored residual)
δ_ask = δ_maker − β · α(t)
δ_bid = δ_maker + β · α(t)
```
Net effect: quotes skew toward the direction the residual
predicts (CJ prescription for an MM with an exogenous short-term
alpha signal).

Parameters:
- β ∈ {0.5, 1.0, 1.5, 2.0} (in ticks — β=1 means ±σ_resid of
  residual moves the quote by 1 tick asymmetrically)

Grid: 4 cells.

### 4.4 C4 — `AshOFIGate`

**File**: `src/strategies/ash_ofi_gate.py`.

Baseline = C_h1_alt. Add OFI-gate on the taker threshold:

```
OFI(t) = (ΔbidV(t) − ΔaskV(t))   (Cont-Stoikov-Talreja definition, 1-tick lag)
If OFI > +OFI_thresh and sign(gap) = +1:
    # Buyer-pressure; don't cross up — wait
    buy_below = None
If OFI < −OFI_thresh and sign(gap) = −1:
    # Seller-pressure; don't cross down — wait
    sell_above = None
```

Optional maker-side mirror (skew the maker quote asymmetrically by
OFI sign). Default off in the first cell, on in a second.

Parameters:
- OFI_thresh ∈ {calibrated σ, 2σ} from Phase A

Grid: 2 thresh × 2 maker-mirror-on/off = **4 cells**.

### 4.5 C5 — `AshTargetPositionV2`

**File**: `src/strategies/ash_target_position.py` — MODIFY
existing Phase-10 scaffold. The three fixes:

1. **EWMA anchor**: `mean_source="ewma"` (new option) computed
   over a user-tunable window τ. Addresses Phase-10 issue #6 (anchor
   = hard 10 000 is too blunt).
2. **σ-aware α**: `α_effective = α_base · (σ_ref / σ_current)` so
   the target-position pull scales inversely with realized residual
   volatility. Addresses Phase-10 issue #2 (fixed α saturates in
   low-σ regimes).
3. **Flatten-integrated cap**: clip target to
   `flatten_threshold × limit`, not a separate `cap`. The flatten
   valve then engages *before* any single-tick overshoot.
   Addresses Phase-10 issue #4 (saturation at 334/1000 near-limit).

Parameters (guided by Phase A):
- EWMA τ ∈ {500, 2000, 8000} ticks
- α_base ∈ {2.0, 3.0} (v.s. the Phase-10 range of {5, 8, 12})
- dead_zone d ∈ {2, 3, 4}
- exec_style ∈ {hybrid, maker}
- hybrid_threshold ∈ {2.0, 3.0, 4.0}

Selective grid: 3 τ × 2 α × 3 d × 2 style × 3 thresh = 108 cells —
cut down by locking to 1 α-d pair per style: **~12 cells**.

### 4.6 Phase-C summary

| Strategy | Cells |
|---|---|
| C1 AS | 3 |
| C2 Guéant | 3 |
| C3 Cartea | 4 |
| C4 OFI-gate | 4 |
| C5 Target-v2 | ~12 |
| **Total** | **~26** |

Engineering: 5 new files + 5 test files + runner extension.
Runtime: ~1.5 hours of sims.

**Time**: 2 sessions (1 implement C1+C2 and test, 1 implement C3+C4+C5).

---

## 5. Phase D — Hybrids

Takes the best-shape winners from Phase B (one per lever) and best
academic mechanism from Phase C, and composes 3–5 candidates:

- **D1** = C_h1_alt + C3 (Cartea skew). Cheapest hybrid. If the
  residual alpha is real this should show up here.
- **D2** = C1 (AS reservation) + C4 (OFI gate). Structural +
  gating.
- **D3** = C2 (Guéant spread) + C3 (Cartea skew) + C1 reservation
  price. The "fullest stack".
- **D4** = C5 (Target-v2) + C4 (OFI gate). Mean-reversion capture +
  adverse-selection protection.
- **D5** = C_h1_alt + best B3 skew shape + best B5 size skew. The
  "no-paper" hybrid that just stacks empirical winners.

Engineering: composition only. ~1 file of glue, 0 new unit tests
beyond end-to-end smoke.

**Time**: 1 session.

---

## 6. Phase E — ASH-specific stress tapes

The existing `outputs/round_1/multi_day_cv/stress_tapes.py` ONLY
mutates PEPPER rows (see its loop at lines 76–88: rows whose
`product != "INTARIAN_PEPPER_ROOT"` are passed through unchanged).
For this pass we need ASH stress tapes.

### 6.1 New generator

`outputs/round_1/ash_deep_dive/ash_stress_tapes.py`, generates:

| Tape | Perturbation |
|---|---|
| `ash_flat` | Zero oscillation — replace mid with constant 10000; bid/ask shifted accordingly |
| `ash_amp3x` | Oscillation × 3 (similar to PEPPER's `high_vol`) — residuals amplified, drift unchanged |
| `ash_narrow_spread` | Spread compressed 16 → 12 ticks (pull top-of-book toward the middle by 2 ticks each side) |
| `ash_thin_book` | Level-1 volumes × 0.5 (fill-throttling regime); L2 unchanged |
| `ash_anchor_shift` | Mid anchor steps 10000 → 10025 at t=50k (regime-shift robustness) |
| `ash_one_sided_heavy` | 2× rate of one-sided snapshots (exercise the fallback chain; sampled by dropping one side at random 8%→16%) |

6 tapes, each 1M ticks. Generated offline, deposited under
`data/raw/round_1_ash_stress/prices_<tape>.csv`.

### 6.2 Stress sweep

Every surviving candidate from Phase B/C/D runs against each of the
6 tapes + 3 real days = 9 replays. Emit a matrix CSV at
`phase_e/stress_matrix.csv` with ASH PnL per tape per candidate.

**Kill-before-ship**: candidate loses ≥ −300 on any single tape
vs C_h1_alt *with no mitigation*. Soft-flag if loss is −150–300.

**Time**: 1 session (tape generator + sweep + memo).

---

## 7. Phase F — Official submission cohort

Uploads are unlimited. The acceptance threshold in §0.3 is
intentionally wide so we get ground-truth data points on as many
mechanism classes as possible.

### 7.1 Batch plan

| Batch | Candidates | Purpose |
|---|---|---|
| **F1 — Control refresh** | 1 candidate: C_h1_alt re-uploaded on this plan's exact PEPPER pin | Anchor a new "ASH-only delta" frame. Since existing C_h1_alt was uploaded with *V3_nearhold* PEPPER not buy_hold, this gives us an ASH-with-buy_hold reference |
| **F2 — Phase-B winners** | ≤3 candidates (one best per lever whose Phase-E matrix passes) | Are empirical-shape wins real on official? |
| **F3 — Phase-C composites** | ≤5 (C1 best γ, C2 best γ, C3 best β, C4 best thresh, C5 best τ) | Does each paper mechanism show up on official? |
| **F4 — Phase-D hybrids** | ≤5 (D1–D5) | Does stacking win? |
| **Upper bound** | ~14 official slots |  |

Each upload gets its own bundle under
`outputs/submissions/round_1/limit_80/ash_deep_dive/<candidate>/`,
its own `*.meta.md`, and its own line in the proxy-vs-official
calibration table.

### 7.2 Proxy-vs-official calibration table

Key secondary deliverable. After F1–F4 land:

`outputs/round_1/ash_deep_dive/phase_f/proxy_vs_official.md` —
each candidate gets a row with columns:
- Predicted ASH PnL (3-day local mean)
- Observed ASH PnL (official)
- Delta, delta%
- Mechanism class (baseline / B / C / D)
- Fill-mix shift (local maker% vs official maker%)

This is the first time we'd have a multi-mechanism calibration
curve, not a single data point. It tells us *which mechanism
classes are trustworthy in local and which are not* — direct input
into any future round's evaluation methodology.

**Time**: 1 session per batch (bundle + upload + analyze result),
so 4 sessions for F1–F4.

---

## 8. Engineering surface this plan will create

```
src/analysis/
  __init__.py                                (may already exist)
  ash_calibration.py                         NEW  — Phase A
tests/
  test_ash_calibration.py                    NEW  — Phase A
  test_ash_avellaneda_stoikov.py             NEW  — Phase C
  test_ash_gueant.py                         NEW  — Phase C
  test_ash_cartea_skew.py                    NEW  — Phase C
  test_ash_ofi_gate.py                       NEW  — Phase C
src/strategies/
  ash_avellaneda_stoikov.py                  NEW  — C1
  ash_gueant.py                              NEW  — C2
  ash_cartea_skew.py                         NEW  — C3
  ash_ofi_gate.py                            NEW  — C4
  ash_target_position.py                     MODIFY  — C5 (Phase-10 scaffold extended; research-only)
  ash_skew_shape.py                          NEW  — B3 helper (wrapper strategy for skew replacement)
outputs/round_1/ash_deep_dive/
  PLAN.md                                    (this file)
  run_ash_research.py                        NEW  — master runner (arg: --phase a|b|c|d|e)
  ash_stress_tapes.py                        NEW  — Phase E generator
  phase_a/
    calibration_report.md                    GENERATED
    fits.json                                GENERATED
  phase_b/
    results.csv                              GENERATED
    PHASE_B_MEMO.md                          HAND-WRITTEN AFTER RUN
    by_lever/B{1..6}.csv                     GENERATED
  phase_c/
    results.csv                              GENERATED
    PHASE_C_MEMO.md                          HAND-WRITTEN AFTER RUN
  phase_d/
    results.csv                              GENERATED
    PHASE_D_MEMO.md                          HAND-WRITTEN AFTER RUN
  phase_e/
    stress_matrix.csv                        GENERATED
    PHASE_E_MEMO.md                          HAND-WRITTEN AFTER RUN
  phase_f/
    submission_log.md                        ONE-LINE-PER-UPLOAD
    proxy_vs_official.md                     FINAL DELIVERABLE
data/raw/round_1_ash_stress/                 NEW — 6 CSVs via Phase E
outputs/submissions/round_1/limit_80/ash_deep_dive/
  <per-candidate bundles>                    NEW, research-only upload path
```

Zero changes to:
- `src/core/config.py`'s `default_engine_config`, `round1_*` factories
- `src/core/signals.py`, `src/core/execution.py`, `src/core/fair_value.py`
- `src/strategies/__init__.py` / `STRATEGY_REGISTRY`
- `src/scripts/export_submission.py` / `LIVE_MODULE_ORDER`
- Any existing submission bundle under `outputs/submissions/round_1/`

Sanity check at end of every phase: `git diff src/core/ | wc -l` == 0.

---

## 9. Runner surface

Single entry point: `outputs/round_1/ash_deep_dive/run_ash_research.py`.
Args:
```
--phase {a,b,c,d,e}
--levers B1,B2,...                (phase b only — subset of cells)
--candidates C1,C2,...            (phase c/d only)
--tapes flat,high_vol,...         (phase e only — subset)
--days -2,-1,0                    (default all)
--out <dir>                       (default outputs/round_1/ash_deep_dive/)
--n-workers N                     (parallel sims)
```

Reuses `outputs/round_1/multi_day_cv/cv_harness.py` evaluation
primitives (Candidate dataclass, `_run_candidate`,
`_fold_pnl(..., ASH)`) but pins PEPPER to buy_and_hold 80 and
hot-swaps the ASH strategy per candidate.

Each phase emits its CSV in the same schema so Phase E can ingest
everything uniformly.

---

## 10. Time budget (sessions, ~2 hours each)

| Phase | Sessions | Dep |
|---|---|---|
| A — Calibration | 1 | — |
| B — Lever screens (build + 58-cell run + memo) | 2 | A |
| C — Academic composites (5 files + 5 tests + ~26-cell run + memo) | 3 | A, B (for parameter priors) |
| D — Hybrids (composition + 5-cell run + memo) | 1 | B, C |
| E — Stress tapes (generator + matrix sweep + memo) | 1 | D |
| F — Uploads (4 batches × 1 session, each: bundle + upload + analyze) | 4 | E |
| **Total** | **12 sessions** | |

Parallelism: A is blocking; B and early C (C1/C2) can proceed in
parallel once A lands; C5 reuses Phase-10 scaffold and can start
before B finishes. D is strictly after B+C. E is strictly after
D. F batches can overlap as data comes in.

Minimum critical path if everything lands on the first try:
A → B → D → E → F = 1+2+1+1+1 = 6 sessions (skipping C). But
Phases C and D together are the academic heart of the pass; not
running them leaves the ASH work looking like another empirical
grid sweep. Recommend the full 12-session budget.

---

## 11. Kill-switches and off-ramps

If any of the following, stop and reconvene:

1. **Phase A shows OFI R² < 0.02 at every horizon.** The OFI lever
   is dead on this product. Drop C4 and all D-hybrids using it.
2. **Phase A shows the maker fill curve is essentially zero for
   any δ > 1.0.** Means local simulator maker-model is too sparse
   to screen maker-side changes at all; downgrade every maker-
   shape candidate from "decides ship" to "official confirmation
   required". Phase F still gets to check them — we just stop
   trusting local PnL for these.
3. **Phase B shows every lever-winner is within local noise of
   C_h1_alt (|Δ| < 50 on mean).** The empirical-shape thesis is
   dead on ASH. Skip Phase D.5, keep only C1–C5 academic
   candidates for Phase F.
4. **Phase C shows every academic candidate loses on 3-day CV by
   > 300.** The paper mechanisms don't fire. Escalate to user —
   the conclusion would be that ASH's edge on this simulator is
   saturated at C_h1_alt.
5. **Phase E stress matrix flags > 50 % of surviving candidates.**
   Regime-fragility is too high to trust any of them as upload
   candidates; promote only the candidates that are strictly
   Pareto-dominant on the 3-day CV AND pass all 6 tapes.

---

## 12. Open questions (carried from the conversation)

- None blocking Phase A.
- Phase F batch F1's "control refresh" upload: do we want this
  *before* or *after* the new-candidate batches? Upload-before
  pins the reference cleanly; upload-after saves one slot if we
  don't end up promoting anything. Default here: **upload-before**
  (F1 goes first).
- PEPPER engineering drift: buy_hold_80 is used by
  `round1_test_engine_config()`; we will replicate its mechanic
  inline in the runner rather than import the factory (keeps the
  research path decoupled). Nothing changes on the shipped side.

---

**End of PLAN.md.**
