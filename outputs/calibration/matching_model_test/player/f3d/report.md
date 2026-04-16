# Monte Carlo strategy comparison

Each strategy was run across **100 synthetic sessions**, each session = one full synthetic 1000-tick day with the same calibrated round-1 parameters.

## PnL distribution comparison

| strategy | mean | median | std | q05 | q95 | win_rate | mean_R^2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| f3d_player | -380 | -209 | 761 | -1782 | +489 | 36.0% | +0.540 |

## f3d_player

- Sessions: **100**
- Win rate (PnL > 0): **36.0%**

### PnL stats
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | -379.592 | -209.125 | 760.754 | -1782.138 | -774.207 | +205.276 | +488.621 | -2932.719 | +699.625 |

### Alpha (slope of equity curve per tick)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | -0.437 | -0.219 | 0.907 | -2.526 | -0.798 | +0.233 | +0.463 | -3.530 | +0.750 |

### R^2 (consistency of equity slope; high = stable edge)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | +0.540 | +0.594 | 0.316 | +0.006 | +0.275 | +0.841 | +0.925 | +0.000 | +0.937 |

### Downside deviation (semi-std of negative returns)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | +14.713 | +14.942 | 5.727 | +6.179 | +10.359 | +18.904 | +24.247 | +4.169 | +29.573 |

- **Worst 5 seeds** (lowest PnL): 20260435, 20260444, 20260460, 20260471, 20260505
- **Best 5 seeds** (highest PnL): 20260480, 20260447, 20260482, 20260461, 20260474
