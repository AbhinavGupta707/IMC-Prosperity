# I2a — 4-level ladder (tick-rotation 2.5/5/8/12)

**Upload label:** I2a (Phase-I post-Phase-H exploration — LADDER primary).
**Factory:** `round1_ash_deep_i2a_engine_config`.
**Inlined research:** `ash_ladder.py` with `AshLadderStrategy` +
`LadderParams(edges=(2.5,5,8,12), size_mults=(1,1.5,2,3))`.

## Purpose

The first variant to beat F3a on local 3-day mean PnL. Tests whether
tick-rotation multi-level quoting exploits the OU amplitude
distribution that F3a's single-edge approach misses.

Phase H established ASH is OU-mean-reverting (half-life 2 ticks)
around a near-constant fair value, with mid oscillations of ±1-10
ticks and occasional ±12-tick excursions. F3a's `maker_edge=2.5`
quote catches small oscillations but leaves outer-amplitude moves
unfilled at their full edge. I2a rotates through 4 edge levels so
that each gets ~2 500 of the ~10 000 ticks per day.

## Config

- ASH: strategy=`ash_ladder`, fv=`weighted_mid`, m=2.5, t=0.5.
- PEPPER: `buy_and_hold`, max_aggressive_size=80 (identical to F-series).
- LadderParams:
  - edges = (2.5, 5.0, 8.0, 12.0)
  - size_mults = (1.0, 1.5, 2.0, 3.0)
  - skew_coef = 2.0 (F3a linear skew)
  - flatten_threshold = 0.7

## Local numbers (Phase-I sweep)

| | local 3-day mean | maker | taker | markout_1 | exp_off |
|---|---:|---:|---:|---:|---:|
| F3a (reference) | +3 446 | 5 | 701 | ~+0.5 | — |
| **I2a (ladder 4-lvl)** | **+3 666** | **72** | **699** | +2.11 | +9 834 |
| I2d (ladder 5-lvl) | +3 636 | 58 | 702 | +2.06 | +8 035 |
| I2b (ladder 3-lvl) | +3 545 | 52 | 704 | +2.03 | +7 095 |
| I2c (ladder 2-lvl) | +3 472 | 27 | 701 | +2.01 | +3 903 |

## Fingerprint

| | Value |
|---|---|
| Size | 84 391 bytes |
| SHA-256 | `820b70a9acf8d90a44e9a7a2f14a148ccd85d1d1358fd233852e9817ee9be386` |
| Validator | 0 errors, 1 warning (size over soft-budget, under hard) |

## Predictions

- **Empirical transfer (0.42, trust more):** 3 666 × 0.42 ≈ +1 540.
  Δ vs F3a = +145 (+10% over F3a's observed +1 395).
- **Fill-scaled (untrusted after H5):** +9 834/day. Almost certainly
  overstated. Ignore.
- **Honest point estimate:** +100 to +300 over F3a officially.

## Hypothesis / risks

**Hypothesis:** multi-level maker quotes catch OU deviations at
multiple amplitudes, adding 67 maker fills at higher per-fill edge
without sacrificing taker economics.

**Risks:**
- **Tick-rotation != simultaneous multi-level.** Each level is only
  quoted 25% of the time. If queue-position matters officially
  (orders must persist to earn priority), rotation may underperform
  a true concurrent ladder.
- **Outer levels may not fill officially.** The 12-tick edge
  catches rare ±12 moves locally — IMC's real flow may not reach
  that deep.
- **Local simulator may over-fill maker.** Phase-A found local
  maker fills are ~28× denser than official; our 72 maker count
  could represent only 2-3 officially. Still +ve vs F3a's 5, but
  smaller absolute delta.

## If result

- **I2a beats F3a by >+100 ASH:** ladder hypothesis confirmed.
  Follow up with I2d (5-level) and test asymmetric ladders, or
  pursue engine-level true-concurrent multi-level.
- **I2a matches F3a within ±100:** tick-rotation doesn't translate
  but the amplitude-coverage idea is right. Consider architectural
  change to emit simultaneous multi-level quotes.
- **I2a loses:** the 72 local maker fills were simulator artifacts.
  Discount local multi-level testing and fall back to F3a as the
  shipped strategy.

## Build

```
PYTHONPATH=. .venv/bin/python -m src.scripts.round_1.export_round1_ash_deep_i2a
```
