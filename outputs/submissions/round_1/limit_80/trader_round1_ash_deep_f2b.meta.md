# F2b — wall_mid + m=2.5 + AS-continuous flatten (D6 hybrid)

**Phase-F priority:** #4 (top wall_mid-family hybrid).
**Factory:** `round1_ash_deep_f2b_engine_config`.
**Inlined research:** `ash_shape_override.py`.

## Config
- ASH: strategy=`ash_shape_override`, fv=`wall_mid`, m=2.5, t=0.5
- PEPPER: `buy_and_hold`, max_aggressive_size=80
- ShapeParams: `skew_mode=as`, `as_gamma=5e-7`, `as_sigma=2.0`, `as_horizon=100_000`,
  `flatten_mode=as_continuous`, `size_mode=constant`

## Fingerprint
- Size: 90 875 bytes
- SHA: `8e982f8231086552fee560380586ca0c24f6f516fae8a8ee2e7a47c6775085bd`
- Validator: 0 errors, 0 warnings

## Phase-E stress matrix
`ash_anchor_shift` = −589 (best wall_mid-family recovery).
Day-0 real: +3 136.
