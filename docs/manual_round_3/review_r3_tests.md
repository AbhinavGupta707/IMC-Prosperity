# Round-3 Unit Test Audit

**Scope:** 119 unit tests across 8 files on branch `round3-engine`.
**Bottom line:** test *quantity* is good; test *rigor* is mixed.
Primitives that are pure math (SST, BSM, hysteresis, conversions) are
reasonably well tested. Primitives that are *stateful* and *statistical*
(Welford, SmileFitter EWMA, PredictiveEstimator components,
CounterpartyIntel classifier) are under-tested. The Stage-E engine
suite is explicitly smoke-only — it catches crashes, not numerical
regressions. Two tests in `test_stage_c_primitives.py` contain
tautology assertions of the form `not r.passed or abs(ic) < X` that
pass regardless of what the code does. A handful of tests use unseeded
`random` calls.

Ratings out of 10. 10 = I'd trust this to block a merge; 5 = catches
only major breakage; 0 = cargo-cult.

---

## 1. `test_sst_primitive.py` — 13 tests

**Coverage 7 · Rigor 6 · Edge cases 5**

**Good:** take on both sides, clear-mode suppression for both long and
short, config validation, idle on invalid fair, determinism check.

**Gaps:**
1. **No "take AND make in the same tick" test.** The source emits both
   when a cheap ask exists *and* buy capacity remains. This is exactly
   the regression called out in the brief. Add a fixture with a cheap
   ask + enough capacity and assert *both* an aggressor buy and a
   maker bid appear at different prices.
2. **Toxicity filter is only tested ask-side.** The `bid_price -= 1`
   branch when buy-side is toxic is untested. A sign flip survives.
3. **Clear-mode aggressor-take branch (sst.py:238-257) is untested.**
   Clear-mode tests only verify the *wrong side* is suppressed. They
   never verify the clear take *fires*.
4. **Join logic is untested.** `_pick_join_level` and `disregard_edge`
   both have zero direct coverage. `test_sst_make_places_symmetric_
   maker_quotes` happens to produce the same price with or without the
   join branch firing.
5. **Crossed-spread guard (lines 284, 305) is untested.** Removing the
   clamp doesn't fail any test.
6. **`max_taker_size` cap is untested** (only the opponent-volume clamp
   is verified).

**Verdict:** would catch config-validation regressions and basic
branch flips; would miss duplicate-order-per-tick, clear-take breakage,
buy-toxic flips, and join/disregard bugs.

---

## 2. `test_crash_telemetry.py` — 11 tests

**Coverage 8 · Rigor 7 · Edge cases 7**

**Good:** happy+error path, kill-switch window boundary, cool-off
decrement, heartbeat hang detect/reset/empty-book ignore, snapshot
roundtrip, invalid-payload restore, config validation.

**Gaps:**
1. **`enabled=False` propagation is untested.** Source lines 143-147
   let errors raise when telemetry is disabled. If a regression
   swallowed them, no test fails — and "errors silently swallowed" is
   the exact historical bug this primitive was written to prevent.
2. **`test_kill_switch_triggers_after_threshold_errors`** uses
   `assert 499 <= cooloff_remaining <= 500`, papering over whether
   `tick_cooloff` is called once or twice on the error path. Exactly
   one of those is correct; the test should pick.
3. **`max_error_history` bounded-deque behavior is untested.** Record
   100 errors with `max_history=32`: should retain only the last 32.
4. **Cross-tick persistence:** `errors_in_window` after
   snapshot→restore→tick is not exercised.

**Verdict:** solid baseline. Fix the cooloff assertion and add the
`enabled=False` propagation test.

---

## 3. `test_sweep_selector.py` — 10 tests

**Coverage 7 · Rigor 7 · Edge cases 6**

**Highlight:** `test_v5_vs_promoted_noise_rejected` encodes the exact
R2 regression with real per-day P&L numbers. The most valuable test in
the entire suite.

**Gaps:**
1. **"Plateau never overrides significance" is asserted only in prose,
   never in code.** Add a candidate with narrow CI but CI-lower inside
   baseline's CI-upper; expect rejection.
2. **`_score_by_quantiles`, `_score_top3`, `_score_top10`** — only
   `linear` is exercised. `custom` + quantiles path has zero coverage.
3. **Bootstrap reproducibility:** identical inputs should produce
   byte-identical output given the `hash(label)` seeding. Not
   asserted.
4. **Outlier-inflation case (the R2 dep-5 lesson):** `[1000, 7000,
   7200, 7100]` vs `[7000]×4` should not produce a winner. Close
   analog but not exact.

**Verdict:** best-in-file regression test carries this one. Strengthen
with custom-objective coverage.

---

## 4. `test_fill_calibration.py` — 5 tests

**Coverage 5 · Rigor 4 · Edge cases 4**

**Weakest file.**

**Gaps:**
1. **No golden integration test.** The harness's stated purpose is to
   match our backtest to the IMC simulator's R2 `Promoted` truth
   (7,654 ± 366 vs backtest ~249,375). No fixture encodes that
   measurement. The module that's meant to tell us whether every
   other test is lying has no ground-truth test itself.
2. **`scale_to_truth` never stressed.** All tests use 1.0 or 30.0 in
   trivial ways. The divide-by-30 is never verified numerically.
3. **`rel_error` with `truth_pnl=0`** — the `max(1e-9, ...)` guard is
   untested; R2 has had near-zero days.
4. **`consensus_fill_rate` with disagreement** between sweeps is
   untested — a regression that returned None on disagreement would
   pass.
5. **`format_sweep` output has no assertion.** A column-swap or
   sign-flip reporting bug ships silently.

**Verdict:** harness is unit-tested; calibration decision is not
test-driven. Given this primitive gates all other calibration, this is
a high-priority gap.

---

## 5. `test_stage_b_primitives.py` — 24 tests

**Coverage 8 · Rigor 7 · Edge cases 7**

**Good:** PortfolioSnapshot build + missing + immutable; wall-mid
picks largest volume / falls back / None on empty; hysteresis covers
exit/hold/active/kill and both signs; PortfolioRiskManager covers
gross, per-group, residual-on-for-arb doctrine; F2 "inside wall"
placement pattern asserted explicitly.

**Gaps:**
1. **`test_filtered_wall_mid_uses_ratio`** asserts `mid > 0` only —
   "assertion too weak." Any non-crashing implementation passes.
   Assert the actual numeric value.
2. **`test_hysteresis_scales_in_active_zone`** — at `z=entry_z`
   exactly, `t1` should be 0. Asserted as `0 <= abs(t1)`, which
   passes if someone flipped `>` to `>=` and produced t1=1. Tighten.
3. **`scale_exponent != 1.0`** — quadratic and sub-linear sizing
   never exercised.
4. **Partial tagging:** mixing tagged and untagged products in the
   same `portfolio_capacity` call is not tested.
5. **`clamp_by_capacity` with negative limit** (returns 0) —
   untested edge.

**Verdict:** solid. Two weak assertions and the exponent gap.

---

## 6. `test_stage_c_primitives.py` — 19 tests

**Coverage 6 · Rigor 5 · Edge cases 5**

**Most test-smells of any file.**

**Critical bugs in the tests themselves:**
1. `test_strict_lag_test_detects_contemporaneous_correlation` asserts
   `not r.passed or (r.ic is not None and abs(r.ic) < 0.15)`.
   Disjunction with a NOT — passes if the test just returned
   `passed=False, ic=None`. Effectively `assert True`.
2. `test_strict_lag_test_passes_for_true_leading_signal` has the same
   anti-pattern AND the feature/returns construction guarantees IC ≈ 0
   (the test claims to "pass for a leading signal" but the fixture
   doesn't actually produce one).

Both should be rewritten with explicit assertions:
`assert not r.passed` and `assert abs(r.ic) < 0.15` as separate
conjunctions, with fixtures that genuinely match the case.

**Other gaps:**
3. **Global-RNG use** at lines 100, 111, 147-148 — `random.gauss(0, 1)`
   without `random.seed()` or local `Random`. Flake-prone under
   pytest random-order plugins.
4. **`test_shuffle_test_fails_when_both_series_correlate_with_time`**
   — name says "fails," body asserts `r.passed`. Rename or invert.
5. **`own_quote_causality_test`** — only the vacuous-pass (<100 clean
   ticks) branch is covered. The real D9 "OBI endogenous" path has
   zero coverage. Brief explicitly asks for this; it's missing.
6. **`walk_forward_test` vacuous-pass** (IS IC < 0.02) branch
   untested.
7. **`validate_signal` `passed_all` aggregate** — not asserted for a
   known-pass signal vs a known-fail one.
8. **PredictiveEstimator `components` dict contents** — only `price`
   is asserted. A refactor that dropped `signal_ic` or `base_price`
   from components ships silently.
9. **PredictiveEstimator `max_adjustment` exact boundary** untested.

**Verdict:** this file would not reliably catch a regression in
`signal_validation.py`. Rewrite the four validation-test tests; add a
real own-quote-causality fixture.

---

## 7. `test_stage_d_primitives.py` — 28 tests

**Coverage 7 · Rigor 5 · Edge cases 6**

**Good:** norm_cdf vs textbook values, BSM input validation, IV
roundtrip, IV rejects below-intrinsic + zero, conversion break-evens,
3× batch cap, regime detector cold start, FillRateProbe convergence.

**Biggest issue: tolerances are too loose.**
1. **`test_call_price_atm_sanity`** uses `abs=0.5` on a true value of
   7.97 — 6% tolerance. Near-ATM P&L routinely moves within that
   band. A 0.3-tick pricing bias from a smile/moneyness sign flip
   passes. Tighten to `abs=0.02`.
2. **`test_call_price_deep_itm_converges_to_intrinsic`** — `abs=0.5`
   on a known-exact 100.0. Given A&S 7.5e-8 accuracy, `abs=0.01` is
   defensible.

**Missing property tests:**
3. Monotonicity: `call(σ)` strictly increasing, `call(S)` strictly
   increasing, `call ≥ max(S-K·exp(-rT), 0)`. None asserted. A
   sign-flipped vega passes everything.
4. Greeks consistency: `gamma·S·σ·√T ≈ φ(d1)`. No cross-check.
5. **IV bracket-widening branch (bsm.py:191-198)** — untested; a
   market price implying σ > 5 exercises it.

**Smile gaps:**
6. **Quadratic coefficient sign** — fitting `{95:0.25, 100:0.18,
   105:0.25}` should give `a > 0` (convex U). Only the interpolated
   *value* is checked, not the coefficient sign. A smile flipped
   concave would pass.
7. **`_solve_3x3` singular path** (degenerate colinear points) —
   untested.
8. **`SmileFitter.observe` rolling-window deque eviction** — untested.
9. **`test_smile_rolling_mode_after_warmup`** asserts `iv > 0.22`.
   Expected EWMA value given halflife=100 after 50 new obs is ~0.23.
   Marginal — a bug that doubled halflife still passes. Tighten the
   bound or compute the expected value analytically.

**Conversion gaps:**
10. **Signed tariffs (F4 doctrine):** no test asserts that
    `ConversionSpec(import_tariff=-2.0)` constructs (subsidies must be
    allowed).
11. **`target_batch_size` with `max_inventory_buffer=None`** (default
    branch) — untested.

**Verdict:** this file is where a real pricing bug is most likely to
hide under current tolerances. High priority for tightening.

---

## 8. `test_stage_e_engines.py` — 9 tests

**Coverage 4 · Rigor 3 · Edge cases 3**

File docstring honestly says "smoke tests." By the brief's standard
("verify primitives compose correctly"), the gaps are severe.

1. **`test_basket_engine_returns_orders_on_large_spread`** asserts
   "some long-basket order exists." The brief asks: does
   `hedge_factor=0.5` produce a hedge leg of the expected size?
   **Not asserted.** A bug that dropped hedges entirely, or set
   hedge_factor=1.0, would pass. Add explicit assertions on the
   basket-leg / hedge-leg size *ratio*.
2. **Welford cold-start (brief item):** zero unit tests on
   `_WelfordStats`; zero engine tests on the first post-warmup tick
   with σ=0. This is the "edge bleed" case the brief calls out. Add
   a primitive-level test: constant series → `stdev() → 0`.
3. **`test_options_engine_quotes_after_smile_warmup`** asserts
   `"V_10000" in tags` — but tags are built unconditionally by
   `_build_tags()`. The test holds even if *zero* voucher orders are
   emitted. Add: `any(o.symbol == "V_10000" for o in orders)`.
4. **Jump detection + 500-tick kill-cooldown** in options — untested.
5. **Whalley-Wilmott band + delta-hedge branch** in options —
   `delta_hedge_enabled=False` in every test. ~60 lines of WW math
   with zero coverage.
6. **StatArb squeeze-regime overlay** (stat_arb.py:172-185) —
   untested.
7. **Counterparty fingerprint** — the test asserts 3 identical
   behaviors hash to one key (necessary), not that different
   behaviors hash to different keys (sufficient). A regression that
   hashed everything to a constant passes.
8. **Counterparty informed classifier** — test asserts `cum_pnl > 0`
   but never `state.regime == "informed"`. The three-branch
   classifier with specific thresholds has zero coverage.
9. **`test_stat_arb_no_arb_no_orders`** uses a degenerate
   `bid=ask=100` book instead of a canonical `bid=99, ask=101` no-arb
   case.

**Verdict:** highest-risk file. Engine-level numerical regressions —
hedge ratio, smile adaptation, jump halt — are exactly where R3 P&L
is won or lost, and none are under test.

---

## Cross-cutting observations

**Flaky tests.** `test_stage_c_primitives.py` lines ~100-115 and
`test_stage_d_primitives.py` line 288 use the global `random` module
without `random.seed()` or a local `Random(seed)` instance. Fix by
routing through a seeded `Random` everywhere.

**Tests that pass but shouldn't.** Ranked by severity:
1. Two `not r.passed or |ic| < X` assertions in
   `test_stage_c_primitives.py` — tautologies.
2. `test_kill_switch_triggers_after_threshold_errors` — ambiguous
   cooloff range.
3. `test_basket_engine_returns_orders_on_large_spread` — says nothing
   about hedge size.
4. `test_filtered_wall_mid_uses_ratio` — asserts `mid > 0` only.
5. `test_options_engine_quotes_after_smile_warmup` — tags assertion
   holds even when no orders are emitted.

**Redundant tests.** Few. Candidates:
- `test_bus_emit_get_trusted_only_default` overlaps
  `test_bus_filters_unvalidated_by_default`.
- `test_hysteresis_exits_inside_exit_z` and
  `test_hysteresis_sign_convention` overlap on the sign dimension.
- The two SST config-validation tests could merge into one
  `pytest.mark.parametrize` block.

**Regression-test checklist from the brief:**

| Brief item | Status |
|---|---|
| v5 vs Promoted stat significance | Covered |
| Welford cold-start edge bleed | **Missing** at both primitive and engine level |
| OBI IC endogeneity (own_quote_causality) | **Missing** — only vacuous-pass branch tested |
| SST emits both take AND make same tick | **Missing** |
| BSM near-ATM P&L swings within tolerance | Tolerances too loose; property tests missing |
| Hedge-factor=0.5 produces expected hedge size | **Missing** |

---

## Overall per-file verdict

| File | N | Cov | Rig | Would catch a real regression? |
|---|---|---|---|---|
| test_sst_primitive.py | 13 | 7 | 6 | Partial — misses take+make, clear-take, buy-tox |
| test_crash_telemetry.py | 11 | 8 | 7 | Mostly — fix cooloff assertion |
| test_sweep_selector.py | 10 | 7 | 7 | Yes for R2 bug; gaps in custom-objective |
| test_fill_calibration.py | 5 | 5 | 4 | Harness OK; no golden integration test |
| test_stage_b_primitives.py | 24 | 8 | 7 | Mostly yes |
| test_stage_c_primitives.py | 19 | 6 | 5 | **No** — tautology assertions |
| test_stage_d_primitives.py | 28 | 7 | 5 | Loose tolerances hide pricing bugs |
| test_stage_e_engines.py | 9 | 4 | 3 | Only crashes — not numerical regressions |

## Top 5 fixes before IMC upload day

1. **Rewrite the two `not r.passed or |ic| < X` assertions** in
   `test_stage_c_primitives.py`. They are tautologies.
2. **Tighten BSM tolerances** from `abs=0.5` to `abs=0.02` for
   textbook cases, and add monotonicity property tests (vega > 0,
   delta > 0, call ≥ intrinsic).
3. **Add SST "take AND make same tick" regression test.**
4. **Add explicit hedge-size assertion** to the basket-engine large-
   spread test (`hedge_factor=0.5` → half-size hedge on each
   constituent).
5. **Add a `_WelfordStats` unit-test file** covering constant-series
   `stdev → 0` and an engine-level test of the first post-warmup tick.

One focused afternoon. Expected regression-capture rate improvement
from roughly 50% to 80%. That is the difference between "backtest
green, live red" and "backtest green, live green."
