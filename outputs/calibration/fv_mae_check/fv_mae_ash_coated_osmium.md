# ASH_COATED_OSMIUM — FV estimator MAE ranking

Per-tick estimator scored against recovered server fair value.
Lower MAE = better foundation for market-making strategies.
Bias indicates systematic offset (estimator - true FV).

| rank | estimator | MAE | bias | RMSE | n | description |
|---:|---|---:|---:|---:|---:|---|
| 1 | `weighted_mid_5` | 0.5482 | -0.0892 | 0.7904 | 914 | rolling-mean of last 5 mids |
| 2 | `wall_mid` | 0.5662 | -0.0293 | 0.8417 | 914 | midpoint of outermost visible bid/ask |
| 3 | `micro_price` | 0.7883 | +0.0541 | 1.2935 | 914 | size-weighted touch mid |
| 4 | `mid` | 0.8155 | -0.0878 | 1.3872 | 914 | (best_bid + best_ask) / 2 |
| 5 | `anchor_10000` | 1.7652 | +0.1138 | 2.1760 | 1000 | constant 10000.0 |
| 6 | `depth_mid` | 2.4666 | +0.0465 | 3.8193 | 998 | volume-weighted avg of all visible levels |

**Recommendation**: use `weighted_mid_5` as the FV foundation. MAE 0.5482 (≈ 1.10 ticks of typical per-tick noise). Bias -0.0892 suggests a small negative systematic offset.