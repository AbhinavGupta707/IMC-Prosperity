# F3c — m=2.5 + ultra-mild Cartea beta=0.1 (D8 hybrid)

**Phase-F priority:** #9 (borderline).
**Factory:** `round1_ash_deep_f3c_engine_config`.
**Inlined research:** `ash_cartea_skew.py`.

## Config
- ASH: strategy=`ash_cartea_skew`, fv=`wall_mid`, m=2.5, t=0.5
- PEPPER: `buy_and_hold`, max_aggressive_size=80
- CarteaSkewParams: `beta=0.1`, `fv_for_alpha=ewma_mid`, `sigma_residual_prior=1.06`, `alpha_clip=3.0`

## Fingerprint
- Size: 88 350 bytes
- SHA: `c8512b956c9a7eac13724e8253a9d15da2adb1d74fe9c315a0960c1b6ca3cf2d`
- Validator: 0 errors, 0 warnings

## Phase-E stress matrix
`ash_anchor_shift` = −4 764 (worst anchor-shift fragility in cohort).
Day-0 real: +2 673.
