# F3d — Avellaneda-Stoikov gamma=5e-7 (safer gamma)

**Phase-F priority:** #8.
**Factory:** `round1_ash_deep_f3d_engine_config` (= `f2a_engine_config`; AS params differ in bundle wiring).
**Inlined research:** `ash_avellaneda_stoikov.py`.

## Config
- ASH: strategy=`ash_avellaneda_stoikov`, fv=`wall_mid`, m=2.0, t=0.5
- PEPPER: `buy_and_hold`, max_aggressive_size=80
- AS params: γ=5e-7, σ=2.0, k=0.4, T=100000

## Fingerprint
- Size: 88 449 bytes
- SHA: `35b1d904913559fbcbc5ad19761b0195cef27739f7035726e7bf4bc1f2382645`
- Validator: 0 errors, 0 warnings

## Phase-E stress matrix
`ash_flat` = −4 488 (similar to shipped).
Day-0 real: +2 943.
