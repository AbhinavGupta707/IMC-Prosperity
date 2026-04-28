# Round 4 Mark-Conditioned Schedule Audit

Date: 2026-04-27

## Question

Earlier Mark research tested standalone follow/fade trades and found that the
edge was usually smaller than crossing cost. This audit asks a narrower and more
strategy-relevant question:

Can recent Mark flow identify which *existing* R3/R4 schedule signals should be
sized, delayed, skipped, or recycled?

This matters because the current strategy saturates limits early. Extra alpha is
unlikely to come from simply adding more schedule fills; it has to come from
using capacity better.

## Artifacts

Script:

`/Users/abhinavgupta/Desktop/IMC/src/scripts/round_4/audit_mark_conditioned_schedule.py`

Outputs:

`/Users/abhinavgupta/Desktop/IMC/outputs/round_4/mark_conditioned/schedule_signal_edges.csv`

`/Users/abhinavgupta/Desktop/IMC/outputs/round_4/mark_conditioned/conditioned_schedule_edges.csv`

`/Users/abhinavgupta/Desktop/IMC/outputs/round_4/mark_conditioned/loo_feature_gates.csv`

Run:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_4.audit_mark_conditioned_schedule \
  --data-dir /tmp/imc-r4-counterparty-audit/data/raw/round_4 \
  --out-dir /Users/abhinavgupta/Desktop/IMC/outputs/round_4/mark_conditioned
```

## Method

For each historical R4 day, the script builds every top-of-book schedule signal:

- buy signal when `best_ask <= schedule_buy`
- sell signal when `best_bid >= schedule_sell`

It then computes spread-aware forward edge:

- buy edge = future bid - entry ask
- sell edge = entry bid - future ask

Horizons: `1k`, `5k`, `10k`, `30k`, `100k` ticks.

Recent Mark features are attached over `1k`, `5k`, `10k`, and `30k` trailing
windows. The audit deliberately restricts feature pairings:

- VELVET signals: VELVET Mark flow
- Voucher signals: VELVET Mark flow plus Mark 22 voucher/OTM flow
- HYDROGEL signals: HYDROGEL Mark flow

The most important output is the leave-one-day gate search. For each candidate
feature, train on two days, choose whether active or inactive feature state has
better schedule edge, then test that choice on the held-out day.

## Headline Counts

- Schedule-trigger rows: `133,285`
- Conditional summary rows: `3,632`
- Leave-one-day gate rows: `2,431`

The strategy surface is dense. This supports the capacity-saturation diagnosis:
many schedule opportunities exist, but the current trader often spends the
position limit early and then plateaus.

## Strong Historical Gates

The cleanest leave-one-day candidates are:

| Product | Side | Horizon | Feature | Window | Chosen state | Mean test uplift |
| --- | --- | ---: | --- | ---: | --- | ---: |
| VELVET | buy | 100k | Mark 67 buys VELVET | 30k | inactive | +9.67 |
| VELVET | buy | 30k | Mark 14 buys VELVET | 30k | inactive | +7.33 |
| VEV_4500 | sell | 30k | Mark 22 sells VELVET | 10k | active | +6.32 |
| VELVET | sell | 30k | Mark 22 sells VELVET | 10k | active | +6.23 |
| VEV_4000 | sell | 30k | Mark 22 sells VELVET | 10k | active | +6.17 |
| VEV_5000 | sell | 10k | Mark 22 sells VELVET | 10k | active | +4.95 |

Important interpretation:

- `Mark 22` selling VELVET is the most coherent active sell-side conditioner.
- `Mark 67` buying VELVET is *not* a simple follow signal inside the schedule.
  The gate chooses inactive for VELVET/VEV_5000 buy signals, suggesting Mark 67
  often appears after a move or in a worse schedule-buy state.
- The signal is more credible as a short-horizon/recycling input than as a
  terminal-position input.

## OTM Voucher Buy Conditioning

Historical results also show Mark 22 voucher-selling flow conditioning long
horizon buy signals:

| Product | Side | Horizon | Feature | Window | Uplift vs inactive |
| --- | --- | ---: | --- | ---: | ---: |
| VEV_5200 | buy | 100k | Mark 22 sells VEV_5300 | 30k | +5.15 |
| VEV_5300 | buy | 100k | Mark 22 sells VEV_5300 | 30k | +2.73 |
| VEV_5200 | buy | 100k | Mark 22 sells VEV_5500 | 10k | +2.58 |
| VEV_5200 | buy | 100k | Mark 22 OTM sell basket | 10k | +2.44 |

This is plausible: informed/structural OTM selling may identify moments when
ATM/OTM voucher schedule buys are less toxic or mean-reverting. But the official
100k simulator slice cannot validate 100k forward edge directly, so this should
not be uploaded as a large static gate without more calibration.

## Official 100k Calibration

Using `r4 Sim Results/sellonly/497595.log`, non-SUBMISSION Mark flow was sparse:

- Mark 22 sold VELVET only 4 times, from tick `31,400` to `85,000`.
- Mark 22 sold OTM vouchers mostly from tick `32,900` onward.
- Many Mark features become active in the same small window around
  `33,500-37,300`, so the official slice cannot cleanly distinguish Mark ID
  from market regime.

Selected official conditioned schedule edges:

| Product | Side | Horizon | Feature | Active rows | Active edge | Inactive edge |
| --- | --- | ---: | --- | ---: | ---: | ---: |
| VEV_5000 | sell | 10k | Mark 22 sells VELVET, 10k window | 29 | +15.38 | +3.72 |
| VEV_5100 | sell | 10k | Mark 22/OTM sell window | 14 | +15.71 | +4.94 |
| VEV_5000 | sell | 30k | same active window | 29 | +10.14 | +22.76 |
| VEV_4000 | sell | 30k | same active window | 6 | -2.67 | +10.38 |

This mixed official result is the key calibration warning. The Mark-conditioned
sell-side state appears useful at short horizons in the official 100k slice, but
can be worse at 30k and is not uniformly transferable across strikes.

## Research Conclusion

Marks are not the primary alpha engine yet.

The best current interpretation is:

1. Mark flow can identify short-horizon schedule quality, especially when
   `Mark 22` sells VELVET and the schedule is also showing sell signals in
   VELVET/VEV_5000/VEV_5100.
2. Mark flow should not be used as a blunt order filter across all strikes.
   The official 100k slice shows strike/horizon disagreement.
3. The most promising implementation class is dynamic inventory recycling or
   quote skew around existing schedule signals, not standalone crossing and not
   a permanent post-Mark regime switch.

## Next Upload-Calibrated Mark Experiments

Use official simulator uploads as calibration experiments:

1. `MARK22_VELVET_SELL_MICRO`
   - Only trade VEV_5000/VEV_5100 sell-side when Mark 22 recently sold VELVET
     or OTM vouchers.
   - Keep size small and horizon/recycling short.
   - Purpose: measure whether the official short-horizon sell edge survives
     outside the observed 100k slice.

2. `MARK22_RECYCLER_ON_BASE`
   - Start from the current `sell7` or disabled/sellonly base.
   - When Mark 22 sell-flow is active and VEV_5000/VEV_5100 bid is above schedule
     sell threshold, allow small sell/reduce trades even if the base book is
     long from earlier schedule buys.
   - Do not apply to VEV_4000/4500 until official evidence improves.

3. Negative control
   - Trigger the same VEV_5000/5100 recycler on a non-Mark condition with similar
     frequency, such as any VELVET trade or a random-looking Mark 55 window.
   - If this performs similarly, the alpha is regime/timing rather than Mark ID.

4. Long-horizon OTM buy probe
   - Separately test Mark 22 voucher-sell-conditioned VEV_5200/5300 buys.
   - This needs official upload calibration because the historical edge is mostly
     at 100k horizons and the 100k simulator logs do not provide enough forward
     runway.

## Capacity Reserve Probe

After official calibration, one practical concern was that Mark 22 sell-flow in
the official 100k slice appeared after VEV_5000/VEV_5100 were already short at
limit. I tested a local wrapper that reserves short capacity in VEV_5000 and
VEV_5100 until Mark 22 sell-flow becomes active.

Script:

`/Users/abhinavgupta/Desktop/IMC/src/scripts/round_4/test_mark_capacity_reserve.py`

Output:

`/Users/abhinavgupta/Desktop/IMC/outputs/round_4/mark_conditioned/reserve_probe_summary.csv`

Quick-grid result versus `sell7` base:

| Variant | Total PnL | Delta | Trimmed qty |
| --- | ---: | ---: | ---: |
| base | 886,964 | 0 | 0 |
| floor -250, 10k window | 886,964 | 0 | 0 |
| floor -200, 10k window | 886,964 | 0 | 6 |
| floor -200 until 50k, 10k window | 886,964 | 0 | 0 |
| floor -100, 10k window | 886,955 | -9 | 106 |

Interpretation:

- On historical replay, Mark 22 sell-flow is frequent/early enough that reserve
  constraints almost never bind.
- Therefore a Mark22 capacity reserve is not a meaningful local upgrade.
- The official slice may have different timing, but this makes a reserve upload
  a calibration probe, not a recommended candidate.
