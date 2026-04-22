# D3 — Residual Allocator A/B Test

Re-runs R2 baseline with ResidualConfig.enabled=True at multiple (edge, size) calibrations. F2 is a confirmed leak if any variant shows stable positive ΔP&L vs baseline.

| Variant | Total P&L | ΔP&L vs baseline | ASH P&L | PEPPER P&L | Trade count |
|---|---|---|---|---|---|
| baseline (off) | 249,375.0 | +0.0 | 9,847.0 | 239,528.0 | 989 |
| enabled edge=2/size=2 | 249,241.0 | -134.0 | 9,793.0 | 239,448.0 | 1048 |
| enabled edge=1/size=2 | 249,430.0 | +55.0 | 9,905.0 | 239,525.0 | 1000 |
| enabled edge=2/size=3 | 249,241.0 | -134.0 | 9,793.0 | 239,448.0 | 1048 |
| enabled edge=3/size=2 | 249,725.0 | +350.0 | 9,905.0 | 239,820.0 | 1091 |

## Interpretation

- **Any variant ΔP&L > 200 stable across params:** F2 is a confirmed leak. Flip `ResidualConfig.enabled=True` as default.
- **ΔP&L ≈ 0 or negative:** residual allocator is not a leak on this product set; may still help on R3+ basket products.
- **Best variant picks the production config:** use the (edge, size) pair that maximizes ΔP&L.
