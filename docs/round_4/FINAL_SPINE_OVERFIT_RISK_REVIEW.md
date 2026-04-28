# R4 Final Spine Overfit Risk Review

Date: 2026-04-28

## Question

Current intended spine:

```text
probe_stack VELVET/options + HYD abortgate18_long80_60
```

Does it look overfit to the official 100k simulator slice, and how should we
manage that risk for the final unseen 1M run?

## Evidence Used

- R3 public/historical research outputs and R3 final hidden 1M result.
- R4 official 100k simulator uploads under `r4 Sim Results/`.
- R4 public historical days 1/2/3 full 1M local replay.
- New audit script:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.audit_final_spine_overfit
```

Outputs:

- `outputs/round_4/final_spine_overfit_audit/full_day_summary.csv`
- `outputs/round_4/final_spine_overfit_audit/product_summary.csv`
- `outputs/round_4/final_spine_overfit_audit/bucket_summary.csv`
- `outputs/round_4/final_spine_overfit_audit/report.md`

Local replay is not the official simulator. Treat it as a distributional sanity
check, not a leaderboard estimate.

## R3 Cross-Check

R3 final hidden 1M:

| sleeve | hidden 1M PnL |
|---|---:|
| HYDROGEL | 54,597 |
| VELVET + options | 124,200 |
| total | 178,797 |

This matters because the broad R3 structure was not pure public-data overfit:
static product-level VELVET/options thresholds and HYD inventory logic survived
hidden 1M. The lesson is not "avoid static structure." The lesson is:

- broad product/geometry structure generalized;
- exact timestamp/path-oracle logic was dangerous;
- terminal flattening reduced hidden-settlement risk;
- official 100k uploads calibrated fill behavior but did not prove final 1M
  behavior.

R3 public VELVET research also showed that final-oriented static sleeves were
judged on 30 public 100k windows and 3 full 1M days, not one simulator slice.
The R4 `probe_stack` add-on currently has weaker public-window support than the
R3 static backbone had.

## R4 Official Calibration

Key official 100k results:

| candidate | total | HYD | VELVET complex | read |
|---|---:|---:|---:|---|
| validated sell7 | 68,655.81 | 1,680 | 66,975.81 | baseline |
| probe_stack | 71,997.24 | 1,680 | 70,317.24 | VELVET/options add-on |
| abortgate18_long80_60 | 74,632.81 | 7,657 | 66,975.81 | HYD add-on |
| expstack8060 | 77,974.24 | 7,657 | 70,317.24 | additive stack |

The components are almost perfectly additive:

```text
probe_stack delta      ~= +3,341
HYD abort80 delta      ~= +5,977
combined official gain ~= +9,318
```

The desired exact combo
`submission_r4_final_probe_stack_hyd_abortgate18_long80_60.py` locally matches
`expstack8060` on the public day-3 path, so if uploaded it should be expected
to land very close to `expstack8060` unless there is a packaging/logic mistake.

## R4 Public Full-Day Replay

Full public 1M replay:

| candidate | day 1 | day 2 | day 3 | mean |
|---|---:|---:|---:|---:|
| sell7 validated | 377,669 | 331,029 | 178,266 | 295,655 |
| probe_stack | 377,669 | 331,029 | 181,636 | 296,778 |
| sell7 + abort80 | 377,669 | 331,029 | 184,317 | 297,672 |
| probe_stack + abort80 | 377,669 | 331,029 | 187,687 | 298,795 |

Incremental delta versus sell7:

| candidate | day 1 | day 2 | day 3 | mean |
|---|---:|---:|---:|---:|
| probe_stack | 0 | 0 | +3,370 | +1,123 |
| abort80 | 0 | 0 | +6,051 | +2,017 |
| combo | 0 | 0 | +9,421 | +3,140 |

This is the core risk read:

- The combo does not damage public full-day replay.
- The public 1M outcome is additive and clean on day 3.
- But the incremental alpha only appears on one of three public day-starts.
- That one active public day is also the official-simulator day-3-like path.

So the candidate is not "obviously overfit broken." It is a high-regime
calibration bet with limited independent positive samples.

## Flat Region Interpretation

The official 100k curve's flat region is expected mechanically:

- the strategy front-loads most VELVET/options inventory early;
- HYD flips into its high-regime short around the 60k release;
- after that, there are few fresh trades, so PnL is mostly mark-to-market carry;
- local public full-day replay confirms the system re-engages later in the 1M
  path and flattens most VELVET/voucher exposure by the end.

The flat region is not by itself a bug. The risk is that the early official
path and terminal mark are unusually favorable, not that no trades happen from
50k to 90k.

## Overfit Verdict

Verdict:

```text
Medium overfit risk, not disqualifying.
```

What is robust enough:

- R3 hidden 1M validates the broad static VELVET/options backbone.
- R3/R4 public full-day replays do not show the current combo blowing up.
- The official/local fill calibration is close on this family.
- The final 1M version has terminal flattening behavior in local replay, unlike
  the mark-heavy official 100k ending.

What is still overfit-prone:

- The R4 official 100k price path is highly day-3-like.
- HYD `20k-30k trigger -> 60k release` is still path-specific, even with the
  abort gate.
- `probe_stack` has weak public-window support: prior audit found active
  windows are sparse and conditional win rate is low.
- The combined alpha is not observed on public days 1/2 because the gates never
  fire there.

## Practical Decision

Use `probe_stack + abortgate18_long80_60` as the max-EV current spine if the
goal is to optimize expected official/final performance while accepting a
regime bet.

Use `sell7 + abortgate18_long80_60` as the safer spine if we decide the VELVET
probe-stack add-on is too path-specific after the parallel VELVET session's
final readout.

Do not keep adding small Mark wrappers or more timestamp tweaks to reduce
overfit. They either add negligible PnL or make the path-dependence worse.

## How To Reduce Risk Further

Highest-value next checks:

1. Upload the exact combo once, if not already uploaded, as a packaging sanity
   check. It should be close to `expstack8060`.
2. Keep a two-candidate final ladder:
   - max-EV: `probe_stack + abortgate18_long80_60`;
   - safer: `sell7 + abortgate18_long80_60` or the VELVET session's best
     robustness-improved replacement.
3. Stress-test the combo with synthetic spliced paths:
   - day-3 first 100k followed by day-1/day-2 tails;
   - day-1/day-2 first 100k followed by day-3 tail;
   - adverse HYD false-trigger prefixes.
4. Do not promote new VELVET add-ons unless they beat `probe_stack` on:
   - official 100k;
   - public sliding windows;
   - negative controls;
   - final inventory/drawdown.
5. For HYD, do not move beyond long80 unless intentionally accepting higher
   variance. Long120 adds official PnL but worsens early pain and rolling-tail
   stress.

Final stance: the current combo is a defensible max-EV candidate, but not a
low-overfit theorem. The right risk control is candidate selection discipline,
not more official-slice tuning.
