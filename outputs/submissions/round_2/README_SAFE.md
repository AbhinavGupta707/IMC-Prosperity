# Round-2 SAFE submission bundle — provenance manifest

This is the **defense-in-depth** Round-2 upload candidate, built to
maximise the 5th-percentile floor PnL across observed R2 official
test runs. Use this bundle when you want the lowest-variance,
most-hedged option.

## Variant

| Field | Value |
|---|---|
| Variant name | `round2_promoted_safe` |
| File | [`trader_round2_promoted_safe.py`](trader_round2_promoted_safe.py) |
| Source factory | `src.core.config.round2_v5micro_wide113_engine_config` |
| Export script | `src.scripts.round_2.export_round2_submission --killswitches --bid 350` |
| Bundle SHA256 | `4a612e12706c9cbab8ba3dd1d0bd47119831f79f95a9bbffae699649d0497a22` |
| Bundle size | 84,065 bytes (68% of validator hard cap) |
| Validator | 0 errors / 0 warnings |
| `Trader().bid()` | returns 350 ✅ |

## Why this variant for "safe / can't go negative"

Across **16 R2 official test runs** (4 variants × 4 iterations,
1 day × 1k snaps each):

| Variant | mean | σ | min | 5th-pct floor |
|---|---:|---:|---:|---:|
| **`Killswitch` (this bundle)** | +7,812 | **166** | **+7,635** | **+7,538** |
| `Ash L1` | +7,952 | 248 | +7,601 | +7,542 |
| `v5` (R1 stack rebuilt) | +7,972 | 442 | +7,399 | +7,242 |
| `Promoted` (default) | +7,654 | 366 | +7,295 | +7,050 |

- **Lowest variance** (σ 166) → most predictable outcome
- **Highest minimum** observed (+7,635 → ~+76k scored)
- 5th-percentile floor tied with `Ash L1` for the safest variant
- Adds an **explicit circuit-breaker layer** (kill switches) — defense
  against unseen adverse tape, even if redundant on observed tape

The mean PnL is ~140 XIRECs lower than `Ash L1`/`v5` (within 1σ).
This is the price of the safety layer.

## Embedded configurations

### ASH_COATED_OSMIUM (batch-D1 sweep winner: `wide_w113`)

`AshLadderStrategy` with `LadderParams`:

| Field | Value |
|---|---|
| `edges` | `(3.0, 5.0, 8.0)` (wide) |
| `size_mults` | `(1.0, 2.0, 3.0)` |
| `weights` | `(1, 1, 3)` (outer-heavy) |
| `skew_coef` | `1.0` |
| `flatten_threshold` | `0.7` |

### INTARIAN_PEPPER_ROOT (R1 v5_micro **+ batch-B kill switches**)

`PepperCoreLongStrategy` with `CoreLongParams` (V5_MICRO + kills):

| Field | Value | Source |
|---|---:|---|
| All `V5_MICRO_PARAMS` (open_seed=65, window=500, taker exec, base/ceiling=80, no_short=True, guard_window=32, guard_negative_slope=0.01, etc.) | unchanged | R1 winner |
| `kill_slope_window` | `50` | batch-B |
| `kill_consecutive_neg_slope_n` | `20` | batch-B |
| `kill_slope_pause_snaps` | `50` | batch-B |
| `kill_residual_threshold` | `35.0` | batch-B |
| `kill_residual_release` | `15.0` | batch-B |
| `kill_step_move_threshold` | `40.0` | batch-B |
| `kill_step_move_pause_snaps` | `10` | batch-B |
| `kill_intraday_pnl_threshold` | `2500.0` | batch-B |

The kill switches are 4 independent signals (slope / residual /
step-move / intraday-PnL). Any one tripping pauses BUY-side trading
for a configured number of snapshots; the existing
`guard_negative_slope` machinery still runs underneath.

### MAF auction bid (`Trader.bid()`)

**Bid = 350 XIRECs** (EV-max under empirically derived v ≈ 3,000).

| bid | EV at v=3k | downside if v=0 | algo + bid net (5th-pct) |
|---:|---:|---:|---:|
| 0 | +0 | 0 | +75,383 |
| 200 | +1,292 | −168 | +76,200 |
| **350** | **+2,220** | **−294** | **+76,920** ← chosen |
| 500 | +2,125 | −420 | +76,800 |
| 2,300 | +691 | −2,270 | +75,500 |

Bid 350 is the strict EV-max at v=3,000. Worst-case downside if v
turns out to be 0 (extra access does nothing): −294 XIRECs (~0.4%
of expected algo PnL). Bidding 0 leaves +2k of expected EV on the
table for ~zero safety gain.

Full analysis: [`outputs/round_2/maf_bid_decision.md`](../../round_2/maf_bid_decision.md).

## Expected scored PnL

Test sandbox is 1 day × 1k snaps = 10% of scored length. Scaling by 10:

| metric | value |
|---|---:|
| Mean (4-run) | +7,812 → **+78,120** scored |
| 5th-pct floor | +7,538 → **+75,380** scored |
| Min observed | +7,635 → **+76,350** scored |
| Plus MAF bid 350 EV (mixture) | +2,220 → **+22,200** scored if won (one-shot) |
| **Net mean (algo + bid EV)** | | **~+78,200** scored |
| **Net 5th-pct floor** | | **~+76,900** scored |

**P(algo PnL > 0) ≈ 100%** based on observed runs. Even pessimistic
extrapolations land comfortably at +70k+ scored.

## Reproducing the bundle

```bash
# Safety bundle (defense-in-depth):
PYTHONPATH=. .venv/bin/python -m src.scripts.round_2.export_round2_submission --killswitches --bid 350

# Default bundle (slightly higher mean, no kill switches):
PYTHONPATH=. .venv/bin/python -m src.scripts.round_2.export_round2_submission --bid 500

# Validate:
PYTHONPATH=. .venv/bin/python -m src.scripts.validate_submission outputs/submissions/round_2/trader_round2_promoted_safe.py

# Verify fingerprint:
shasum -a 256 outputs/submissions/round_2/trader_round2_promoted_safe.py
```

## Decision rationale (vs the default bundle)

The default `trader_round2_promoted.py` (no kills, bid 500) has:
- Mean +7,654 ± 366 → +76.5k scored
- 5th-pct floor +7,050 → +70.5k scored

The safe `trader_round2_promoted_safe.py` (kills on, bid 350) has:
- Mean +7,812 ± 166 → +78.1k scored
- 5th-pct floor +7,538 → +75.4k scored

The safe bundle has **higher mean AND higher floor AND lower variance**.
The +5k 5th-percentile improvement comes from kill switches narrowing
the worst-case tape distribution.

## What this bundle does NOT change vs the default

- ASH ladder (still `wide_w113`)
- Engine factory (still `round2_v5micro_wide113_engine_config`)
- Bundler / banner redaction / validator behaviour
- All other PEPPER `V5_MICRO_PARAMS` fields

The ONLY differences are: PEPPER kill thresholds populated, and
bid_value = 350.
