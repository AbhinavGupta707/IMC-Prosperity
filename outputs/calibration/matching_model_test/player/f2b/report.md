# Monte Carlo strategy comparison

Each strategy was run across **100 synthetic sessions**, each session = one full synthetic 1000-tick day with the same calibrated round-1 parameters.

## PnL distribution comparison

| strategy | mean | median | std | q05 | q95 | win_rate | mean_R^2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| f2b_player | -475 | -259 | 885 | -2195 | +489 | 38.0% | +0.546 |

## f2b_player

- Sessions: **100**
- Win rate (PnL > 0): **38.0%**

### PnL stats
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | -475.203 | -258.592 | 884.869 | -2194.970 | -881.201 | +234.014 | +488.621 | -3409.625 | +699.625 |

### Alpha (slope of equity curve per tick)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | -0.529 | -0.228 | 1.048 | -2.921 | -0.931 | +0.242 | +0.463 | -4.023 | +0.750 |

### R^2 (consistency of equity slope; high = stable edge)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | +0.546 | +0.608 | 0.309 | +0.006 | +0.282 | +0.834 | +0.924 | +0.001 | +0.936 |

### Downside deviation (semi-std of negative returns)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | +15.959 | +15.298 | 7.064 | +6.179 | +10.327 | +21.242 | +27.652 | +4.169 | +33.321 |

- **Worst 5 seeds** (lowest PnL): 20260435, 20260444, 20260459, 20260460, 20260471
- **Best 5 seeds** (highest PnL): 20260480, 20260447, 20260482, 20260461, 20260474
