# K2 — J2_tight (outer at 4/6 instead of 5/8)

**Upload label:** K2 (Phase-K).
**Factory:** `round1_ash_deep_k2_engine_config`.
**Inlined research:** `ash_ladder.py`.

## Config
- edges = (2.5, 4.0, 6.0)
- size_mults = (1.0, 1.5, 2.0)
- weights = (3, 1, 1) → inner 60%, outers 20% each

## Hypothesis
ASH's dominant spread is 16 (each side ~8 ticks). Outer quotes at
edge=6 likely still sit INSIDE the book; edge=4 even more so. These
may fire at higher rates than edge=5/8 (J2's wider outers). Lower
edge per fill but higher fill rate — test whether the trade-off wins.

## Local (Phase-K)
| | local 3-day | maker | taker |
|---|---:|---:|---:|
| J2 (ref, +1 647) | +3 653 | 61 | 703 |
| **K2** | +3 497 | 26 | 700 |

Local maker count is low (26) because K2's "outer" edges are so
tight they likely collapse onto F3a-like quote levels in the
simulator. Official could diverge.

## Fingerprint
| Size | 88 583 bytes |
| SHA-256 | `6c62b9e5b8b957521bc03c9e347af796fe5c48fbc4bd17bceed079a326fc88fa` |
| Validator | 0 errors, 1 size warning |
