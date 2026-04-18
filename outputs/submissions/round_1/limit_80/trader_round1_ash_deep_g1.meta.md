# G1 — wall_mid + m=2.5 + linear skew c=2 (F3a tuning on wall_mid FV)

**Upload label:** G1 (Phase-G exploration extension).
**Factory:** `round1_ash_deep_g1_engine_config` (alias of `f2b`; same engine config).
**Inlined research:** `ash_shape_override.py` with `skew_coef=2.0`.

## Purpose

Tests whether F3a's +435 ASH PnL win over baseline comes from the
**fair-value choice** (weighted_mid) or from the **edge/skew tuning**
(m=2.5 + linear skew c=2). G1 swaps the FV back to wall_mid while
keeping F3a's edge/skew tuning; F3a is the reference.

## Config
- ASH: strategy=`ash_shape_override`, fv=`wall_mid`, m=2.5, t=0.5
- PEPPER: `buy_and_hold`, max_aggressive_size=80
- ShapeParams: `skew_mode="linear"`, `skew_coef=2.0`, `flatten_mode="hard"`,
  `flatten_threshold=0.7`, `size_mode="constant"`

## Local numbers (Phase-G sweep)

| | local 3-day mean | maker fills | taker fills |
|---|---:|---:|---:|
| F3a (reference) | +3 446 | 5 | 701 |
| **G1** | **+3 058** | 12 | 770 |
| baseline | +2 827 | 6 | 768 |

**Projected official**: ~+1 407 (using wall_mid transfer ratio 0.46)
— tied with F3a's observed +1 395 within noise.

## Fingerprint

| | Value |
|---|---|
| Size | 91 008 bytes |
| SHA | `3fe298d6c92bccee5d6c66523cb05fd1038a2d15bb7bf0470dbe7e4b829541e2` |
| Validator | 0 errors, 0 warnings |

## Build

```
PYTHONPATH=. .venv/bin/python -m src.scripts.round_1.export_round1_ash_deep_g1
```
