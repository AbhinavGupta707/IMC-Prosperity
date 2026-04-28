# HYDROGEL Final Abort-Gate Upload Set

Date: 2026-04-27

## Purpose

This is the final HYDROGEL test set before choosing the Round 4 submission.
These are not random parameter shots. They test one structural thesis:

> Act immediately after an early high-regime trigger, but add a 40k abort gate
> so false high-regime triggers do not force us into a bad 60k hold.

All files are built on the validated `sell7` full-submission base. Non-HYD
logic is unchanged; only the HYD high-regime overlay varies.

## Upload files

| priority | file | HYD overlay | reason |
|---:|---|---|---|
| 1 | `outputs/submissions/r4/submission_r4_final_sell7_hyd_abortgate15_long20_60.py` | target +20 to 60k, abort if 20k->40k slope < 15 | best balanced alpha/risk bridge |
| 2 | `outputs/submissions/r4/submission_r4_final_sell7_hyd_abortgate15_long40_60.py` | target +40 to 60k, abort if slope < 15 | max reasonable alpha without long80 overfit |
| 3 | `outputs/submissions/r4/submission_r4_final_sell7_hyd_abortgate15_flat60.py` | target flat to 60k, abort if slope < 15 | robust core edge, no long overlay |
| 4 | `outputs/submissions/r4/submission_r4_final_sell7_hyd_abortgate18_flat60.py` | target flat to 60k, abort if slope < 18 | strict defensive confirmation |

Do **not** treat these as four independent guesses. They form a decision ladder:

- if `long20` beats flat cleanly without worse drawdown, the long overlay is
  worth keeping;
- if `long40` materially beats `long20`, the larger overlay is justified;
- if flat beats both longs, final HYD should be flat-only;
- if strict flat is close to loose flat, prefer strict confirmation for final
  1M robustness.

## Local HYD-only replay sanity

The abort gate passes on the official/day-3 prefix, so the local official proxy
preserves the hardflat/hardlong family:

| candidate | official proxy HYD | day3 1M HYD | hist all 1M HYD |
|---|---:|---:|---:|
| abortgate15 long40 | 7,370 | 56,320 | 167,693 |
| abortgate15 long20 | 7,026 | 55,976 | 167,349 |
| abortgate15 flat | 6,626 | 55,576 | 166,949 |
| abortgate18 flat | 6,626 | 55,576 | 166,949 |
| hardlong80 fixed60k | 7,867 | 56,817 | 168,190 |
| slopegate15 cap40 long40 | 6,324 | 55,274 | 166,647 |

## Rolling false-trigger stress

Approximate rolling high-trigger stress for the abort-gate family:

| family | rolling overlay mean | worst window | p10 | positive rate | official-like overlay |
|---|---:|---:|---:|---:|---:|
| abortgate15 flat | -2,479 | -16,800 | -8,200 | 23.1% | +7,000 |
| abortgate15 long20 | -2,615 | -16,800 | -8,400 | 23.1% | +7,200 |
| abortgate15 long40 | -2,750 | -16,800 | -8,400 | 22.2% | +7,400 |
| abortgate18 flat | -2,419 | -16,800 | -8,200 | 24.8% | +7,000 |
| hardlong40 fixed60k | -4,271 | -19,840 | n/a | 25.6% | +7,760 |
| hardlong80 fixed60k | -5,503 | -23,680 | n/a | 23.1% | +8,520 |

This is the intended trade:

- abortgate gives up some theoretical official-path upside versus long80;
- it keeps most of hardflat/hardlong40's official-path alpha;
- it has materially better false-trigger stress than blind hardlong.

## Realistic decision after upload

Use actual official HYD attribution, not total score alone:

1. Compare `hyd_pnl`, `hyd_touch_liquidation_pnl`, and `hyd_max_drawdown`.
2. If `long20` adds several hundred HYD over flat with no worse drawdown, it is
   likely the best final HYD compromise.
3. If `long40` adds only a small amount over `long20`, reject `long40`; the
   extra path bet is not worth it.
4. If flat is close to long20, final should be flat/strict-flat.
5. Keep `hardlong80` only as the max-100k reference, not as the default final
   1M strategy.

## Commands

Regenerate files:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.export_hyd_abortgate_final_uploads
```

Re-run local HYD replay:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.evaluate_hydrogel_probe_submissions
```
