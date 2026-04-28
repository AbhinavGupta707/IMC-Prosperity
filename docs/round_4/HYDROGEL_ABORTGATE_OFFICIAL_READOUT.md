# HYDROGEL Abort-Gate Official Readout

Date: 2026-04-27

## What was uploaded

| zip | decoded run | HYD overlay |
|---|---|---|
| `abortgateflat60.zip` | `abortgate15_flat60` | target flat until 60k, abort at 40k if 20k->40k slope < 15 |
| `abortgatelong2060.zip` | `abortgate15_long20_60` | target +20 until 60k, abort at 40k if slope < 15 |
| `abortgate4060.zip` | `abortgate15_long40_60` | target +40 until 60k, abort at 40k if slope < 15 |
| `abortgate18flat60.zip` | `abortgate18_flat60` | target flat until 60k, abort at 40k if slope < 18 |

All four are on the validated `sell7` full-submission base.

The attribution script was updated and rewrote:

- `outputs/round_4/hydrogel_probes/official_hydrogel_probe_batch_summary.csv`

## Official results

| run | total PnL | HYD PnL | non-HYD PnL | HYD touch-liquidated | final HYD pos | HYD max DD |
|---|---:|---:|---:|---:|---:|---:|
| combo_stack_hardlong40_60k | 77,468.24 | 7,151 | 70,317.24 | 5,501 | -200 | -4,038.75 |
| combo_sell7_hardlong80_60k | 74,632.81 | 7,657 | 66,975.81 | 6,007 | -200 | -4,038.75 |
| abortgate15_long40_60 | 74,126.81 | 7,151 | 66,975.81 | 5,501 | -200 | -4,038.75 |
| abortgate15_long20_60 | 73,815.81 | 6,840 | 66,975.81 | 5,190 | -200 | -4,038.75 |
| abortgate15_flat60 | 73,409.81 | 6,434 | 66,975.81 | 4,784 | -200 | -4,038.75 |
| abortgate18_flat60 | 73,409.81 | 6,434 | 66,975.81 | 4,784 | -200 | -4,038.75 |
| combo_sell7_hardlong40_60k | 74,126.81 | 7,151 | 66,975.81 | 5,501 | -200 | -4,038.75 |
| hardlong80_60k | 72,563.90 | 7,657 | 64,906.90 | 6,007 | -200 | -4,038.75 |
| hardlong40_60k | 72,057.90 | 7,151 | 64,906.90 | 5,501 | -200 | -4,038.75 |
| hardflat60k | 71,340.90 | 6,434 | 64,906.90 | 4,784 | -200 | -4,038.75 |

## Was this expected?

Yes. The abort gate passes on this official/day-3 prefix, so the uploaded
abortgate strategies collapse to the corresponding hardflat/hardlong behavior:

- `abortgate15_flat60` = `hardflat60k` HYD PnL.
- `abortgate15_long40_60` = `hardlong40_60k` HYD PnL.
- `abortgate18_flat60` = `hardflat60k` HYD PnL because the official
  20k->40k slope still passes the stricter gate.
- `abortgate15_long20_60` lands between flat and long40, as designed.

The local proxy was also calibrated:

| run | official HYD | local proxy HYD | official - local |
|---|---:|---:|---:|
| abortgate15_long40_60 | 7,151 | 7,370 | -219 |
| abortgate15_long20_60 | 6,840 | 7,026 | -186 |
| abortgate15_flat60 | 6,434 | 6,626 | -192 |
| abortgate18_flat60 | 6,434 | 6,626 | -192 |

This is good simulator calibration. It means the local replay is directionally
useful but optimistic by about 180-220 HYD on this family.

## Impact

The abortgate did not add official 100k PnL versus the corresponding hard
targets. Its value is not visible on this single official path because the gate
does not reject the path.

The impact is structural:

- `abortgate15_long40_60` should dominate blind `hardlong40_60k` in design:
  same official result when the high path is real, with an escape hatch when the
  high path fails.
- `abortgate15_long20_60` is the best middle-risk candidate:
  it gives up `311` HYD versus long40, but retains `406` over flat.
- flat15 and flat18 are fallback/defensive references, not alpha maximizers.

## Capture versus hindsight

Prior official HYD oracle estimates:

- force-flat L1 oracle: `15,585`;
- terminal-mark L1 oracle: `18,017`.

| run | HYD / terminal oracle | touch-liquidated HYD / force-flat oracle |
|---|---:|---:|
| hardlong80 / sell7 hardlong80 | 42.5% | 38.5% |
| abortgate15 long40 | 39.7% | 35.3% |
| abortgate15 long20 | 38.0% | 33.3% |
| abortgate15 flat | 35.7% | 30.7% |

So we are not "fully optimized" versus theoretical max. But the remaining gap
is mostly dynamic hindsight path-recycling, not clean first-entry alpha. Chasing
it with more fixed opening variants is likely overfit.

## What we learn

1. The high-regime architecture is confirmed.
   - Immediate inventory override after the 20k-30k trigger is the right class.
   - Slow slopegate was too conservative.

2. Abortgate is insurance, not a new alpha source on the 100k path.
   - This is fine. It is exactly what an abort gate should look like when the
     path is genuinely high.

3. The long overlay is monotonic on this path.
   - flat: `6,434`;
   - long20: `6,840`;
   - long40: `7,151`;
   - long80: `7,657`.
   - But rolling stress worsens with larger long exposure, so this is a risk
     choice, not free money.

4. Strict flat18 is redundant for this path.
   - It has the same official result as flat15.
   - It may be slightly safer in rolling stress, but it is not an alpha
     candidate.

5. The non-HYD base matters more to total score now.
   - `combo_stack_hardlong40_60k` is the top uploaded total at `77,468.24`, but
     that improvement is non-HYD stack alpha, not new HYD alpha.

## Are we fully optimized?

HYD is close to optimized **within the robust first-entry / 60k-release
architecture**.

Not fully optimized versus theoretical max:

- best official HYD captures only about `40-43%` of terminal hindsight;
- touch-liquidated capture is about `35-39%` of force-flat hindsight.

But the remaining gap is not low-hanging fruit. It requires dynamic recycling
after release, and the evidence so far says fixed variants are now mostly
trading off official-path score against false-trigger robustness.

## Final HYD recommendation

For final 1M, do not use raw `hardlong80` as the default unless we explicitly
accept a high path bet.

Recommended HYD choice:

1. **Balanced/risk-seeking robust:** `abortgate15_long40_60`
   - Same HYD as hardlong40 on the official path.
   - Better architecture than hardlong40 because it can abort failed regimes.

2. **More conservative robust:** `abortgate15_long20_60`
   - Gives up `311` official HYD versus long40.
   - Lower long-overlay path risk.

3. **Defensive fallback:** `abortgate15_flat60` or `abortgate18_flat60`
   - Good if we decide long exposure is too path-fit.

If total-score maximizing on the current official calibration is the goal,
`combo_stack_hardlong40_60k` is the top uploaded result. If we wanted the
maximum 100k score only, a stack + hardlong80 variant would likely be higher,
but that is exactly the kind of overfit-risk escalation we should be careful
about for final unseen 1M.
