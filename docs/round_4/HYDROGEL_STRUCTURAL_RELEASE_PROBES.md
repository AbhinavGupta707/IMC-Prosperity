# HYDROGEL Structural Release Probes

Date: 2026-04-27

## Purpose

The latest official HYD probes showed that `hardlong40_60k` is better than
static `flat995`, but the exact `60k` release may be path-fit. This pass tests
whether a more structural release rule can improve or de-risk the high-regime
overlay.

Script:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.evaluate_hydrogel_structural_release
```

Output:

- `outputs/round_4/hydrogel_probes/structural_release_summary.csv`

## Main Result

The structural release rules did not beat fixed `60k` on the current
official/day-3 prefix.

| candidate | official-proxy HYD | release | comment |
| --- | ---: | ---: | --- |
| `hardlong80_fixed60k` | 7,867 | 60,000 | Best local/proxy PnL, higher exposure risk. |
| `hardlong40_fixed60k` | 7,370 | 60,000 | Current best official-tested family. |
| `hardlong40_bid10048_fallback70k` | 7,370 | 60,000 | Same behavior as fixed `60k` on this path. |
| `hardlong40_bid10052_fallback70k` | 7,240 | 60,300 | Releases later; slightly worse. |
| `hardlong40_bid10048_persist3_fallback70k` | 7,330 | 60,200 | Persistence costs a little. |
| `hardlong40_turn_bid10052_drop4_fallback70k` | 7,174 | 60,400 | Turn confirmation costs a little. |
| `hardflat_fixed60k` | 6,626 | 60,000 | Cleaner lower-risk fallback. |
| `flat995` | 1,816 | n/a | Shorts too early in this high path. |

Interpretation:

- `bid >= 10048` is not a new structural edge on the official prefix. It fires
  exactly at `60k`.
- `bid >= 10052`, persistence, and turn-confirmation release after `60k`, but
  the later start does not improve fill quality enough to pay for delayed
  participation.
- The fixed `60k` rule remains best among the release policies tested, but this
  increases concern that the good result is tied to the specific path shape.

## Size Probe

The only tested improvement is size:

| candidate | official-proxy HYD | delta vs `hardlong40_60k` | full historical HYD |
| --- | ---: | ---: | ---: |
| `hardlong40_60k` | 7,370 | 0 | 167,693 |
| `hardlong80_60k` | 7,867 | +497 | 168,190 |

This is not a free lunch. `+80` doubles the rising-leg inventory exposure. It
helps on the current official/day-3 prefix because the path rises into release.
It remains more fragile if the hidden final path false-triggers and mean-reverts
before release.

## Abort Guard Warning

A naive abort guard is dangerous. The `abort_mid=10018` version aborted at
`39.2k` on the official/day-3 prefix and produced a large loss in the local
proxy. The path temporarily dipped before the later high move. That means:

- do not add a tight early breakdown abort;
- if adding an abort, it needs persistence and/or a lower threshold;
- the release/abort problem is path-regime classification, not a simple line.

## Upload Candidates Created

Two uploadable probes were added:

- `outputs/submissions/r4/submission_r4_probe_hyd_highregime_hardlong80_60k.py`
- `outputs/submissions/r4/submission_r4_probe_hyd_highregime_hardlong40_bid10052_70k.py`

Priority:

1. `hardlong80_60k`
   - Asks whether increasing the pre-release long target extracts more official
     fill PnL.
   - Higher overfit and false-trigger risk.

2. `hardlong40_bid10052_70k`
   - Mechanism control for structural release.
   - Expected to slightly underperform `hardlong40_60k` on this path unless
     official fill behavior rewards the later release more than local replay
     does.

## Current Recommendation

Do not pivot away from the current broad family. The evidence still supports:

`regime-conditioned mean-reversion / inventory timing`

But the structural-release pass did not uncover a robust replacement for fixed
`60k`. For upload learning, `hardlong80_60k` is the most informative next
alpha probe; `bid10052_70k` is a lower-priority mechanism control.
