# Monte Carlo strategy comparison

Each strategy was run across **100 synthetic sessions**, each session = one full synthetic 1000-tick day with the same calibrated round-1 parameters.

## PnL distribution comparison

| strategy | mean | median | std | q05 | q95 | win_rate | mean_R^2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| f2d | -338 | -95 | 742 | -1654 | +515 | 42.0% | +0.512 |

## f2d

- Sessions: **100**
- Win rate (PnL > 0): **42.0%**

### PnL stats
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | -338.156 | -95.142 | 742.485 | -1654.259 | -835.849 | +215.230 | +514.631 | -2804.805 | +808.523 |

### Alpha (slope of equity curve per tick)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | -0.376 | -0.086 | 0.867 | -2.034 | -0.817 | +0.267 | +0.548 | -3.253 | +0.953 |

### R^2 (consistency of equity slope; high = stable edge)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | +0.512 | +0.571 | 0.334 | +0.005 | +0.206 | +0.827 | +0.919 | +0.000 | +0.946 |

### Downside deviation (semi-std of negative returns)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | +15.878 | +16.479 | 5.734 | +6.329 | +11.362 | +20.180 | +24.643 | +4.169 | +26.363 |

- **Worst 5 seeds** (lowest PnL): 20260435, 20260444, 20260471, 20260450, 20260465
- **Best 5 seeds** (highest PnL): 20260480, 20260426, 20260447, 20260482, 20260461
