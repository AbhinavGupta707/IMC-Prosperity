# K1 — J2_heavier (weights 4/1/1, 67% inner)

**Upload label:** K1 (Phase-K neighborhood tuning of J2 winner).
**Factory:** `round1_ash_deep_k1_engine_config`.
**Inlined research:** `ash_ladder.py`.

## Config
- edges = (2.5, 5.0, 8.0)
- size_mults = (1.0, 1.5, 2.0)
- weights = (4, 1, 1) → inner 67%, outers 16.5% each
- skew_coef = 2.0, flatten_threshold = 0.7

## Hypothesis
J2's transfer ratio 0.451 suggested inner-heavy UNDER-projects
locally. Push inner weight higher: 67% vs J2's 60%. If the
under-projection pattern holds, K1 could match or beat J2.

## Local (Phase-K)
| | local 3-day | maker | taker |
|---|---:|---:|---:|
| J2 (ref, observed +1 647) | +3 653 | 61 | 703 |
| **K1** | +3 516 | 40 | 699 |

## Fingerprint
| Size | 88 604 bytes |
| SHA-256 | `8ca6feb99392182ad9f27c6e9cc5d3d603f7390eeb93c5e74f43fcdd7ef3be35` |
| Validator | 0 errors, 1 size warning |

## Projected official (speculative)
- 3 516 × 0.451 (J2 transfer) = +1 586 (below J2)
- 3 516 × 0.50 (if heavier lifts ratio) = +1 758 (above J2)
