# J7 — weighted 3/1/1/1 + spread-gated outer (combo)

**Upload label:** J7 (Phase-J ladder variation, combines J2 + J3).
**Factory:** `round1_ash_deep_j7_engine_config`.
**Inlined research:** `ash_ladder.py`.

## Purpose

Combine J2's inner-heavy weighting (50% at edge=2.5) with J3's
spread-gated outer (outer levels fire only when spread >= 16). Both
mechanisms attack the same problem: I2a's 75% time-at-outer caused
volume loss offset by the edge gain. J7 applies both filters so
outer levels only activate when they're both (a) their turn in the
rotation, and (b) the book spread justifies them.

## Config

- edges = (2.5, 5.0, 8.0, 12.0)
- size_mults = (1.0, 1.5, 2.0, 3.0)
- weights = (3, 1, 1, 1) → inner 50%, outers 17% each
- spread_gate_enabled = True, gate_spread = 16
- skew_coef = 2.0, flatten_threshold = 0.7

## Local (Phase-J sweep)

| | local 3-day | maker | taker |
|---|---:|---:|---:|
| F3a (ref) | +3 446 | 5 | 701 |
| I2a (observed) | +3 666 | 72 | 699 |
| **J7** | **+3 581** | **37** | 701 |

Lower local maker count than J2/J3 because spread-gating + inner
weighting double-filters outer-level fires. If both filters discard
low-value outer ticks correctly, each remaining outer fill is
higher-quality. Expected outcome: lower LOCAL PnL but HIGHER
transfer ratio.

## Fingerprint
| Size | 87 079 bytes |
| SHA-256 | `4c6560476f228d68a98927066ba2401ffff65e251d4957f3f42ed760e611427f` |
| Validator | 0 errors, 1 size warning |

## Projected official

- 3 581 × 0.37 = +1 325 (floor if transfer ratio doesn't improve)
- 3 581 × 0.41 = **+1 468** (blended, transfer improves)
- 3 581 × 0.42 = +1 504 (optimistic — transfer matches F3a)

## Build
```
PYTHONPATH=. .venv/bin/python -m src.scripts.round_1.export_round1_ash_deep_j7
```
