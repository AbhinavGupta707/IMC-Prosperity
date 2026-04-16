# Monte Carlo strategy comparison

Each strategy was run across **100 synthetic sessions**, each session = one full synthetic 1000-tick day with the same calibrated round-1 parameters.

## PnL distribution comparison

| strategy | mean | median | std | q05 | q95 | win_rate | mean_R^2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| f3d_bot | -392 | -209 | 758 | -1782 | +488 | 36.0% | +0.539 |

## f3d_bot

- Sessions: **100**
- Win rate (PnL > 0): **36.0%**

### PnL stats
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | -391.713 | -209.125 | 757.967 | -1782.138 | -774.207 | +205.276 | +488.359 | -2932.719 | +699.625 |

### Alpha (slope of equity curve per tick)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | -0.449 | -0.216 | 0.902 | -2.511 | -0.838 | +0.229 | +0.450 | -3.530 | +0.750 |

### R^2 (consistency of equity slope; high = stable edge)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | +0.539 | +0.594 | 0.318 | +0.005 | +0.268 | +0.838 | +0.923 | +0.000 | +0.937 |

### Downside deviation (semi-std of negative returns)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | +14.704 | +14.729 | 5.721 | +6.137 | +10.377 | +18.904 | +24.070 | +4.169 | +29.485 |

- **Worst 5 seeds** (lowest PnL): 20260435, 20260444, 20260471, 20260460, 20260505
- **Best 5 seeds** (highest PnL): 20260480, 20260482, 20260461, 20260474, 20260447
