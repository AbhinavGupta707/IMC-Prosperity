# G5 — F3a with softer skew c=1

**Upload label:** G5 (Phase-G exploration — primary upgrade candidate).
**Factory:** `round1_ash_deep_g5_engine_config` (alias of `f3a`; same engine config).
**Inlined research:** `ash_shape_override.py` with `skew_coef=1.0`.

## Purpose

F3a uses linear skew coefficient = 2 (Phase-B B3 winner). Phase-G
local sweep showed c=1 delivers a HIGHER 3-day mean PnL (+3 495 vs
F3a's +3 446), continuing the monotone trend from c=8 → c=4 → c=2
found in Phase B. G5 tests whether the trend continues on official.

## Config
- ASH: strategy=`ash_shape_override`, fv=`weighted_mid`, m=2.5, t=0.5
- PEPPER: `buy_and_hold`, max_aggressive_size=80
- ShapeParams: `skew_mode="linear"`, `skew_coef=1.0` (vs F3a's 2.0),
  `flatten_mode="hard"`, `flatten_threshold=0.7`, `size_mode="constant"`

## Local numbers (Phase-G sweep)

| | local 3-day mean | maker | taker |
|---|---:|---:|---:|
| F3a (reference) | +3 446 | 5 | 701 |
| **G5 (skew c=1)** | **+3 495** | 7 | 695 |
| G6 (skew c=0.5) | +3 481 | 6 | 697 |
| baseline | +2 827 | 6 | 768 |

**Projected official**: ~+1 468 (using F3a's 0.42 transfer ratio).
**Projected Δ vs F3a**: +72 ASH PnL.

## Fingerprint

| | Value |
|---|---|
| Size | 91 047 bytes |
| SHA | `221b23c67c41b1d2ae9c84a98ed91a1c0b51ff533e8b7fcf4d119ad4e179c1f6` |
| Validator | 0 errors, 0 warnings |

## Hypothesis / risks

**Hypothesis**: softer inventory skew keeps quotes in the sweet spot
for longer. Phase-B showed c=8 → c=4 → c=2 monotone-improved local
PnL; Phase-G extends this to c=1 and c=0.5, with c=1 the peak.

**Risk**: very soft skew means quotes don't retreat from the touch
fast when position grows, so on a day with bigger position swings
the flatten-valve engagement could be delayed. Phase-G saw this
didn't happen on our 3-day local tape — position rarely exceeded
±25 anyway — but official behavior is uncertain.

**If G5 beats F3a**: upload G6 (skew c=0.5) next to find the true
peak.
**If G5 underperforms F3a**: the c=2 → c=1 step moved past the real
optimum; revert to F3a tuning.

## Build

```
PYTHONPATH=. .venv/bin/python -m src.scripts.round_1.export_round1_ash_deep_g5
```
