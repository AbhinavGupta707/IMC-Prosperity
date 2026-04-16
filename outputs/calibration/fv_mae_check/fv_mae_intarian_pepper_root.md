# INTARIAN_PEPPER_ROOT — FV estimator MAE ranking

Per-tick estimator scored against recovered server fair value.
Lower MAE = better foundation for market-making strategies.
Bias indicates systematic offset (estimator - true FV).

| rank | estimator | MAE | bias | RMSE | n | description |
|---:|---|---:|---:|---:|---:|---|
| 1 | `weighted_mid_5` | 0.4843 | -0.2202 | 0.6858 | 910 | rolling-mean of last 5 mids |
| 2 | `wall_mid` | 0.5625 | -0.0192 | 0.8692 | 910 | midpoint of outermost visible bid/ask |
| 3 | `micro_price` | 0.6635 | -0.0762 | 1.1837 | 910 | size-weighted touch mid |
| 4 | `mid` | 0.7602 | +0.0000 | 1.3047 | 910 | (best_bid + best_ask) / 2 |
| 5 | `depth_mid` | 2.2350 | -0.1263 | 3.4679 | 999 | volume-weighted avg of all visible levels |
| 6 | `anchor_10000` | 2049.9560 | -2049.9560 | 2050.1591 | 1000 | constant 10000.0 |

**Recommendation**: use `weighted_mid_5` as the FV foundation. MAE 0.4843 (≈ 0.97 ticks of typical per-tick noise). Bias -0.2202 suggests a small negative systematic offset.