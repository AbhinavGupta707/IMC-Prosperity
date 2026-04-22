# D4 — OBI-Skewed Fair-Value Counterfactual

Adds `beta * book_imbalance * spread` to the existing weighted_mid fair value for ASH_COATED_OSMIUM. beta=0 reproduces baseline. If best beta yields a material ASH P&L lift, F5 is confirmed — predictive OBI signal captures alpha the current reactive FairValueEngine cannot.

| β | Total P&L | ΔTotal vs β=0 | ASH P&L | ΔASH vs β=0 | PEPPER P&L | Trades |
|---|---|---|---|---|---|---|
| -0.50 | 246,967 | +0 | 7,439 | +0 | 239,528 | 762 |
| -0.25 | 248,569 | +0 | 9,041 | +0 | 239,528 | 873 |
| -0.10 | 249,141 | +0 | 9,613 | +0 | 239,528 | 947 |
| +0.00 | 249,375 | +0 | 9,847 | +0 | 239,528 | 989 |
| +0.10 | 249,374 | -1 | 9,846 | -1 | 239,528 | 1048 |
| +0.25 | 248,705 | -670 | 9,177 | -670 | 239,528 | 1305 |
| +0.50 | 245,292 | -4,083 | 5,764 | -4,083 | 239,528 | 1988 |
| +1.00 | 169,926 | -79,449 | -69,602 | -79,449 | 239,528 | 3442 |
| +2.00 | -305,584 | -554,959 | -545,112 | -554,959 | 239,528 | 9844 |

## Interpretation

- **Best β positive with ΔASH > 500:** F5 confirmed. OBI predictor captures real alpha; build predictive estimator into FairValueEngine.
- **Best β at 0:** F5 not confirmed on ASH; reactive FV is already near-optimal for this product.
- **Asymmetric response (positive β helps, negative hurts):** confirms the direction of the causal signal.
- **Symmetric response:** suspicious — may indicate tuning sensitivity rather than directional edge.

D1 already showed IC(OBI, 10-tick) = +0.52 on ASH. If D4 also shows a material positive β, the signal is *both* statistically significant *and* actionable given the existing execution stack — double confirmation.
