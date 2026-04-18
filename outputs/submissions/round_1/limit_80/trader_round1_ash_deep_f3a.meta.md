# trader_round1_ash_deep_f3a.py — metadata

**Upload label:** F3a (Phase-F batch 3, candidate a).
**Phase-F priority:** #3 (per revised order in PHASE_E_MEMO sec 4).
**Built:** 2026-04-16. First Phase-F bundle to inline a research-only ASH strategy.

## What it is

The Phase-D D5 empirical stack, packaged for official upload:

- **ASH**
  - Strategy: **`AshShapeOverrideStrategy`** (research-only, inlined at bundle tail)
  - Fair value: `weighted_mid`, fallbacks `(wall_mid, mid)`
  - Maker edge: 2.5, taker edge: 0.5
  - `ShapeParams`: `skew_mode="linear"`, `skew_coef=2.0`,
    `flatten_mode="hard"`, `flatten_threshold=0.7`, `size_mode="constant"`
  - Position limit: 80
- **PEPPER**: buy-and-hold, `max_aggressive_size=80` (Phase-F pin)

## Why this upload

From `PHASE_D_MEMO.md` sec 2:

> "D5 set an all-time local-PnL record (+3 446). [...] If the
> fill-reality rescale is too harsh, D5 could surprise."

From `PHASE_E_MEMO.md` sec 3:

> "Three candidates survive every tape without a loss: F2c, F3a,
> F3b. All three use weighted_mid fair value."

F3a delivers the highest local PnL of any cell tested across
Phase B/C/D **and** passes every Phase-E stress tape with zero loss.

## Fingerprint

| | Value |
|---|---|
| Factory | `src.core.config.round1_ash_deep_f3a_engine_config` |
| Builder | `src.scripts.round_1.export_round1_ash_deep_f3a` |
| Inlined research module | `src/strategies/ash_shape_override.py` |
| Strategy registry entry | `ash_shape_override` (bundle-local, NOT shipped) |
| Size | 90 760 bytes (**under soft cap**, no warnings) |
| SHA256 | `c36412138f13d58fb81e76f774bb63cdcb4ef1f63db196de45ccc9f2d8ccd218` |
| Validator | 0 errors, 0 warnings |
| Local 3-day mean ASH | +3 446 |
| Expected-official | +1 012 (rescale) / +3 346 on day_0_real |

## Stress-matrix row (Phase E)

| Tape | F3a PnL | shipped PnL | Δ |
|---|---:|---:|---:|
| ash_flat | 0 | −4 446 | +4 446 |
| ash_amp3x | +23 489 | +15 424 | +8 066 |
| ash_narrow_spread | +6 327 | +5 063 | +1 264 |
| ash_thin_book | +1 572 | +1 324 | +248 |
| ash_anchor_shift | +3 168 | −4 601 | **+7 769** |
| ash_one_sided_heavy | +2 710 | +2 552 | +158 |
| day_0_real | +3 346 | +2 541 | +805 |

Every tape: non-negative Δ vs shipped C_h1_alt.

## Bundle-tail wiring

The export script mirrors the v2_clean pipeline:

1. Standard live bundle via `build_submission_source(platform)`
2. Patch `Trader.__init__`'s default config to call
   `round1_ash_deep_f3a_engine_config`
3. Strip `src/strategies/ash_shape_override.py` via the shipped
   `strip_module` helper; append its body as a new module block
4. Append wiring appendix that:
   - materializes `_F3A_SHAPE_PARAMS = ShapeParams(...)`
   - defines `_f3a_ash_strategy_factory(fve, sig) -> AshShapeOverrideStrategy(...)`
   - rebinds `KNOWN_STRATEGY_NAMES` to include `"ash_shape_override"`
   - rebinds `STRATEGY_REGISTRY` to include the factory under that name
5. Minify via v2_clean's docstring/comment/blank-line stripper

## Reproducing

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_1.export_round1_ash_deep_f3a
```

Deterministic apart from banner timestamp; strategy logic bytes are
fixed at the recorded commit.

## Smoke test record

```python
import trader_round1_ash_deep_f3a as mod
trader = mod.Trader()
# ASH strategy class: AshShapeOverrideStrategy (bundle-local)
# Params: ShapeParams(skew_mode='linear', skew_coef=2.0, flatten_mode='hard', ...)
# orders emitted on a 2-product state: {'ASH': 2, 'PEPPER': 2}
```

## Open questions

1. **Does D5's local PnL ceiling transfer to official?** This is the
   central question the F3a upload answers.
2. **Does the weighted_mid anchor-shift robustness manifest on a
   real day with anchor drift?** Phase-A measured tiny real drifts
   (+2.67, +0.79 per day); F3a is the cleanest test.
