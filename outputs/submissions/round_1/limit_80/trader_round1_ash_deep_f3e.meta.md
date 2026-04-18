# F3e — Cartea beta=0.3 (C3 only above-baseline cell)

**Phase-F priority:** #10 (last, lowest confidence).
**Factory:** `round1_ash_deep_f3e_engine_config`.
**Inlined research:** `ash_cartea_skew.py`.

## Config
- ASH: strategy=`ash_cartea_skew`, fv=`wall_mid`, m=2.0, t=0.5
- PEPPER: `buy_and_hold`, max_aggressive_size=80
- CarteaSkewParams: `beta=0.3`, `fv_for_alpha=ewma_mid`, `sigma_residual_prior=1.06`, `alpha_clip=3.0`

## Fingerprint
- Size: 88 341 bytes
- SHA: `52293073826334460f1c74211e4de7ca0bb0df21dd36d58ac4226210c2c5da6d`
- Validator: 0 errors, 0 warnings

## Phase-E stress matrix
`ash_anchor_shift` = −4 615. Day-0 real: +2 294 (worst of cohort).
