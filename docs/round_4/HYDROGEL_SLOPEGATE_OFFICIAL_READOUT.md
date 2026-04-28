# HYDROGEL Slopegate Official Readout

Date: 2026-04-27

## New official uploads parsed

| uploaded zip | decoded run | strategy |
|---|---|---|
| `slopgate4060.zip` | `slopegate15_cap40_flat60` | cap short at -40 until 40k, require +15 slope, then flat to 60k |
| `slopegatelong4060.zip` | `slopegate15_cap40_long40_60` | same gate, then +40 long to 60k |
| `slopgaet 8060.zip` | `slopegate18_cap80_flat60` | defensive cap -80, require +18 slope, then flat to 60k |
| `exphardlong4060.zip` | `combo_sell7_hardlong40_60k` | integrated sell7-style base plus hardlong40 HYD |

The official attribution script now includes these runs and rewrote:

- `outputs/round_4/hydrogel_probes/official_hydrogel_probe_batch_summary.csv`

## Official HYD results

| run | total PnL | HYD PnL | touch-liquidated HYD | final HYD pos | HYD max drawdown |
|---|---:|---:|---:|---:|---:|
| hardlong80_60k | 72,563.90 | 7,657 | 6,007 | -200 | -4,038.75 |
| hardlong40_60k | 72,057.90 | 7,151 | 5,501 | -200 | -4,038.75 |
| combo_sell7_hardlong40_60k | 74,126.81 | 7,151 | 5,501 | -200 | -4,038.75 |
| bid10052_70k | 71,957.90 | 7,051 | 5,401 | -200 | -4,038.75 |
| hardflat60k | 71,340.90 | 6,434 | 4,784 | -200 | -4,038.75 |
| slopegate15_cap40_long40_60 | 70,843.90 | 5,937 | 4,287 | -200 | -4,038.75 |
| slopegate15_cap40_flat60 | 70,521.90 | 5,615 | 3,965 | -200 | -4,038.75 |
| cap40_60k | 70,048.90 | 5,142 | 3,492 | -200 | -4,038.75 |
| slopegate18_cap80_flat60 | 70,018.90 | 5,112 | 3,462 | -200 | -4,038.75 |
| cap80_60k | 69,200.90 | 4,294 | 2,644 | -200 | -4,432.50 |
| old_flat995 | 66,586.90 | 1,680 | 30 | -200 | -8,780.62 |

All high-regime variants still finish `-200`, so the absolute official HYD
score has the same `-1,650` terminal touch-liquidation risk. The marginal
ranking between high-regime variants is still mostly cash-path signal, because
the final mark exposure is identical.

## Critical read

The slopegates worked mechanically, but they did not beat hardflat/hardlong on
the official 100k path. This is expected and meaningful:

- The official/day-3 prefix reveals the high path early at `21.5k`.
- Hardflat/hardlong act immediately.
- Slopegate waits until `40k`, allowing the base sleeve to carry a bounded
  short during a known rising leg.
- That delay costs about `819` HYD PnL versus hardflat and about `1,214`
  versus hardlong40 on this official path.

This is not a failure of the high-regime thesis. It tells us where the alpha is:
**the valuable inventory decision begins immediately after the 20k-30k trigger,
not only after the 40k confirmation.**

## Marginal signal

| comparison | HYD delta |
|---|---:|
| slopegate15 cap40 flat vs old_flat995 | +3,935 |
| slopegate15 cap40 flat vs cap40_60k | +473 |
| slopegate15 cap40 long40 vs slope flat | +322 |
| hardflat60k vs slope flat | +819 |
| hardlong40_60k vs slope long40 | +1,214 |
| hardlong80_60k vs hardlong40_60k | +506 |

The `+322` from the long40 overlay is real on this 100k path, but small. It is
not the main alpha. The main alpha is avoiding the bad early short and releasing
around 60k.

## Robustness versus official score

Rolling false-trigger stress from historical 100k windows:

| policy | official HYD | rolling overlay mean | worst window | positive rate |
|---|---:|---:|---:|---:|
| hardlong80_60k | 7,657 | -5,503 | -23,680 | 23.1% |
| hardlong40_60k | 7,151 | -4,271 | -19,840 | 25.6% |
| hardflat60k | 6,434 | -3,039 | -16,000 | 27.4% |
| slopegate15 cap40 long40 | 5,937 | -2,373 | -13,440 | 21.4% |
| slopegate15 cap40 flat | 5,615 | -2,101 | -13,440 | 23.1% |
| cap40_60k | 5,142 | -2,431 | -12,800 | 27.4% |
| slopegate18 cap80 flat | 5,112 | -1,664 | -10,680 | 24.8% |

This is the tradeoff:

- Hardlong80 is best on the uploaded 100k path and worst on false-trigger
  stress.
- Slopegate18 cap80 is the best defensive 1M candidate, but gives up too much
  official alpha to be an alpha-maximizer.
- Slopegate15 cap40 flat/long is a useful middle ground, but the 40k delay is
  too conservative if the final unseen 1M has the same early high-path behavior.

## What this says about overfitting

The hardlong family is locally inflated by the known official/day-3 high prefix.
It is still real alpha on that path, not a terminal-mark artifact, but the
rolling stress says it is a path bet. The slopegate uploads did not disprove
hardlong; they quantified the insurance premium.

For final unseen 1M, the question is not "slopegate or hardlong" in isolation.
The better design is:

1. Act early enough to avoid the bad short after the 20k-30k trigger.
2. Add an abort gate around 40k if the path fails to persist.
3. Keep long overlay modest unless official and stress both support it.

## Next alpha extraction probe

The best next HYD probe is an **abort-gated hardflat/hardlong**, not another
slow slope-gate:

- trigger at `mid >= 10020` during `20k-30k`;
- immediately force flat, or flat plus small long;
- at `40k`, require `20k->40k` slope >= `15-18`;
- if failed, abort and flatten/release back to base;
- if passed, continue to 60k release.

Local exact replay for this shape:

| candidate | official proxy HYD | day3 1M HYD | hist all 1M HYD |
|---|---:|---:|---:|
| abortgate15_flat60 | 6,613 | 55,563 | 166,936 |
| abortgate15_long40_60 | 7,025 | 55,975 | 167,348 |

Rolling stress for the same family is better than blind hardflat/hardlong on
mean, though not as defensive as cap80:

| family | rolling overlay mean | worst window | official-like overlay |
|---|---:|---:|---:|
| abortgate flat60, threshold 15 | -2,479 | -16,800 | +7,000 |
| abortgate long40, threshold 15 | -2,750 | -16,800 | +7,400 |
| hardflat fixed60k | -3,039 | -16,000 | +7,000 |
| hardlong40 fixed60k | -4,271 | -19,840 | +7,760 |

This is the most interesting path to extract more HYD alpha without simply
doubling down on overfit.

## Current recommendation

For pure official 100k score:

- `combo_sell7_hardlong40_60k` is the current best uploaded result at
  `74,126.81`.
- A `sell7 + hardlong80_60k` combo would likely score around `74.6k` on this
  same path, but it is the highest overfit-risk HYD choice.

For final 1M robustness:

- Prefer an abort-gated flat/long probe next.
- If forced to choose only among uploaded HYD variants, use:
  - risk-seeking: `hardlong40_60k`;
  - balanced: `slopegate15_cap40_long40_60`;
  - defensive: `slopegate18_cap80_flat60`.

I would not choose `hardlong80_60k` as the final 1M HYD default unless we are
explicitly accepting the public-prefix path bet.
