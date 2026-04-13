# Optimization Pass 1 — Working Notes

## EMERALDS Status

Under the current local replay / fill model and the tested sweep range
(maker_edge 0.5-4.0, taker_edge 0.5-2.0, flatten_threshold 0.65-0.80,
inventory_skew 4.0-10.0), EMERALDS produced zero fills and zero PnL
across all 68 tested configurations.

This strongly suggests EMERALDS is not worth further optimization **in
the current local tutorial replay setup**.  It does **not** prove there
is no EMERALDS edge on the official site or under different fill
behavior assumptions.  The anchor-based fair value at 10,000 may
interact differently with the live exchange's fill model.

**Decision:** Leave EMERALDS config at baseline.  Do not spend further
local sweep budget.  Re-evaluate if site-side results differ.

---

## TOMATOES Fair-Value Comparison (Phase 3)

### Full comparison (both days combined)

| Estimator | PnL | Trades | MAE(n1) | Entry Edge | mk1 | mk5 | mk20 |
|-----------|-----|--------|---------|------------|-----|-----|------|
| wall_mid | 1296 | 263 | 0.647 | +1.195 | +1.059 | +1.120 | +0.946 |
| filtered_wall_mid | 1296 | 263 | 0.647 | +1.195 | +1.059 | +1.120 | +0.946 |
| rolling_mid | 1188 | 405 | 1.745 | +2.048 | +0.338 | +0.554 | +0.577 |
| weighted_mid (current) | 276 | 16 | 0.815 | +0.664 | +1.111 | +1.250 | +0.941 |
| ewma_mid | 273 | 34 | 0.828 | — | — | — | — |
| mid | -9 | 7 | 0.790 | — | — | — | — |
| microprice | -9 | 7 | 0.741 | — | — | — | — |
| hybrid_wall_micro | -9 | 7 | 0.679 | — | — | — | — |
| depth_mid | -256 | 27 | 0.652 | — | — | — | — |

### Cross-slice sanity check

| Estimator | Day | PnL | Trades | Edge | mk1 | mk5 | mk20 | Final Pos | Near Lim |
|-----------|-----|-----|--------|------|-----|-----|------|-----------|----------|
| wall_mid | -2 | 952.50 | 137 | +1.218 | +1.065 | +1.133 | +0.891 | -3 | 0 |
| wall_mid | -1 | 454.00 | 130 | +1.171 | +1.040 | +1.124 | +1.072 | -2 | 0 |
| rolling_mid | -2 | 895.50 | 194 | +2.016 | +0.398 | +0.540 | +0.532 | 1 | 0 |
| rolling_mid | -1 | 304.00 | 215 | +2.079 | +0.277 | +0.568 | +0.622 | -6 | 0 |
| weighted_mid | -2 | 225.00 | 6 | +0.619 | +0.953 | +1.594 | +2.172 | 2 | 0 |
| weighted_mid | -1 | -56.00 | 12 | +0.709 | +1.268 | +0.906 | -0.290 | 7 | 0 |

**Key finding:** wall_mid advantage is present on both days.  Not
concentrated in one slice.

---

## Early wall_mid Review (Pre-Phase-5 Sanity Check)

### Summary metrics (full replay)

- PnL: 1296.00
- Trades: 263 (259 taker, 4 maker; 130 buy, 133 sell)
- Entry edge: +1.195
- Markouts: mk1=+1.059, mk5=+1.120, mk20=+0.946 (all positive)
- Final position: -2 (essentially flat)
- Steps near limit: 0
- Max drawdown: 377.5 (from peak 1611.5)

### Trade distribution

- 263 trades across 259 distinct 100-step time buckets
- Maximum 2 trades in any single bucket
- No clustering — gains are distributed evenly across the full timeline
- Buy/sell sides nearly perfectly balanced (130/133)

### Assessment

wall_mid looks structurally sound:

- Gains are steady and distributed, not clustered in a narrow window
- All markout horizons are positive on both days
- Inventory behavior is healthy (final position near zero, no time near limits)
- The improvement comes from genuine edge (positive markouts), not from
  more aggressive inventory exposure
- No suspicious timestamp clusters driving most of the gain

**Conclusion:** wall_mid passes the early sanity check.  Proceed with
Phase 5 sweeps around it.

---

## Updated TOMATOES Shortlist for Phase 5

### 1. wall_mid — strong candidate

Best PnL (1296), best markout quality across all horizons, advantage
present on both days, healthy inventory.  No history dependency — sweep
only maker_edge and taker_edge.

### 2. rolling_mid — shortlisted, higher-risk

Second-best PnL (1188), but quality flags:

- Much poorer markout quality (mk1=+0.338 vs wall_mid +1.059)
- High entry edge (+2.048) with low markout suggests it wins through
  aggressive taker volume rather than cleaner fair value
- 405 trades vs wall_mid's 263 — substantially more inventory turnover
- Phase 5 analysis must explicitly watch: entry edge, short-horizon
  markouts, inventory path, and whether PnL comes from real edge or
  just more aggressive trading

### 3. weighted_mid — current primary (baseline comparator)

PnL=276, only 16 trades.  Included for delta comparison against the
current production config.

### Not included in Phase 5 sweep

- **filtered_wall_mid**: Produced identical results to wall_mid on
  tutorial data (PnL, trades, markouts all match exactly).  This is
  expected — tutorial book depth is 2-3 levels, so the 25% volume
  filter and top-3 cutoff have no effect.  Implementation retained in
  code for future rounds with deeper books; not worth spending sweep
  budget on a duplicate in this pass.

- **hybrid_wall_micro, mid, microprice**: PnL=-9, minimal trades (7).
  Not competitive.

- **depth_mid**: Negative PnL (-256).  Excluded.

- **ewma_mid**: Similar to weighted_mid (PnL=273).  Not distinct enough
  to justify a third sweep slot over the stronger candidates.
