# R4 Submissions — Pinned & Archive

Round 4 closeout. Pinned files at top level are the references kept for R5
reuse and audit. All other R4 submissions are in `_archive/` (72 files).
The 8 velvet probe variants from the late-R4 frontier sweep are kept together
in `velvet_probe_ladder/` for easy comparison against `README_UPLOAD_SELECTION.md`.

## Pinned files

| File | Why pinned |
|---|---|
| `submission_r4_final_probe_stack_hyd_abortgate18_long80_60.py` | **The actual final submission.** Live R4 score: 143,528. |
| `submission_r4_exp_stack_hydhardlong80_60k.py` | Best-known historical anchor (Kevin BT 3-day total: 895,379; official 100k: 77,974). Reference base for any R5 stack-style work. |
| `submission_r4_combo_stack_hyd80_marks_v1.py` | Reference for the Mark 38 HYD taker-buy fade overlay. Useful template if R5 has counterparty IDs. |
| `submission_r4_exp_flat995_vev5500_sell7_validated.py` | Validated R3-style baseline with R4 TTE fix. Acts as the conservative floor. |
| `submission_r4_safer_hydflat995.py` | Hardflat HYD wrapper, smallest terminal residual. Useful as a defensive fallback pattern. |

## What's in `_archive/`

72 R4 submissions covering:
- Mark research probes (Mark 38, Mark 22, Mark 55, Mark 67 variants)
- HYD wrapper variants (cap40/80/120, hardflat/long, slope-gated, abortgate)
- Voucher schedule variants (sell7, sellonly, disabled, regime-gated)
- Combo / stack variants (target=80/100/120 × Mark mechanisms)
- Calibration probes (flat95k, hardlong40_bid10052_70k, etc.)

Open the file directly for code-level lookups; the file names are descriptive.

## R4 outcome summary

- **Submitted: `final_probe_stack_hyd_abortgate18_long80_60`**
- **Live PnL: 143,528** (Day 4 unseen, 1M ticks, all positions flat at close)
- Top scorers: 200k+. Gap analysis in `docs/round_4/R4_LIVE_POSTMORTEM.md`.

Per-product attribution on Live D4:

| Product | PnL |
|---|---:|
| HYDROGEL_PACK | 56,870 |
| VELVETFRUIT_EXTRACT | 9,699 |
| VEV_4000-5200 (core) | 80,981 |
| VEV_5300/5400 (wings) | -4,022 |

## Key lessons (full doc: `docs/round_5/ROUND_4_LESSONS_FOR_ROUND_5.md`)

1. Regime adapters > Mark identity. Mark research yielded ~$600 of incremental alpha on live.
2. Schedule-based strategies have fat left tails on regime-shift days — drawdown protection needed.
3. Static short OTM basket alongside Mark 22 was a missed ~$15-20k.
4. HYD swing trader dedicated module would have captured ~$20-40k.
5. Cross-strike correlation gate as bearish signal — completely missed.

## Tooling references

For R5, the reusable pieces from R4 work:
- `src/scripts/validate_submission.py` — validator-clean check
- `src/backtest/replay_engine.py` + `src/backtest/simulator.py` — local replay
- `external/kevin-bt/` (gitignored) — community backtester for cross-validation
- `src/scripts/round_4/audit_*.py` — audit scripts (counterparty, regime, basket structure)
