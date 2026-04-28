# Mark55 Lite Interposition Official Readout

## Upload Set

These were the size-safe Mark55/Mark67 VELVET passive interposition probes
generated from `submission_r4_exp_stack_hydhardlong80_60k.py`.

Base reference:

- `expstack8060 / 516313`
- official PnL: `77,974.243774`

## Official 100k Results

| Upload | Submission id | Official PnL | Delta vs stack80 base | Final VELVET pos | Delta VELVET pos |
| --- | ---: | ---: | ---: | ---: | ---: |
| base `expstack8060` | 516313 | 77,974.2438 | 0.0000 | +161 | 0 |
| `bidonly markgate` | 522566 | 77,882.4938 | -91.7500 | +169 | +8 |
| `periodic s1 control` | 522689 | 77,971.2438 | -3.0000 | +161 | 0 |
| `twosided` markgate | 522799 | 77,884.3688 | -89.8750 | +165 | +4 |
| `always s1 control` | 522905 | 77,876.0563 | -98.1875 | +162 | +1 |
| `askonly markgate s1` | 523051 | 77,989.9938 | +15.7500 | +153 | -8 |

## What Changed

Only VELVET PnL moved materially. HYDROGEL and voucher final PnLs were unchanged
within rounding.

VELVET submission fill deltas versus base:

| Upload | VELVET trades | Buy qty | Sell qty | Net qty | Net cash | Delta net qty | Delta net cash |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| base | 32 | 401 | 240 | +161 | -835,190 | 0 | 0 |
| bidonly | 66 | 414 | 245 | +169 | -877,312 | +8 | -42,122 |
| periodic | 36 | 402 | 241 | +161 | -835,193 | 0 | -3 |
| twosided | 68 | 413 | 248 | +165 | -856,295 | +4 | -21,105 |
| always | 82 | 417 | 255 | +162 | -840,542 | +1 | -5,352 |
| askonly | 40 | 401 | 248 | +153 | -793,144 | -8 | +42,046 |

The Mark layer did get the intended counterparties:

- `bidonly`: +21 buys from Mark55, +9 buys from Mark67, but also displaced
  cheaper base buys from Mark14/Mark01/Mark22.
- `twosided`: same adverse bid-side behavior plus a few extra sells.
- `askonly`: +4 sells to Mark55 and +4 sells to Mark67, with no extra buys.

## Markout Read

Incremental VELVET fill markout versus base:

| Upload | 100-tick PnL | 1k PnL | 5k PnL | 10k PnL | Terminal PnL |
| --- | ---: | ---: | ---: | ---: | ---: |
| bidonly | +52.5 | +19.5 | -68.0 | -76.5 | -94.0 |
| periodic | -6.0 | +6.5 | -15.0 | +6.5 | -3.0 |
| twosided | +56.0 | +17.5 | -74.5 | -51.0 | -91.0 |
| always | +57.5 | +43.5 | -54.5 | -46.5 | -98.5 |
| askonly | 0.0 | -4.0 | -14.0 | +32.0 | +18.0 |

Interpretation:

- Bid-side Mark interposition had real short-horizon signal, but it decayed
  quickly and became negative by 5k/terminal.
- That is not an execution alpha on this base because the stack holds VELVET
  inventory for too long. The overlay increased an already-large long terminal
  VELVET position.
- Ask-only reduced long VELVET exposure by 8 units and gained a small terminal
  amount, but the 1k/5k markouts were negative and the sample was only 8 units.

## Verdict

This official batch fails the pre-registered Mark55 kill criterion:

- bidonly markgate did not beat periodic by `+100`; it lost to periodic by
  `-88.75`.
- twosided markgate also lost to periodic by `-86.875`.
- askonly was positive versus base by only `+15.75`, far below a meaningful
  100k calibration threshold.

So we did not find material Mark55 passive execution alpha. The result is still
useful because it was an actual fill-priority test, not a no-op:

- Mark IDs can steer who fills us.
- The economics are too small/adverse unless paired with a fast recycler or an
  existing need to reduce VELVET inventory.

## Implications

1. Do not integrate bid-side Mark55/Mark67 interposition into the final stack.
   It adds long VELVET in exactly the wrong risk direction.

2. Do not use two-sided Mark interposition. The bid side dominates and damages
   the result.

3. Ask-only Mark interposition is not proven alpha. Treat it as a possible
   inventory-reduction execution tweak, not as a standalone R4 edge.

4. The remaining Mark edge, if any, is likely not "follow Mark". It would have
   to be one of:
   - a fast explicit recycler that exits within 100-1000 ticks;
   - an ask-only passive exit channel when the VELVET strategy is already too
     long;
   - a separate HYDROGEL Mark38 passive-maker experiment, which has larger raw
     economics but high conflict risk with the confirmed HYD strategy.

## Next Decision

For final-candidate work, prioritize the main HYD/VELVET frontier over more
Mark55 uploads.

The only Mark upload that remains defensible is an ask-only matched-control
pair if upload budget is truly unlimited:

- ask-only Markgate size 1,
- ask-only periodic control size 1,
- ask-only always control size 1,
- optionally only when VELVET position is strongly long.

Expected value is low: this batch suggests a ceiling of tens of PnL per 100k,
not hundreds or thousands.
