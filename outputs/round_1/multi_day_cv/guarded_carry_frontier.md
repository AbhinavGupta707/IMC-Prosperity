# Guarded carry frontier

Tight PEPPER frontier around `window=32`, `target=0`, `open_take_mode=level1_only`.

## Expanded stress set

- `flat`
- `reversed`
- `high_vol`
- `stepped`
- `mild_reversed`
- `late_reversed`
- `reversed_high_vol`
- `shock_down_recover`

## V3 reference

- mean_real: 79381.3
- reversed: -80431.0
- mild_reversed: -40451.0
- late_reversed: -451.0
- reversed_high_vol: -61100.0
- stepped: -451.0
- shock_down_recover: 79549.0

## Top frontier candidates

| label | mean_real | reversed | mild_rev | late_rev | rev_high_vol | stepped | shock | score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| GC_w32_g0p005_t00_l1 | 79417.0 | -3402.0 | -2551.0 | 49598.0 | -3101.5 | 32888.0 | 78927.0 | 102539.9 |
| GC_w32_g0p01_t00_l1 | 79417.0 | -3402.0 | -2551.0 | 49598.0 | -3825.5 | 32888.0 | 79719.0 | 102497.5 |
| GC_w32_g0p015_t00_l1 | 79417.0 | -3402.0 | -2939.0 | 49598.0 | -3825.5 | 32888.0 | 79740.0 | 102484.2 |
| GC_w32_g0p02_t00_l1 | 79417.0 | -3402.0 | -3085.0 | 49598.0 | -4618.0 | 32888.0 | 79887.0 | 102396.6 |
| GC_w32_g0p03_t00_l1 | 79417.0 | -3402.0 | -3085.0 | 49598.0 | -5015.0 | 32888.0 | 79881.0 | 102370.0 |
| GC_w32_g0p025_t00_l1 | 79417.0 | -3402.0 | -3085.0 | 49598.0 | -5318.0 | 32888.0 | 79881.0 | 102335.1 |
| GC_w32_g0p04_t00_l1 | 79417.0 | -3402.0 | -4036.0 | 49598.0 | -4943.0 | 32888.0 | 79781.0 | 102312.7 |
| GC_w32_g0p05_t00_l1 | 79417.0 | -4577.0 | -10107.5 | 49598.0 | -3391.5 | 32888.0 | 79687.0 | 101883.6 |
