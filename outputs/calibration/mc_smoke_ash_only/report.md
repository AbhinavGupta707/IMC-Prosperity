# Monte Carlo strategy comparison

Each strategy was run across **5 synthetic sessions**, each session = one full synthetic 1000-tick day with the same calibrated round-1 parameters.

## PnL distribution comparison

| strategy | mean | median | std | q05 | q95 | win_rate | mean_R^2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| trader_round1_ash_deep_f3a | +138 | -14 | 718 | -722 | +885 | 40.0% | +0.650 |

## trader_round1_ash_deep_f3a

- Sessions: **5**
- Win rate (PnL > 0): **40.0%**

### PnL stats
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 5 | +137.915 | -14.080 | 718.329 | -722.309 | -33.249 | +700.273 | +885.017 | -894.574 | +931.203 |

### Alpha (slope of equity curve per tick)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 5 | +0.200 | +0.196 | 0.692 | -0.644 | -0.135 | +0.826 | +0.874 | -0.771 | +0.885 |

### R^2 (consistency of equity slope; high = stable edge)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 5 | +0.650 | +0.629 | 0.303 | +0.316 | +0.421 | +0.935 | +0.965 | +0.290 | +0.973 |

### Downside deviation (semi-std of negative returns)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 5 | +9.937 | +8.633 | 4.211 | +6.808 | +7.698 | +9.562 | +15.678 | +6.586 | +17.207 |

- **Worst 5 seeds** (lowest PnL): 20260417, 20260418, 20260420, 20260421, 20260419
- **Best 5 seeds** (highest PnL): 20260419, 20260421, 20260420, 20260418, 20260417
