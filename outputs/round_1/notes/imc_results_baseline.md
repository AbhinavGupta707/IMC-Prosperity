# IMC Round-1 official result — baseline

## Identity
- Submission file: `outputs/submissions/round_1/trader_round1_baseline.py`
- Bundle banner commit: `b1fc5bf` (matches uploaded file's banner)
- Uploaded file: `outputs/round_1/official_results/Baseline/115117.py` (byte-identical to export modulo trailing newline)
- Submission ID: `8b7d0f48-b5c4-4283-af72-6b264f65ae07`
- Round / day: Round 1, day 0 (official), 1 000 snapshots

## Headline metrics
- **Total official PnL: +2 276.15**
- Per-product PnL (from `activitiesLog`):
  - ASH_COATED_OSMIUM: **+832.25**
  - INTARIAN_PEPPER_ROOT: **+1 443.90**
- Trade count (ours): 137 total — 89 ASH, 48 PEPPER
- Final positions: ASH −8, PEPPER +1, XIRECS 70 198
- Cumulative-PnL curve shape: back-loaded; ≈95 % of PnL accrues in the last 50 % of steps

## Stability / sanity flags
- No submission errors / platform warnings observed.
- No obvious divergence in book behaviour: ASH mid range 9986–10011 (mean 9999.9), PEPPER slope ≈ +0.101/timestamp (matches local Phase-1 drift).
- Single-run data point — repeatability untested.

## Free-text observations
- Baseline ASH (wall_mid, t=1.0) captured +3.73 per round-trip on 89 trades — slightly lower per-trade edge than alt but more fills than promoted.
- Baseline PEPPER (t=1.0) captured +12.55 per round-trip, the lowest of all three variants — consistent with `taker_edge=1.0` firing on marginal signals.
- Sets the reference for Promoted (+10.6 %) and Alt (+33.6 %) comparisons.
