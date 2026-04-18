# F2a — Avellaneda-Stoikov gamma=2e-6

**Phase-F priority:** #5 (Phase-C winner on local but wall_mid-family fragile on stress).
**Factory:** `round1_ash_deep_f2a_engine_config`.
**Inlined research:** `ash_avellaneda_stoikov.py`.

## Config
- ASH: strategy=`ash_avellaneda_stoikov`, fv=`wall_mid` (fallbacks mid/microprice), m=2.0, t=0.5
- PEPPER: `buy_and_hold`, max_aggressive_size=80
- AS params: γ=2e-6, σ=2.0, k=0.4, T=100000, min_half_spread=0.5, flatten=0.7

## Fingerprint
- Size: 88 470 bytes (86% of hard cap)
- SHA: `853e9a934a206266f6c40292e4ebe7e467492fc57d1193cc1b41de3ab62b4bf1`
- Validator: 0 errors, 0 warnings

## Phase-E stress matrix (vs shipped)
Worst: `ash_flat` = −4 614 (lost on zero-oscillation); vs shipped −4 446 (Δ −169).
Best: `ash_amp3x` = +15 845.
Day-0 real: +2 943 (shipped +2 541, Δ +402).

## Build
```
PYTHONPATH=. .venv/bin/python -m src.scripts.round_1.export_round1_ash_deep_f2a
```
