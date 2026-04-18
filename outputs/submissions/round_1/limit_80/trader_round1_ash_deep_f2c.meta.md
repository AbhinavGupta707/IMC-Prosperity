# trader_round1_ash_deep_f2c.py — metadata

**Upload label:** F2c (Phase-F batch 2, candidate c).
**Phase-F priority:** #1 (first upload in the Phase-E-revised order).
**Built:** 2026-04-16, commit `043faac`.

## What it is

A single-file Prosperity submission wrapping the `ash_deep_f2c` engine:

- **ASH_COATED_OSMIUM**
  - Strategy: `market_making` (shipped)
  - Fair value primary: **`weighted_mid`**
  - Fair value fallbacks: `(wall_mid, mid)`
  - Maker edge: 1.5, taker edge: 0.5
  - Inventory skew: 4.0, flatten threshold: 0.7
  - History length: 48, position limit: 80
- **INTARIAN_PEPPER_ROOT**
  - Strategy: `buy_and_hold` (shipped)
  - Fair value: `mid` (unused by buy-and-hold logic)
  - `max_aggressive_size`: 80 — one-tick fill to +80, then hold
  - Position limit: 80
- No Phase-9 fastsearch knobs (early_window = 0, per-side taker edges unset)

## Why this is the #1 Phase-F upload

Per `outputs/round_1/ash_deep_dive/phase_e/PHASE_E_MEMO.md` sec 4,
revised after the stress-tape analysis:

1. **F2c is the only tested ASH variant with zero losses on every
   Phase-E stress tape** (along with F3a and F3b, which also use
   weighted_mid but add shape-override or AS mechanisms).
2. The weighted_mid FV tracks mid tightly via a linearly-weighted
   rolling average, so it adapts to regime shifts naturally and
   never generates false cross signals on constant-mid tapes.
3. On the `ash_anchor_shift` tape (mid steps 10 000 → 10 025 at
   mid-day), F2c returns **+2 985 vs shipped C_h1_alt's −4 601** —
   a +7 585 swing. This single stress result is larger than the
   entire local-PnL dispersion across all 85 Phase-B/C/D cells.
4. The simpler mechanisms (weighted_mid alone, no extra skew or
   alpha-skew) reduce the "compound surprise" risk on official.

## Provenance

- Source factory: `src.core.config.round1_ash_deep_f2c_engine_config`
- Builder: `src.scripts.round_1.export_round1_ash_deep_f2c`
- Datamodel mode: `platform`
- Build commit: `043faac`
- SHA256 (current build): `ea7c9fbd9eac9f8ab71f626c41babf8b12c14d13ba4198705e6e574cb0dd684c`
  _(SHA changes each rebuild because the banner embeds the build timestamp; strategy logic bytes are deterministic at the pinned commit.)_
- Size: 100 971 bytes (soft cap 98 304, hard cap 102 400)
- Validator: 0 errors, 1 `size_approaching_limit` warning (same as every
  other pre-v2_clean bundle; within the hard 100 KiB cap).
- Smoke test: `Trader()` constructs cleanly, strategies
  `{market_making, buy_and_hold}` register, ASH/PEPPER configs
  match the intended values.

## Local-proxy PnL predictions

From `outputs/round_1/ash_deep_dive/phase_b/B1/results.csv`:

| Day | ASH PnL (local) |
|---|---:|
| day -2 | +2 914 |
| day -1 | +3 696 |
| day 0 | +3 387 |
| 3-day mean | +3 332 |

Expected-official rescale (Phase-A fill multipliers): **+2 102** PnL/day.

Compare to shipped `trader_round1_test.py` (C_h1_alt + buy_hold PEPPER):
- Expected-official rescale: +883
- Delta: **+1 219 / day**

## Stress-tape matrix (Phase E)

From `outputs/round_1/ash_deep_dive/phase_e/stress_matrix.csv`:

| Tape | F2c PnL | shipped PnL | Δ |
|---|---:|---:|---:|
| ash_flat | 0 | −4 446 | +4 446 |
| ash_amp3x | +24 067 | +15 424 | +8 644 |
| ash_narrow_spread | +6 403 | +5 063 | +1 341 |
| ash_thin_book | +1 557 | +1 324 | +234 |
| ash_anchor_shift | +2 985 | −4 601 | **+7 585** |
| ash_one_sided_heavy | +2 680 | +2 552 | +128 |
| day_0_real | +3 387 | +2 541 | +846 |

Every tape: non-negative Δ. Worst absolute PnL: 0 (on flat) — never
loses money on any tested regime.

## Reproducing

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_1.export_round1_ash_deep_f2c
```

Deterministic at the recorded commit; the banner embeds
`Built: 2026-04-16T12:14:53.494062+00:00 (commit 043faac)` which
changes on each rebuild.

## Open questions for the upload

1. **Does weighted_mid's stress-tape robustness transfer to the
   official environment?** Primary reason for uploading this first.
2. **Does the +846 day-0 local delta over shipped translate into a
   comparable official delta?** Rescale predicts +1 219; historical
   delta from the Phase-A fill-reality measurement was ±200 at worst.
3. **Is there a hidden regression in fill behavior?** The shipped
   `weighted_mid` estimator has been in the codebase since Phase 1
   but was never the primary on any shipped ASH leg.
