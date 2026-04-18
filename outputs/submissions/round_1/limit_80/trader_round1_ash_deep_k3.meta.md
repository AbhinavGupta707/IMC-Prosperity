# K3 — J2 + d=12 outer (4-level, weights 3/1/1/1)

**Upload label:** K3 (Phase-K).
**Factory:** `round1_ash_deep_k3_engine_config`.
**Inlined research:** `ash_ladder.py`.

## Config
- edges = (2.5, 5.0, 8.0, 12.0)
- size_mults = (1.0, 1.5, 2.0, 3.0)
- weights = (3, 1, 1, 1) → inner 50%, outers 16.7% each

## Hypothesis
J2's structure plus a 4th outer level at d=12 to catch the rare
extreme excursions. I2a (equal-weight 4-level including d=12) got
31 shares at d=9-10 that F3a missed entirely. Adding the d=12 level
while keeping inner-heavy weighting tests whether extreme-move
coverage adds edge without cannibalizing inner volume.

## Local (Phase-K)
| | local 3-day | maker | taker |
|---|---:|---:|---:|
| J2 (ref) | +3 653 | 61 | 703 |
| **K3** | +3 582 | 38 | 701 |

Lower maker count than J2 (38 vs 61) because 4 levels × 3/1/1/1 =
50% inner vs J2's 60%. But the d=12 coverage is new.

## Fingerprint
| Size | 88 563 bytes |
| SHA-256 | `8439946da617db252e6c630c58f8ac36fc18f2ad5c38b3470fa24f1eb6143d52` |
| Validator | 0 errors, 1 size warning |
