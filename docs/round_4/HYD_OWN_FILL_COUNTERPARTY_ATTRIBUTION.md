# Round 4 HYDROGEL Own-Fill Counterparty Attribution

Date: 2026-04-27

## Question

Can the new Round 4 `own_trades` buyer/seller IDs improve HYDROGEL inventory
management after we get filled?

This is deliberately separate from the active HYDROGEL isolation strategy. It
does not modify any trader. It asks whether a wrapper rule is justified.

## Artifacts

Script:

`/Users/abhinavgupta/Desktop/IMC/src/scripts/round_4/audit_hyd_own_fill_counterparty.py`

Outputs:

`/Users/abhinavgupta/Desktop/IMC/outputs/round_4/mark_policy/hyd_own_fill_counterparty/`

Key files:

- `hyd_candidate_summary.csv`
- `hyd_own_fill_records.csv`
- `hyd_own_fill_unique_events.csv`
- `hyd_counterparty_summary_runweighted.csv`
- `hyd_counterparty_summary_unique.csv`
- `hyd_counterparty_summary_by_candidate.csv`
- `hyd_counterparty_time_bucket_summary.csv`

## Official Runs Parsed

The script loaded all current official R4 logs/zips under:

`/Users/abhinavgupta/Desktop/IMC/r4 Sim Results/`

Best HYD-containing official runs currently present:

| Candidate | Total PnL | HYD PnL | HYD final pos | HYD last fill |
| --- | ---: | ---: | ---: | ---: |
| `hardlong4060k` | 72,057.90 | 7,151 | -200 | 61,900 |
| `hardflat60k` | 71,340.90 | 6,434 | -200 | 61,600 |
| `cap4060k` | 70,048.90 | 5,142 | -200 | 61,300 |
| `cap8060k` | 69,200.90 | 4,294 | -200 | 61,000 |
| `validated` | 68,655.81 | 1,680 | -200 | 23,600 |
| `flat95k` | -4,339.00 | -4,339 | 0 | 96,600 |

This already says the main HYD official gain is not just counterparty identity.
It is the later sell/hold regime around 60k.

## Unique Fill Summary

Deduplicated by `(timestamp, side, counterparty, price)`:

| Side | Counterparty | Rows | Qty | 1k markout | 5k markout | 30k markout | End markout |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| sell | Mark14 | 54 | 673 | -7.14 | -5.21 | -6.58 | +19.11 |
| buy | Mark14 | 25 | 271 | -4.30 | -8.86 | +10.87 | -26.20 |
| sell | Mark38 | 8 | 37 | -9.22 | -1.24 | -18.92 | +6.24 |
| sell | Mark22 | 2 | 14 | +0.07 | +15.00 | +11.79 | +39.00 |

Interpretation:

- HYD sells generally look bad over the first 1k ticks but good to terminal.
- Mark14 sells have the largest capacity and best terminal contribution.
- Mark38 sells are not superior to Mark14 in our own-fill sample.
- Mark22 sell fills look excellent but are only 14 qty, all in the late 60k
  regime, so this is not enough to create a Mark22-specific rule.
- HYD buys against Mark14 are bad to terminal. They are flatten/risk-control
  trades, not alpha trades.

## Timing Confound

Counterparty is strongly confounded with timestamp and strategy state:

| Bucket | Side | Counterparty | Qty | 1k markout | 5k markout | End markout |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| early 0-30k | sell | Mark14 | 253 | -8.64 | -0.79 | +6.73 |
| early 0-30k | sell | Mark38 | 25 | -10.52 | -5.20 | -0.36 |
| mid 30-58k | sell | Mark14 | 200 | -5.87 | -19.34 | +20.10 |
| late 58-70k | sell | Mark14 | 220 | -6.57 | +2.55 | +32.45 |
| late 58-70k | sell | Mark22 | 14 | +0.07 | +15.00 | +39.00 |
| late 58-70k | sell | Mark38 | 6 | -4.00 | +8.00 | +34.00 |
| terminal 70k+ | buy | Mark14 | 200 | -6.12 | n/a | -29.85 |

This is the main caution. The apparent counterparty edge is mostly the late
sell regime. A broad "if Mark14 then hold" rule would overfit.

## Practical Conclusions

1. We should not add a pure HYD post-fill counterparty wrapper yet.
   - Counterparty alone is not stable enough.
   - Timestamp/regime dominates.

2. Do not flatten HYD just because short-term markouts after sells are negative.
   - HYD sells often look bad over 1k-5k but good to terminal.
   - A short stop-loss after fills would likely destroy the official HYD edge.

3. Mark38 is not the magic target for our own fills.
   - Public Mark38 taker flow has passive-maker value in theory.
   - But our actual Mark38 HYD fills are low quantity and weaker than late
     Mark14/Mark22 sells in the official uploads.

4. HYD buys against Mark14 should be treated as risk-control only.
   - They are consistently poor terminal alpha in the official 100k path.
   - If the active HYD strategy buys Mark14 to flatten, it should have a clear
     risk reason, not an alpha reason.

5. The high-value research remains regime/timing/inventory design:
   - why the 60k sell regime works;
   - how much short exposure to hold;
   - whether final 1m behavior requires a different terminal risk rule.

## Possible Wrapper Rule If We Test One

Only after HYD isolation chooses a base:

- If a HYD buy fill occurs against Mark14 and we are not intentionally terminal
  flattening, allow the strategy to re-short sooner.
- Do **not** force quick flatten after HYD sell fills against Mark14/Mark38,
  because the official path rewards holding the short.

This should be tested as a narrow post-fill wrapper, not blended into the active
HYD search yet.
