# IMC Round-1 official result — promoted

## Identity
- Submission file: `outputs/submissions/round_1/trader_round1_promoted.py`
- Bundle banner commit: `b1fc5bf` (matches uploaded file's banner)
- Uploaded file: `outputs/round_1/official_results/Promoted/115254.py`
- Submission ID: pulled from the log (`tradeHistory` + `activitiesLog` present)
- Round / day: Round 1, day 0 (official), 1 000 snapshots

## Headline metrics
- **Total official PnL: +2 518.11** (+10.6 % over baseline)
- Per-product PnL:
  - ASH_COATED_OSMIUM: **+720.91** (−13.4 % vs baseline — the promoted ewma_mid ASH underperforms)
  - INTARIAN_PEPPER_ROOT: **+1 797.20** (+24.5 % vs baseline)
- Trade count (ours): 121 total — 80 ASH, 41 PEPPER (lower than baseline on both)
- Final positions: ASH −21, PEPPER −2, XIRECS 236 775
- Cumulative-PnL curve: similar back-loading profile; ≈80 % of PnL accrues after step 500

## Stability / sanity flags
- Promoted ASH final position (−21) is larger in absolute terms than baseline's (−8) — still well below the 50-unit limit but the directional bias is noticeable.
- No submission errors / platform warnings observed.
- No obvious simulator instability.

## Free-text observations
- **Promoted ASH (`ewma_mid`, `taker_edge=0.25`) underperforms baseline ASH (`wall_mid`, `taker_edge=1.0`) on the official day**. Fewer trades (80 vs 89) at a marginally higher per-trade spread (+3.96 vs +3.73) does not compensate. See `docs/round_1/official_results_analysis.md` for the flagged recommendation.
- Promoted PEPPER (`linear_drift h=32`, `taker_edge=2.0`, `flatten=0.7`) works as designed: +19.61 avg spread captured (the highest of any variant) for +1 797 PnL. Fewer trades (41 vs baseline's 48, alt's 45) but each trade is a cleaner signal.
- Overall: Promoted package beats baseline as intended; ASH leg is the weakness.
