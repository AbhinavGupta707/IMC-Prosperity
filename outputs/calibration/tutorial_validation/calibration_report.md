# Calibration report

## EMERALDS

- Ticks: **20000**
- Fair value: sigma=**1.0136**, mean_return=**+0.0000**, phi=**-0.488** (SE 0.006, n=19999)
- FV range: [9996.00, 10004.00]

### Variance ratio (target: 1.0 for random walk)

| k | VR(k) |
|---:|---:|
| 2 | 0.489 |
| 5 | 0.226 |
| 10 | 0.112 |
| 20 | 0.055 |
| 50 | 0.020 |
| 100 | 0.008 |

### Depth bands

| name | side | offset_min | offset_max | presence |
|---|---|---:|---:|---:|
| level1_outer_bid_sub1 | bid | -9.00 | -7.00 | 96.7% |
| level1_inner_bid_sub2 | bid | -5.00 | -3.00 | 3.3% |
| level2_outer_bid_sub1 | bid | -13.00 | -9.00 | 98.3% |
| level2_inner_bid_sub2 | bid | -7.00 | -5.00 | 1.7% |
| level3_outer_bid | bid | -15.00 | -13.00 | 1.6% |
| level1_inner_ask_sub1 | ask | +3.00 | +5.00 | 3.3% |
| level1_outer_ask_sub2 | ask | +7.00 | +9.00 | 96.7% |
| level2_inner_ask_sub1 | ask | +5.00 | +7.00 | 1.6% |
| level2_outer_ask_sub2 | ask | +9.00 | +13.00 | 98.4% |
| level3_outer_ask | ask | +13.00 | +15.00 | 1.7% |

### Quote rules (best-match formula per band)

| bot | side | formula | match | n |
|---|---|---|---:|---:|
| level1_outer_bid_sub1 | bid | `round(fv +0.00) -8` | 100.0% | 19346 |
| level1_inner_bid_sub2 | bid | `round(fv +0.00) -4` | 100.0% | 654 |
| level2_outer_bid_sub1 | bid | `round(fv +0.00) -10` | 98.4% | 19667 |
| level2_inner_bid_sub2 | bid | `round(fv +0.00) -6` | 100.0% | 333 |
| level3_outer_bid | bid | `round(fv +0.00) -14` | 100.0% | 321 |
| level1_inner_ask_sub1 | ask | `round(fv +0.00) +4` | 100.0% | 654 |
| level1_outer_ask_sub2 | ask | `round(fv +0.00) +8` | 100.0% | 19346 |
| level2_inner_ask_sub1 | ask | `round(fv +0.00) +6` | 100.0% | 321 |
| level2_outer_ask_sub2 | ask | `round(fv +0.00) +10` | 98.3% | 19679 |
| level3_outer_ask | ask | `round(fv +0.00) +14` | 100.0% | 333 |

### Volume fits

| bot | side | min | max | n | chi^2 | p_uniform |
|---|---|---:|---:|---:|---:|---:|
| level1_outer_bid_sub1 | bid | 10 | 15 | 19346 | 13.15 | 0.022 |
| level1_inner_bid_sub2 | bid | 5 | 15 | 654 | 67.49 | 0.000 |
| level2_outer_bid_sub1 | bid | 10 | 30 | 19667 | 16696.30 | 0.000 |
| level2_inner_bid_sub2 | bid | 20 | 30 | 333 | 15.33 | 0.120 |
| level3_outer_bid | bid | 20 | 30 | 321 | 13.97 | 0.174 |
| level1_inner_ask_sub1 | ask | 5 | 15 | 654 | 66.72 | 0.000 |
| level1_outer_ask_sub2 | ask | 10 | 15 | 19346 | 13.15 | 0.022 |
| level2_inner_ask_sub1 | ask | 20 | 30 | 321 | 13.97 | 0.174 |
| level2_outer_ask_sub2 | ask | 10 | 30 | 19679 | 16663.67 | 0.000 |
| level3_outer_ask | ask | 20 | 30 | 333 | 15.33 | 0.120 |

### Trade arrivals

- p_active per tick: **0.0198** (397/20000)
- p_buy | active: **0.4899**
- total trades: 399
- KS vs geometric (gap survival): 0.0372

### Trade sizes

**buy** (n=194):
  - size 3: 0.160
  - size 4: 0.155
  - size 5: 0.175
  - size 6: 0.186
  - size 7: 0.149
  - size 8: 0.175

**sell** (n=202):
  - size 3: 0.139
  - size 4: 0.163
  - size 5: 0.193
  - size 6: 0.238
  - size 7: 0.149
  - size 8: 0.119


## TOMATOES

- Ticks: **20000**
- Fair value: sigma=**1.3410**, mean_return=**-0.0022**, phi=**-0.420** (SE 0.006, n=19999)
- Quantization grid: **0.500000**
- FV range: [4946.50, 5036.00]

### Variance ratio (target: 1.0 for random walk)

| k | VR(k) |
|---:|---:|
| 2 | 0.600 |
| 5 | 0.298 |
| 10 | 0.219 |
| 20 | 0.171 |
| 50 | 0.158 |
| 100 | 0.142 |

### Depth bands

| name | side | offset_min | offset_max | presence |
|---|---|---:|---:|---:|
| level1_inner_bid | bid | -8.00 | -1.50 | 100.0% |
| level2_outer_bid | bid | -12.00 | -2.50 | 100.0% |
| level3_outer_bid | bid | -13.00 | -9.00 | 3.6% |
| level1_inner_ask | ask | +1.50 | +8.00 | 100.0% |
| level2_outer_ask | ask | +3.00 | +12.50 | 100.0% |
| level3_outer_ask | ask | +9.50 | +13.50 | 3.6% |

### Quote rules (best-match formula per band)

| bot | side | formula | match | n |
|---|---|---|---:|---:|
| level1_inner_bid | bid | `round(fv +0.25) -7` | 92.8% | 20000 |
| level2_outer_bid | bid | `round(fv +0.25) -8` | 70.2% | 20000 |
| level3_outer_bid | bid | `round(fv +0.25) -11` | 59.7% | 729 |
| level1_inner_ask | ask | `round(fv +0.75) +6` | 92.8% | 20000 |
| level2_outer_ask | ask | `round(fv +0.75) +7` | 69.3% | 20000 |
| level3_outer_ask | ask | `round(fv +0.25) +11` | 57.6% | 714 |

### Volume fits

| bot | side | min | max | n | chi^2 | p_uniform |
|---|---|---:|---:|---:|---:|---:|
| level1_inner_bid | bid | 2 | 12 | 20000 | 15442.85 | 0.000 |
| level2_outer_bid | bid | 3 | 25 | 20000 | 18946.48 | 0.000 |
| level3_outer_bid | bid | 5 | 25 | 729 | 672.70 | 0.000 |
| level1_inner_ask | ask | 1 | 12 | 20000 | 18620.50 | 0.000 |
| level2_outer_ask | ask | 5 | 25 | 20000 | 15617.89 | 0.000 |
| level3_outer_ask | ask | 15 | 25 | 714 | 6.95 | 0.730 |

### Trade arrivals

- p_active per tick: **0.0403** (806/20000)
- p_buy | active: **0.6850**
- total trades: 820
- KS vs geometric (gap survival): 0.0794

### Trade sizes

**buy** (n=561):
  - size 2: 0.260
  - size 3: 0.232
  - size 4: 0.251
  - size 5: 0.253
  - size 6: 0.004

**sell** (n=258):
  - size 2: 0.244
  - size 3: 0.306
  - size 4: 0.236
  - size 5: 0.213

