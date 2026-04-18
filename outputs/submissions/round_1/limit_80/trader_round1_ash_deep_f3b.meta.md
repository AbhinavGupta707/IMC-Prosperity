# F3b — weighted_mid + AS gamma=2e-6 (D7 hybrid)

**Phase-F priority:** #4 (weighted_mid stress-robust + AS quote formula).
**Factory:** `round1_ash_deep_f3b_engine_config`.
**Inlined research:** `ash_avellaneda_stoikov.py`.

## Config
- ASH: strategy=`ash_avellaneda_stoikov`, fv=`weighted_mid` (fallbacks wall_mid/mid), m=2.0, t=0.5
- PEPPER: `buy_and_hold`, max_aggressive_size=80
- AS params: γ=2e-6, σ=2.0, k=0.4, T=100000

## Fingerprint
- Size: 88 454 bytes
- SHA: `cef507ab9625b367e21eb293c312592783fec1da65078d6fa97247defe5c3104`
- Validator: 0 errors, 0 warnings

## Phase-E stress matrix
Zero losses on all 6 stress tapes (weighted_mid family).
`ash_anchor_shift` = +2 701 (vs shipped −4 601, Δ +7 302).
Day-0 real: +3 336.
