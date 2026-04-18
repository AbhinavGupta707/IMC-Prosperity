# J3 — spread-gated 4-level ladder

**Upload label:** J3 (Phase-J ladder variation).
**Factory:** `round1_ash_deep_j3_engine_config`.
**Inlined research:** `ash_ladder.py`.

## Purpose

Test whether gating outer ladder levels to wide-spread regimes
improves the local→official transfer. Rationale: when book spread
is tight (<16), a quote at edge=12 sits far outside the touch and
adds no value. In those ticks we fall back to the inner level (2.5).
When spread ≥16, the full ladder fires.

Spread distribution observed: 58% at 16, 22% at 18-19, 10% at 10-11.
J3 fires the full ladder on ~80% of ticks (the >=16 regime).

## Config

- edges = (2.5, 5.0, 8.0, 12.0)
- size_mults = (1.0, 1.5, 2.0, 3.0)
- weights = None (equal rotation when ladder is active)
- spread_gate_enabled = True, gate_spread = 16
- skew_coef = 2.0, flatten_threshold = 0.7

## Local (Phase-J sweep)

| | local 3-day | maker | taker |
|---|---:|---:|---:|
| F3a (ref) | +3 446 | 5 | 701 |
| I2a (observed) | +3 666 | 72 | 699 |
| **J3** | **+3 631** | **61** | 700 |

## Fingerprint
| Size | 87 028 bytes |
| SHA-256 | `9311f3f4b88a4d9fe9b07d229393816d9eb09d96d205f0652a49bc95432efd4f` |
| Validator | 0 errors, 1 size warning |

## Projected official

- 3 631 × 0.37 = +1 343 (floor)
- 3 631 × 0.40 = **+1 452** (blended) — **+57 over F3a**

## Build
```
PYTHONPATH=. .venv/bin/python -m src.scripts.round_1.export_round1_ash_deep_j3
```
