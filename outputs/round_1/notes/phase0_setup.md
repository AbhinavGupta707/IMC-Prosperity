# Round 1 — Phase 0 Setup Note

## Branch
- `round1-research` (forked from `optimisation`).

## Data locations

Round 1 CSVs copied from the uploaded `ROUND 1/ROUND_1/` drop into the
canonical repo path:

```
data/raw/round_1/
  prices_round_1_day_-2.csv   (1 498 KB)
  prices_round_1_day_-1.csv   (1 497 KB)
  prices_round_1_day_0.csv    (1 478 KB)
  trades_round_1_day_-2.csv   (34 KB)
  trades_round_1_day_-1.csv   (34 KB)
  trades_round_1_day_0.csv    (33 KB)
```

Each price file is semicolon-delimited with the same schema as the
tutorial files (`day;timestamp;product;bid_price_1;bid_volume_1;...;
mid_price;profit_and_loss`), so the existing
`src.backtest.replay_engine.ReplayEngine.from_files` loader works
without modification.

Each file contains 10 000 timestamps × two products =
**20 000 book snapshots per day, 60 000 total**.

## Output / docs / source skeleton (created, empty)

```
outputs/round_1/
  research/           <- product dossiers (Phase 1)
  charts/             <- plots produced by EDA scripts
  eda/                <- raw EDA tables (JSON/CSV)
  fair_value_comparison/
  sweeps/             <- staged sweeps (Phase 4)
  review_packs/       <- review packs (Phase 5)
  notes/              <- phase-by-phase notes

docs/round_1/
  implementation_plan.md   <- copy of round1_implementation_plan.md

src/scripts/round_1/       <- round-1 specific script wrappers
src/strategies/round_1/    <- round-1 product strategies (Phase 3)
```

## Products

Round 1 introduces two products that are **not yet registered** in
`default_engine_config()`:

1. `ASH_COATED_OSMIUM`
2. `INTARIAN_PEPPER_ROOT`

The plan explicitly defers strategy/config work to Phase 3. Phase 1
dossiers therefore pass a **local, round-1-only `EngineConfig`** to the
fair-value comparison tooling instead of mutating the shared default.
This preserves the rule "no code changes yet except minimal setup if
needed".

## Initial (unverified) per-product config used by Phase 1 tooling

These are *placeholders for the dossier's fair-value replay only*. They
will be revisited in Phase 3 and again after official validation.

| Param             | ASH_COATED_OSMIUM | INTARIAN_PEPPER_ROOT |
|-------------------|-------------------|----------------------|
| position_limit    | 50 (placeholder)  | 50 (placeholder)     |
| strategy_name     | market_making     | market_making        |
| fair_value_method | anchor            | weighted_mid         |
| anchor_price      | 10 000            | — (no anchor)        |
| fair_value_fallbacks | (microprice, mid) | (mid, microprice) |
| taker_edge        | 1.0               | 1.0                  |
| maker_edge        | 1.0               | 1.0                  |
| quote_size        | 5                 | 5                    |
| max_aggressive_size | 10              | 10                   |
| inventory_skew    | 2.0               | 2.0                  |
| flatten_threshold | 0.8               | 0.8                  |
| history_length    | 48                | 48                   |

Rationale for the placeholder primary methods: first-pass statistics
(below) already suggest the leading hypotheses hold, so the dossier's
PnL-per-estimator table will meaningfully rank alternatives against
each product's strongest prior. **The promoted Round-1 defaults are
not decided here** — only used to generate comparisons.

Position limit is explicitly flagged as a placeholder until the
official site confirms the value.

## First-pass data stats (cleaned: rows with one-sided book dropped)

`data/raw/round_1/prices_round_1_day_{-2,-1,0}.csv`, n ≈ 9 200 valid
two-sided snapshots per (product, day).

### ASH_COATED_OSMIUM

| Day | mean mid | std | min–max | range | mean spread | median spread |
|-----|----------|-----|---------|-------|-------------|---------------|
| -2  | 9998.16  | 4.73 | 9984.5–10012.0 | 27.5 | 16.15 | 16 |
| -1  | 10000.83 | 3.83 | 9986.5–10013.5 | 27.0 | 16.19 | 16 |
|  0  | 10001.62 | 5.22 | 9981.5–10017.5 | 36.0 | 16.18 | 16 |

Observations:
- Mean mid stays within ±2 ticks of **10 000** across all three days.
- Standard deviation of mid is **~4–5 ticks**; oscillation is tight.
- Median spread is **16** on every day — a wide, stable spread.
- Leading hypothesis (stable-anchor market-maker product) remains
  supported pending dossier residual/markout work.

### INTARIAN_PEPPER_ROOT

| Day | mean mid | std | min–max | range | mean spread | median spread |
|-----|----------|-----|---------|-------|-------------|---------------|
| -2  | 10 500.57 | 287.92 | 9998.5–11001.5  | 1003 | 12.00 | 12 |
| -1  | 11 501.41 | 287.62 | 10998.0–12001.0 | 1003 | 13.01 | 13 |
|  0  | 12 500.96 | 288.18 | 11998.5–13000.5 | 1002 | 14.13 | 14 |

Observations:
- Daily mean increments by almost exactly **+1 000** per day
  (10 500 → 11 500 → 12 500).
- Per-day **range ≈ 1 000** and **σ ≈ 288**; σ·√12 ≈ 998 ≈ range, i.e.
  price is roughly uniformly distributed across the day's band rather
  than executing a clean single-slope linear drift.
- Spread widens slightly each day (12 → 13 → 14).
- Leading hypothesis ("trend-fair with local reversion") needs
  refinement: **within-day**, the signal may be local mean reversion
  around a shifting daily center; **between days**, the center steps by
  +1 000. Dossier will quantify both.

### Trade tape

Buyer/seller fields are **always blank** on all three days — no
counterparty IDs. Microstructure inference must rely on book behaviour
(walls, sizes, one-sidedness) and timestamp clustering.

## Existing tooling to reuse

| Module | What we reuse for Round 1 |
|--------|---------------------------|
| `src.backtest.replay_engine.ReplayEngine.from_files` | Parses round-1 CSVs as-is. |
| `src.backtest.fair_value_compare.build_fair_value_report` | Takes a custom `EngineConfig`, tests all 10 estimators per product. |
| `src.backtest.fair_value_compare.write_fair_value_report` | Emits JSON + text summaries. |
| `src.core.fair_value` (`ESTIMATORS`) | 10 estimators: anchor, mid, microprice, rolling_mid, weighted_mid, ewma_mid, depth_mid, wall_mid, filtered_wall_mid, hybrid_wall_micro. |
| `src.backtest.drilldown` + `drilldown_writer` + `drilldown_charts` | Per-trade review packs if needed. |
| `src.backtest.simulator.BacktestSimulator` | Full replay with any `Trader` config. |

## New tooling added in Phase 0

| Module | Purpose |
|--------|---------|
| `src/scripts/round_1/__init__.py` | Package marker. |
| `src/strategies/round_1/__init__.py` | Package marker (strategies land in Phase 3). |

No script content yet. Phase 1 will add:

- `src/scripts/round_1/run_round1_fv_compare.py` — fair-value comparison wrapper.
- `src/scripts/round_1/run_round1_dossier.py` — per-product EDA (price/spread statistics, residuals, microstructure flags).

## Acceptance criteria (plan)

| Criterion | Status |
|-----------|--------|
| Branch created | PASS (`round1-research`) |
| Round-1 data paths confirmed | PASS (`data/raw/round_1/`) |
| Output structure created | PASS |
| No code changes yet except minimal setup | PASS (only empty package markers + folder skeleton) |
| Clear list of reusable scripts/modules | PASS (table above) |

## Things explicitly deferred to later phases

- Registering ASH_COATED_OSMIUM / INTARIAN_PEPPER_ROOT in
  `default_engine_config()` — deferred to Phase 3.
- Deciding position limits — waiting on the official site; placeholder
  of 50 used only for dossier PnL comparisons.
- Any strategy-family decisions — Phase 2.
- Any parameter sweeps — Phase 4.
