# Round 1 — Phase 3 Minimum-Viable Implementation Note

## What Phase 3 shipped

### Engine additions (one new estimator + config)

- **New estimator**: `src/core/fair_value.py::LinearDriftEstimator`
  (registered as `"linear_drift"` in `ESTIMATORS` and
  `KNOWN_ESTIMATOR_NAMES`). Online OLS fit over
  `memory.recent_mids[-history_length:]` (plus current mid if
  present), projects one index step ahead. Cold-start falls back to
  current mid; one-sample history falls back to that sample; >=2
  samples fit a slope/intercept and project `slope * n + intercept`.
- **Round-1 product configs** added to `default_engine_config()`:
  - `ASH_COATED_OSMIUM` — primary `wall_mid`, fallbacks
    `(mid, microprice)`; anchor_price 10 000 retained as a last-resort
    fallback; `taker_edge=1.0`, `maker_edge=1.0`, `inventory_skew=4.0`,
    `flatten_threshold=0.7`, `history_length=48`, `position_limit=50`
    (placeholder).
  - `INTARIAN_PEPPER_ROOT` — primary **`linear_drift`**, fallbacks
    `(depth_mid, hybrid_wall_micro, mid)`; `taker_edge=1.0`,
    `maker_edge=1.5`, `inventory_skew=2.0`,
    `flatten_threshold=0.8`, `history_length=48`,
    `position_limit=50`.
- **Tests** — 7 new `linear_drift` unit tests in
  `tests/test_fair_value.py`:
  - `returns_none_when_no_data`
  - `bootstrap_uses_current_mid`
  - `projects_constant_slope` (recovers slope=1 from a perfect ramp)
  - `flat_history_returns_intercept` (slope=0 on flat mids)
  - `respects_history_length` (short window picks up recent slope)
  - `single_prior_falls_back_to_last_mid`
  - `in_estimate_all` (registry wiring)

### Scripts

- **`src/scripts/round_1/run_round1_backtest.py`** — drives the full
  `Trader` against Round-1 data with the registered default config.
  Prints and persists a per-product + per-day summary JSON/TXT at
  `outputs/round_1/backtests/<stamp>_<label>/`.

### Regression tests

**All 410 / 410 pass** (403 pre-Phase-3 + 7 new `linear_drift` tests).
No existing behaviour touched.

## Run output (minimum-viable backtest, placeholder configs)

```
Combined (all days)   total PnL = 23 719
                      steps     = 30 000

product              pnl   trades  mk_q tk_q  pos  near   edge   mk_1   mk_5   mk_20
ASH_COATED_OSMIUM   7301      650    11 4480   -5  100  +2.245 +1.961 +1.864 +1.758
INTARIAN_PEPPER_ROOT 16418    907    60 4744   28 4872  +3.053 +3.460 +3.504 +3.394

ASH_COATED_OSMIUM per-day
 day    pnl  trades  pos  near    edge    mk_5
 -2   2 392     197    9     0  +2.182  +1.948
 -1   2 750     196   10     9  +2.257  +1.914
  0   2 172     249    2    68  +2.329  +1.783

INTARIAN_PEPPER_ROOT per-day
 day     pnl  trades  pos  near    edge    mk_5
 -2  24 864     281  -11  2714  +2.799  +3.155
 -1     385     322  -22  1123  +2.974  +3.516
  0  -4 174     304   34  1114  +3.343  +3.802
```

## What this tells us (read carefully)

### ASH_COATED_OSMIUM — looks healthy out of the box
- Combined PnL +7 301 with very consistent per-day profile
  (2 392 / 2 750 / 2 172).
- Low near-limit steps (0 / 9 / 68 = 77 total, ~0.3 % of snapshots) —
  the moderate `inventory_skew=4.0` keeps the book moving.
- Markouts are positive at every horizon (+1.96, +1.86, +1.76) and
  entry edge is +2.25. Every trade on average captures ~2 ticks of
  immediate edge.
- Maker share is near zero (11 maker trades out of 4 491 qty) — under
  the current taker-permissive config, the engine leans heavily on
  take-the-spread. Phase 4 Stage A should investigate whether a
  maker-heavier config (tighter edges or a `depth_mid` primary)
  raises markout-per-trade quality.

### INTARIAN_PEPPER_ROOT — the drift helps, but stability needs work
- Combined PnL +16 418. Trades and markouts look excellent on paper
  (edge +3.05; mk_5 +3.50).
- **Cross-day PnL is NOT stable**: +24 864 on day -2, only +385 on
  day -1, and **-4 174 on day 0**. The warm-up for `linear_drift`
  across the first ~48 samples of each day is part of this: each day
  the slope estimator has to re-learn from scratch because the rolling
  memory carried across the overnight +1 000 jump is actively
  misleading until it is flushed out.
- **Final positions are large and signed:** -11, -22, +34. The
  near-limit count on day -2 (2 714 steps, ~30 %) shows the book gets
  stuck against the limit early in a strongly-trending day. This is
  exactly the risk the dossier flagged; Phase 4 Stage B/C will need to
  either tighten quote sizes / inventory skew, or add EOD flatten.
- **The Phase 2 hypothesis survived the first engine wiring:** the
  fair-value family works; the parameters around it do not yet.

## Phase-3 acceptance (plan)

| Criterion | Status |
|-----------|--------|
| Code builds | PASS |
| Tests pass | PASS (410/410) |
| Local backtest path runs end-to-end | PASS |
| No final promotion decisions | PASS (defaults are Phase-1 / Phase-2 placeholders; Phase 4 tunes them) |
| Modular changes (no architecture churn) | PASS (one new estimator class + two config entries; no changes to trader, strategy, execution, risk) |
| Preserves fallback behavior | PASS (fallback chains explicit; cold-start tested) |

## Artefacts

- `outputs/round_1/backtests/20260414T132329Z_round1_mvb_phase3/summary.{json,txt}`
- `src/core/fair_value.py` — `LinearDriftEstimator` (~80 LoC)
- `src/core/config.py` — round-1 product registrations
- `tests/test_fair_value.py` — 7 new tests

## Carry-ins for Phase 4

1. **INTARIAN_PEPPER_ROOT cross-day stability is the #1 priority.**
   Day 0 PnL is negative under the placeholder config despite strong
   entry edge and markouts, so the problem is clearly sizing /
   inventory / overnight handling — not signal quality. Stage C in
   Phase 4 is the right place for this; Stage A/B should not ignore
   it.
2. **ASH_COATED_OSMIUM is close to reasonable already.** Stage A
   should explore whether giving up some taker aggression in favour
   of inside-touch maker quotes increases markout quality or final
   PnL.
3. **Maker share is near zero for ASH.** This is a signal that the
   current engine quote placement is dominated by take-the-spread;
   Phase 4 Stage B can test lowering `taker_edge` and raising
   `maker_edge` to see whether the maker share grows and PnL holds.
