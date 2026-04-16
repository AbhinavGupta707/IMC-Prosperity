# Monte Carlo strategy comparison

Each strategy was run across **100 synthetic sessions**, each session = one full synthetic 1000-tick day with the same calibrated round-1 parameters.

## PnL distribution comparison

| strategy | mean | median | std | q05 | q95 | win_rate | mean_R^2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| f2c_player | +363 | +374 | 227 | -59 | +740 | 93.0% | +0.739 |

## f2c_player

- Sessions: **100**
- Win rate (PnL > 0): **93.0%**

### PnL stats
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | +362.577 | +374.157 | 227.224 | -58.899 | +251.831 | +502.824 | +740.105 | -416.746 | +838.781 |

### Alpha (slope of equity curve per tick)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | +0.364 | +0.377 | 0.259 | -0.071 | +0.256 | +0.493 | +0.768 | -0.536 | +1.011 |

### R^2 (consistency of equity slope; high = stable edge)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | +0.739 | +0.827 | 0.250 | +0.137 | +0.653 | +0.928 | +0.968 | +0.001 | +0.983 |

### Downside deviation (semi-std of negative returns)
| n | mean | median | std | q05 | q25 | q75 | q95 | min | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | +6.271 | +6.103 | 2.161 | +3.300 | +4.718 | +7.700 | +10.075 | +2.387 | +11.250 |

- **Worst 5 seeds** (lowest PnL): 20260444, 20260456, 20260503, 20260435, 20260507
- **Best 5 seeds** (highest PnL): 20260421, 20260492, 20260471, 20260427, 20260480
