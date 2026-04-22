# D8 — Fill-Model Calibration Sweep

Calibrates our backtest's `passive_allocation` parameter against a known-truth reference: R2 `Promoted` variant with 4 IMC simulator runs (mean profit **7,654**, σ 366).
**CALIBRATION RESULT: best `passive_allocation` = 0.05** (vs current default 0.3).


If best fill_rate != 0.3 (the current default), every historical sweep is biased. **No R3 tuning decision should be made until this value is calibrated.**

## Calibration sweep: R2 Promoted (wide_w113) vs 4 IMC simulator runs

- Truth: 7654 (n=4, σ=366)
- Scale factor (backtest ticks / truth ticks): 30.0

| fill_rate | sim_raw | sim_scaled | truth | abs_err | rel_err |
|---|---|---|---|---|---|
| 0.05 | 249,206 | 8,307 | 7,654 | 653 | 8.5% |
| 0.10 | 249,206 | 8,307 | 7,654 | 653 | 8.5% |
| 0.15 | 249,237 | 8,308 | 7,654 | 654 | 8.5% |
| 0.20 | 249,343 | 8,311 | 7,654 | 657 | 8.6% |
| 0.25 | 249,375 | 8,312 | 7,654 | 658 | 8.6% |
| 0.30 | 249,375 | 8,312 | 7,654 | 658 | 8.6% |
| 0.40 | 249,431 | 8,314 | 7,654 | 660 | 8.6% |
| 0.50 | 249,557 | 8,319 | 7,654 | 665 | 8.7% |

**Best fill_rate:** 0.05 (minimizes absolute error)
**Within ±5% tolerance:** none — the best we can do is 8.5% error

## Interpretation

- **If best fill_rate < 0.3:** our backtest OVER-credits passive fills. Historical winners are inflated; some may be live losers (like our wide_w113 experience).
- **If best fill_rate > 0.3:** our backtest UNDER-credits passive fills. We've been missing good configs.
- **If ±5% tolerance is never reached:** our fill model itself is the wrong shape, not just miscalibrated. May need a structural fix (conservative maker matching, bot-specific take rates, etc.).

## Next step

1. Adopt the best fill_rate as the new default in `FillModelConfig`.
2. Re-run every historical sweep with the calibrated value.
3. Re-promote based on corrected rankings.
4. Add more reference points if available (port a top-team P3 repo's published scored P&L as a second anchor).
