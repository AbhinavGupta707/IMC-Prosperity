# D2 — Cross-Product Lead-Lag Test

Tests whether lagged returns on product A predict returns on product B. |ρ| > 0.15 at any lag = confirmed cross-product alpha the current per-product architecture cannot capture.

## round_1

| Pair (A, B) | lag=-5 | lag=-3 | lag=-1 | lag=0 | lag=1 | lag=3 | lag=5 | lag=10 | lag=20 | N |
|---|---|---|---|---|---|---|---|---|---|---|
| ASH_COATED_OSMIUM → INTARIAN_PEPPER_ROOT | -0.0019 | +0.0121 | -0.0142 | +0.0161 | -0.0106 | +0.0097 | -0.0052 | -0.0082 | -0.0053 | 29894 |

## round_2

| Pair (A, B) | lag=-5 | lag=-3 | lag=-1 | lag=0 | lag=1 | lag=3 | lag=5 | lag=10 | lag=20 | N |
|---|---|---|---|---|---|---|---|---|---|---|
| ASH_COATED_OSMIUM → INTARIAN_PEPPER_ROOT | -0.0013 | -0.0073 | +0.0013 | +0.0015 | -0.0031 | -0.0063 | -0.0032 | -0.0077 | +0.0073 | 29897 |

## Interpretation

- **|ρ| > 0.15 at ANY lag:** architectural F4 is a confirmed leak. Cross-product engine needed.
- **Peak at lag > 0:** leftmost product (A) leads rightmost (B). Front-run B.
- **Peak at lag = 0:** contemporaneous correlation; still useful for basket arb.
- **Peak at lag < 0:** second product (B) leads first (A). Swap roles.
- **All lags ~ 0:** products are genuinely independent in this regime; F4 not a leak here.
