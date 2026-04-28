# HYDROGEL Probe Implementation

Date: 2026-04-27

This note records the upload-calibration probes created after the HYDROGEL
isolation research.

## Probe Files

`outputs/submissions/r4/submission_r4_probe_hydonly_flat95k.py`

- HYDROGEL-only.
- Forces HYDROGEL flat-and-idle from `ts >= 95_000`.
- Use only as an official 100k calibration upload.
- Question answered: how much official HYD PnL remains when terminal exposure
  is removed before the end?

`outputs/submissions/r4/submission_r4_probe_hyd_width28_flat995.py`

- Full strategy.
- Changes HYDROGEL final take width from `32` to `28`.
- Keeps the current `flat995` terminal wrapper.
- Question answered: is current HYD width too conservative under official fill
  behavior?

`outputs/submissions/r4/submission_r4_probe_hyd_width28_flat990.py`

- Full strategy.
- Changes HYDROGEL final take width from `32` to `28`.
- Moves HYDROGEL flatten to `990_000`.
- Lower-priority sensitivity check; local HYD-only replay does not justify it
  as a recommended candidate.

`outputs/submissions/r4/submission_r4_probe_hyd_highregime_noshort_60k.py`

- Full strategy.
- If HYD midpoint is at least `10020` during the `20k-30k` discovery window,
  suppress HYDROGEL shorts until `60k`.
- Keeps the current `flat995` terminal wrapper.
- Question answered: can we improve the official high-regime slice by delaying
  early static-anchor shorts rather than narrowing width?

`outputs/submissions/r4/submission_r4_probe_hyd_highregime_cap40_60k.py`

- Full strategy.
- Same high-regime trigger, but allows up to `-40` short inventory until `60k`.
- Safer mechanism check versus the no-short version.

`outputs/submissions/r4/submission_r4_probe_hyd_highregime_cap80_60k.py`

- Full strategy.
- Same high-regime trigger, but allows up to `-80` short inventory until `60k`.
- Lower-upside cap sensitivity.

`outputs/submissions/r4/submission_r4_probe_hyd_highregime_noshort_50k.py`

- Full strategy.
- Same high-regime trigger, suppresses shorts only until `50k`.
- Early-release control.

## Local Replay Harness

Script:

`src/scripts/round_4/evaluate_hydrogel_probe_submissions.py`

Run:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.evaluate_hydrogel_probe_submissions
```

Output:

`outputs/round_4/hydrogel_probes/probe_local_summary.csv`

The harness imports each standalone submission, filters output to
`HYDROGEL_PACK`, and replays:

- three historical 1M days;
- first 100k of each historical day;
- the official HYD-only 100k log path with non-SUBMISSION trades.

The official-log replay is approximate. It is useful as a sanity check, not as
a substitute for official upload calibration.

## Key Replay Results

| candidate | hist 3x1M HYD PnL | official-log replay HYD PnL | final exposure in official-log replay |
| --- | ---: | ---: | ---: |
| baseline HYD-only | 165,728 | 1,816 | -200 |
| baseline `flat995` | 162,139 | 1,816 | -200 |
| HYD-only flat95k | 19,171 | -4,153 | 0 |
| width28 flat995 | 162,922 | 942 | -200 |
| width28 flat990 | 154,333 | 942 | -200 |
| highregime cap40 60k | 165,864 | 5,541 | -200 |
| highregime cap80 60k | 164,925 | 4,602 | -200 |
| highregime no-short 60k | 166,936 | 6,613 | -200 |
| highregime no-short 50k | 163,830 | 3,507 | -200 |

Interpretation:

- `HYD-only flat95k` is doing its job: it removes terminal exposure. The
  official-log proxy becomes negative, which strengthens the hypothesis that
  the current official HYD score is terminal-exposure sensitive. Uploading it
  would calibrate this directly.
- `width28 flat995` is a small local improvement in HYD-only replay
  (`+783` versus `flat995`) but looks worse on the official-log proxy. Treat it
  as a probe, not a promoted candidate.
- `width28 flat990` underperforms locally. Do not upload it before the 995k
  width probe unless the goal is explicitly to isolate flatten timing.
- The high-regime family is structurally different and much more informative:
  it delays early shorts only after a high-path observation. On the
  official-log proxy it improves cash while keeping the same final `-200`
  terminal exposure. The best tested version is no-short until `60k`.

Additional timing grid:

`src/scripts/round_4/evaluate_hydrogel_highregime_grid.py`

Output:

`outputs/round_4/hydrogel_probes/highregime_grid_summary.csv`

The grid shows that `60k` is the local release sweet spot in the official-like
path: no-short until `60k` reaches `6,613` HYD proxy PnL, while `50k`, `55k`,
`65k`, and `70k` reach `3,507`, `3,862`, `4,452`, and `3,210` respectively.

## Upload Order

Already answered:

1. `submission_r4_probe_hydonly_flat95k.py`
2. `submission_r4_probe_hyd_width28_flat995.py`

Next recommended HYD upload:

1. `submission_r4_probe_hyd_highregime_noshort_60k.py`
2. `submission_r4_probe_hyd_highregime_cap40_60k.py`, if a less aggressive
   mechanism check is preferred after no-short.

Hold `submission_r4_probe_hyd_width28_flat990.py` unless flatten timing becomes
the active question again.

## Validation Notes

All probe files pass Python compilation.

The repo's `validate_submission.py` is not currently usable for these R4
hand-wrapped bundles because it requires exactly one top-level `class Trader`,
while the existing R4 submission artifacts use successive `Trader` wrapper
definitions. Runtime import and replay smoke checks passed through the local
probe harness.
