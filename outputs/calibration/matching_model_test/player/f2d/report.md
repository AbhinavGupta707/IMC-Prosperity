# Monte Carlo strategy comparison

Each strategy was run across **100 synthetic sessions**, each session = one full synthetic 1000-tick day with the same calibrated round-1 parameters.

## PnL distribution comparison

| strategy | mean | median | std | q05 | q95 | win_rate | mean_R^2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| f2d_player | -336 | -95 | 742 | -1654 | +515 | 42.0% | +0.509 |

## f2d_player

- Sessions: **100**
- Win rate (PnL > 0): **42.0%**

### PnL stats
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | -336.210 | -94.894 | 742.420 | -1654.259 | -835.849 | +215.230 | +514.631 | -2804.805 | +808.523 |

### Alpha (slope of equity curve per tick)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | -0.374 | -0.068 | 0.870 | -2.034 | -0.817 | +0.267 | +0.563 | -3.253 | +0.953 |

### R^2 (consistency of equity slope; high = stable edge)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | +0.509 | +0.571 | 0.337 | +0.005 | +0.187 | +0.827 | +0.919 | +0.000 | +0.946 |

### Downside deviation (semi-std of negative returns)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | +15.855 | +16.329 | 5.723 | +6.329 | +11.362 | +20.180 | +24.640 | +4.169 | +26.363 |

- **Worst 5 seeds** (lowest PnL): 20260435, 20260444, 20260471, 20260450, 20260465
- **Best 5 seeds** (highest PnL): 20260480, 20260426, 20260447, 20260482, 20260461
