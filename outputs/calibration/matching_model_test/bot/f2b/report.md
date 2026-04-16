# Monte Carlo strategy comparison

Each strategy was run across **100 synthetic sessions**, each session = one full synthetic 1000-tick day with the same calibrated round-1 parameters.

## PnL distribution comparison

| strategy | mean | median | std | q05 | q95 | win_rate | mean_R^2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| f2b_bot | -497 | -271 | 903 | -2236 | +488 | 37.0% | +0.543 |

## f2b_bot

- Sessions: **100**
- Win rate (PnL > 0): **37.0%**

### PnL stats
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | -496.915 | -270.812 | 902.779 | -2235.826 | -912.828 | +205.276 | +488.359 | -3409.625 | +699.625 |

### Alpha (slope of equity curve per tick)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | -0.554 | -0.239 | 1.073 | -2.953 | -0.931 | +0.229 | +0.450 | -4.023 | +0.750 |

### R^2 (consistency of equity slope; high = stable edge)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | +0.543 | +0.608 | 0.313 | +0.005 | +0.269 | +0.838 | +0.923 | +0.000 | +0.933 |

### Downside deviation (semi-std of negative returns)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | +15.932 | +15.298 | 7.046 | +6.137 | +10.327 | +21.242 | +27.671 | +4.169 | +33.844 |

- **Worst 5 seeds** (lowest PnL): 20260435, 20260444, 20260460, 20260471, 20260459
- **Best 5 seeds** (highest PnL): 20260480, 20260482, 20260461, 20260474, 20260447
