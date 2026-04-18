# trader_round1_ash_deep_f2d.py — metadata

**Upload label:** F2d (Phase-F batch 2, candidate d).
**Phase-F priority:** #7 (per revised order in PHASE_E_MEMO sec 4).
**Built:** 2026-04-16.

## What it is

Config-only variant of the F1 control:

- **ASH**: `wall_mid`, **maker_edge=2.5** (vs shipped 1.5), taker 0.5,
  skew 4.0, flatten 0.7, history 48.
- **PEPPER**: buy-and-hold, `max_aggressive_size=80`.

## Why this upload

Phase-B B2 sweep showed `maker_edge=2.5` produces 18 maker fills vs
6 on the shipped `maker_edge=1.5`, rescaling to +2 053 expected-official
(vs shipped +883). Phase-E stress-test flagged it as wall_mid-family
fragile on `ash_anchor_shift`, so it ranks behind the weighted_mid
candidates (F2c/F3a/F3b) but is still worth an upload as the cheapest
pure-config improvement over shipped.

## Fingerprint

| | Value |
|---|---|
| Factory | `src.core.config.round1_ash_deep_f2d_engine_config` |
| Builder | `src.scripts.round_1.export_round1_ash_deep_f2d` |
| Size | 101 955 bytes |
| SHA256 | `9fad86efa1798404b020e0c49b869e958598e785392466dcfe3614a8ebd1174d` |
| Validator | 0 errors, 1 `size_approaching_limit` warning |
| Local 3-day mean | +2 815 |
| Expected-official | +2 053 |

## Reproducing

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_1.export_round1_ash_deep_f2d
```
