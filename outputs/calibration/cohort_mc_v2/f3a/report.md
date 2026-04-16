# Monte Carlo strategy comparison

Each strategy was run across **100 synthetic sessions**, each session = one full synthetic 1000-tick day with the same calibrated round-1 parameters.

## PnL distribution comparison

| strategy | mean | median | std | q05 | q95 | win_rate | mean_R^2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| f3a | +394 | +421 | 306 | -103 | +882 | 92.0% | +0.715 |

## f3a

- Sessions: **100**
- Win rate (PnL > 0): **92.0%**

### PnL stats
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | +393.642 | +420.845 | 306.278 | -102.504 | +253.922 | +549.582 | +882.273 | -630.703 | +1079.672 |

### Alpha (slope of equity curve per tick)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | +0.404 | +0.390 | 0.346 | -0.158 | +0.290 | +0.584 | +0.929 | -0.752 | +1.281 |

### R^2 (consistency of equity slope; high = stable edge)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | +0.715 | +0.802 | 0.270 | +0.080 | +0.628 | +0.919 | +0.961 | +0.001 | +0.983 |

### Downside deviation (semi-std of negative returns)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | +7.807 | +7.106 | 3.195 | +3.383 | +5.479 | +9.827 | +13.726 | +2.559 | +16.429 |

- **Worst 5 seeds** (lowest PnL): 20260444, 20260503, 20260456, 20260476, 20260507
- **Best 5 seeds** (highest PnL): 20260421, 20260492, 20260471, 20260462, 20260500
