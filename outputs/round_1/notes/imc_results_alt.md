# IMC Round-1 official result — alt

## Identity
- Submission file: `outputs/submissions/round_1/trader_round1_alt.py`
- Bundle banner commit: `b1fc5bf` (matches uploaded file's banner)
- Uploaded file: `outputs/round_1/official_results/Alt/115380.py`
- Round / day: Round 1, day 0 (official), 1 000 snapshots

## Headline metrics
- **Total official PnL: +3 040.22** (+33.6 % over baseline, +20.7 % over promoted)
- Per-product PnL:
  - ASH_COATED_OSMIUM: **+982.81** (**best of all three**; +18.2 % over baseline, +36.3 % over promoted)
  - INTARIAN_PEPPER_ROOT: **+2 057.41** (+42.5 % over baseline, +14.5 % over promoted)
- Trade count (ours): 134 total — 89 ASH, 45 PEPPER
- Final positions: ASH −10, PEPPER +6, XIRECS 30 468
- Cumulative-PnL curve: same back-loaded pattern; strongest Q3 (+1 430) and strongest Q4 (+846) of all variants

## Stability / sanity flags
- Final positions well within limits on every product.
- No submission errors / platform warnings observed.
- Inventory worries from Phase-4/5 (C-PEP-B spending 24 % of local steps near the limit) **did not materialise** on this official run, almost certainly because the official day is 30× shorter than the local replay.

## Free-text observations
- Alt's ASH (`wall_mid`, `taker_edge=0.5`, `maker_edge=1.5`) is the top-ranked ASH config on the official data: +4.39 avg spread captured on 89 trades — the highest per-trade edge AND full trade count.
- Alt's PEPPER (`linear_drift h=32`, `skew=1.0`, `flatten=0.9`) beats Promoted's PEPPER by +260 on official vs +24 829 locally — the local leverage didn't translate 1:1, but the directional bet paid off.
- **On this single data point, Alt strictly dominates Promoted on both products.** See `docs/round_1/official_results_analysis.md` for why the flagged recommendation is "adopt Alt's ASH leg into Promoted" (not "wholesale replace Promoted").
- Inventory discipline worry from Phase-5 is *deferred, not dismissed*: longer official runs could still expose Alt's near-limit behaviour.
