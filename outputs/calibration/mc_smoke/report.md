# Monte Carlo strategy comparison

Each strategy was run across **5 synthetic sessions**, each session = one full synthetic 1000-tick day with the same calibrated round-1 parameters.

## PnL distribution comparison

| strategy | mean | median | std | q05 | q95 | win_rate | mean_R^2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| trader_round1_ash_deep_f3a | +6816 | +6706 | 637 | +6168 | +7485 | 100.0% | +0.994 |

## trader_round1_ash_deep_f3a

- Sessions: **5**
- Win rate (PnL > 0): **100.0%**

### PnL stats
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 5 | +6815.849 | +6706.035 | 636.751 | +6168.462 | +6283.703 | +7458.199 | +7484.965 | +6139.652 | +7491.656 |

### Alpha (slope of equity curve per tick)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 5 | +7.473 | +7.790 | 0.676 | +6.640 | +6.996 | +7.835 | +8.121 | +6.551 | +8.193 |

### R^2 (consistency of equity slope; high = stable edge)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 5 | +0.994 | +0.997 | 0.005 | +0.988 | +0.993 | +0.997 | +0.998 | +0.987 | +0.998 |

### Downside deviation (semi-std of negative returns)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 5 | +25.219 | +26.240 | 2.336 | +22.019 | +25.693 | +26.253 | +26.699 | +21.101 | +26.811 |

- **Worst 5 seeds** (lowest PnL): 20260417, 20260420, 20260418, 20260419, 20260421
- **Best 5 seeds** (highest PnL): 20260421, 20260419, 20260418, 20260420, 20260417
