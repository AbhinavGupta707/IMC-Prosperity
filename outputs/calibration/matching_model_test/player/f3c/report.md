# Monte Carlo strategy comparison

Each strategy was run across **100 synthetic sessions**, each session = one full synthetic 1000-tick day with the same calibrated round-1 parameters.

## PnL distribution comparison

| strategy | mean | median | std | q05 | q95 | win_rate | mean_R^2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| f3c_player | -339 | -101 | 758 | -1800 | +509 | 43.0% | +0.502 |

## f3c_player

- Sessions: **100**
- Win rate (PnL > 0): **43.0%**

### PnL stats
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | -338.703 | -101.408 | 758.115 | -1799.650 | -749.371 | +191.404 | +508.539 | -2804.805 | +809.039 |

### Alpha (slope of equity curve per tick)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | -0.369 | -0.085 | 0.876 | -2.236 | -0.791 | +0.267 | +0.600 | -3.253 | +0.969 |

### R^2 (consistency of equity slope; high = stable edge)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | +0.502 | +0.585 | 0.338 | +0.001 | +0.176 | +0.811 | +0.917 | +0.000 | +0.931 |

### Downside deviation (semi-std of negative returns)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | +16.110 | +16.477 | 5.561 | +6.548 | +11.903 | +20.291 | +24.766 | +4.253 | +27.219 |

- **Worst 5 seeds** (lowest PnL): 20260435, 20260444, 20260506, 20260471, 20260488
- **Best 5 seeds** (highest PnL): 20260480, 20260426, 20260461, 20260447, 20260482
