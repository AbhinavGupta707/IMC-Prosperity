# K5 — Asymmetric ladder (buy tight, sell wide)

**Upload label:** K5 (Phase-K asymmetric experiment).
**Factory:** `round1_ash_deep_k5_engine_config`.
**Inlined research:** `ash_ladder.py`.

## Config
- **Buy side:** edges=(2.5, 4.0, 6.0), weights=(3,1,1) → accumulate
  on shallow dips quickly.
- **Sell side:** edges=(2.5, 5.0, 8.0), weights=(3,1,1) → hold out
  for bigger upward reversions.
- size_mults=(1.0, 1.5, 2.0) on both sides.
- skew_coef=2.0, flatten_threshold=0.7.

## Hypothesis
First asymmetric per-side ladder. If ASH's OU process is slightly
asymmetric (sharp dips with slower recoveries, or vice versa),
different depths per side should outperform symmetric ladders.
Local +3 581 vs J2 +3 653.

**Design rationale for "flip" direction:** ASH mid sits slightly
above 10 000 mean (days 0: +1.6, day -1: +0.8). Slight upward
bias → sell deeper to exit longs at better prices; buy tighter to
accumulate inventory opportunistically.

## Local (Phase-K)
| | local 3-day | maker | taker |
|---|---:|---:|---:|
| J2 (ref) | +3 653 | 61 | 703 |
| **K5** | +3 581 | 45 | 700 |
| K4 (flip opposite) | +3 531 | 36 | 702 |

K5's variant (buy tight, sell wide) outperformed K4's opposite
direction locally.

## Fingerprint
| Size | 88 980 bytes |
| SHA-256 | `0b225c73ac74ae1fcc6ad40c76539193ed7a19b970dc8560cba5fb05d53bef03` |
| Validator | 0 errors, 1 size warning |
