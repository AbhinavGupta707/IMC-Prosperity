# J2 — 3-level inner-heavy ladder (weights 3/1/1)

**Upload label:** J2 (Phase-J ladder variation).
**Factory:** `round1_ash_deep_j2_engine_config`.
**Inlined research:** `ash_ladder.py`.

## Purpose

I2a tied F3a officially (+1 365 vs +1 395). Post-mortem: edge/share
+29%, volume −29%, net zero. J2 biases the tick-rotation toward the
inner level (60% of ticks at edge=2.5) to recover F3a's volume base
while keeping 2/5 (20% each) outer coverage for deep-amplitude fills.

## Config

- edges = (2.5, 5.0, 8.0)
- size_mults = (1.0, 1.5, 2.0)
- weights = (3, 1, 1) → 60%/20%/20% tick allocation
- skew_coef = 2.0 (F3a linear)
- flatten_threshold = 0.7

## Local (Phase-J sweep)

| | local 3-day | maker | taker | markout_1 |
|---|---:|---:|---:|---:|
| F3a (ref) | +3 446 | 5 | 701 | ~+0.5 |
| I2a (observed) | +3 666 | 72 | 699 | +2.11 |
| **J2** | **+3 653** | **61** | 703 | +2.07 |

## Fingerprint
| Size | 86 989 bytes |
| SHA-256 | `edbcdb6c3d3a7c2dba9f08d459cd77abc4f6f4816fa11b448c388eb9397f9b41` |
| Validator | 0 errors, 1 size warning |

## Projected official

Using I2a's observed ladder transfer ratio (0.37) as a floor and
F3a's (0.42) as a ceiling:

- 3 653 × 0.37 = **+1 352** (floor) — essentially tied with F3a
- 3 653 × 0.40 (blended) = **+1 461** — **+66 over F3a**
- 3 653 × 0.42 = +1 534 — optimistic

Best point estimate: **+50 to +100 over F3a** if inner-heavy lifts the transfer ratio.

## Build
```
PYTHONPATH=. .venv/bin/python -m src.scripts.round_1.export_round1_ash_deep_j2
```
