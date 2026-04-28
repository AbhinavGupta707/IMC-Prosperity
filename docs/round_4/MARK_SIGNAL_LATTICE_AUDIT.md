# Round 4 Mark Signal-Lattice Audit

Date: 2026-04-27

## Bottom Line

We should not say "Mark has no value." The more accurate statement is:

- Mark identities contain real, repeated structure.
- The direct Mark wrappers uploaded so far did not monetize that structure.
- The strongest Mark effects are execution/liquidity-role effects, not clean
  directional alpha.
- We do not yet have a validated high-PnL Mark integration on the final
  VELVET/HYDROGEL stack.

This matters because a no-op upload only kills that implementation surface. It
does not kill Mark as a state variable.

## New Artifact

Script:

`/Users/abhinavgupta/Desktop/IMC/src/scripts/round_4/audit_mark_signal_lattice.py`

Outputs:

`/Users/abhinavgupta/Desktop/IMC/outputs/round_4/mark_signal_lattice/`

Main files:

- `historical_event_edges.csv`
- `historical_robust_event_edges.csv`
- `historical_same_timestamp_signatures.csv`
- `historical_sequence_lifts.csv`
- `historical_robust_sequence_lifts.csv`
- `historical_mark_state_bins.csv`
- official sell-only equivalents

The script scans all Mark/product/side/role cells, all same-timestamp program
signatures, and all Mark-to-Mark sequence lifts. It is wider than the earlier
hand-picked Mark22/Mark55 probes.

## What We Have Actually Explored

1. Full Mark role classification.
   - All seven Marks are classified by product, side, taker/maker role, clip
     size, interval rhythm, markout, spread-aware edge, and official
     replication.

2. Program/basket behavior.
   - Mark22 -> Mark01 OTM voucher baskets are real and repeated.
   - HYDROGEL is almost purely Mark14 <-> Mark38 bilateral flow.
   - VELVET has repeated Mark55 taker flow against passive Mark14.

3. Mark22 first-principles re-audit.
   - Matched-frequency control showed Mark22 OTM baskets predict near-OTM
     voucher drift better than generic voucher bursts.
   - Effect is real but small relative to current HYD/VELVET stack alpha.

4. Mark-conditioned schedule audit.
   - Mark22 flow can condition short-horizon schedule quality, especially
     sell/recycle decisions in VEV_5000/VEV_5100.
   - Official evidence was mixed and highly regime clustered.

5. Mark55/Mark67 policy hazard.
   - Mark67 VELVET buy -> Mark55 VELVET seller flow is a real sequence.
   - The official single-lot recycler only gained about +15 on 100k, so the
     naive implementation is too small.

6. Direct official Mark integrations.
   - The five sell7/HYD Mark wrappers were byte-for-byte identical in executed
     trades and PnL. They were no-ops because the base strategy gave them no
     action surface.

## New Signal-Lattice Findings

### Robust Taker Toxicity

The strongest cross-day event edges are not "follow this Mark." They are
"this Mark is a toxic taker; being the passive counterparty would be valuable."

5k passive-maker edge estimates:

| Mark | Product | Side Mark Takes | Rows | Passive-maker edge |
| --- | --- | --- | ---: | ---: |
| Mark38 | VEV_4000 | buy | 209 | +20.77 |
| Mark38 | VEV_4000 | sell | 233 | +20.70 |
| Mark38 | HYDROGEL | buy | 515 | +16.85 |
| Mark38 | HYDROGEL | sell | 507 | +16.14 |
| Mark55 | VELVET | buy | 598 | +4.59 |
| Mark55 | VELVET | sell | 600 | +4.56 |

Interpretation: Discord participants may be making PnL from Mark by acting as
passive liquidity against predictable taker flow. Our current uploaded wrappers
mostly did not do that.

### Program Signatures

The most repeated same-timestamp signatures are:

- Mark22 sells OTM voucher baskets to Mark01.
- Mark38 trades HYDROGEL with Mark14.
- Mark55 trades VELVET with Mark14.

These are structural participant pairings, not random IDs.

### New Sequence Candidate

The broader sequence scan surfaced a Mark14/Mark22 `VEV_5200` loop:

| Trigger | Target | Horizon | Rows | Hit rate | Baseline | Lift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Mark14 buys VEV_5200 | Mark22 sells VEV_5200 | 30k | 33 | 60.6% | 29.4% | 2.06 |
| Mark14 buys VEV_5200 | Mark22 sells VEV_5200 | 10k | 33 | 33.3% | 13.1% | 2.55 |
| Mark22 sells VEV_5200 | Mark14 buys VEV_5200 | 30k | 46 | 39.1% | 22.5% | 1.74 |

This is real enough to investigate. It is not yet proven to be high-value:
sample size is small, and it may simply be another face of the Mark22 OTM
basket program.

## Why The Uploaded Sell7 Mark Wrappers Failed

They did not disprove Mark alpha.

They failed because:

- `mark55_exec` only improves VELVET buy/cover orders, but the sell7/HYD base
  had no VELVET buy fills on the official path.
- `mark22_core` saw Mark22 activity, but the required VEV_5000/VEV_5100
  bid/position conditions never aligned.
- The combo inherited both problems.

So the correct conclusion is "these wrappers were inert on this base," not
"Mark is useless."

## What Is Still Not Exhausted

1. Mark-aware passive quoting against Mark55/Mark38 taker flow.
2. Mark integration on the actual current stack/final VELVET base.
3. HYDROGEL Mark38/Mark14 integration inside the final HYD architecture.
4. Mark22/VEV_5200 sequence probe with a matched time-control.
5. Mark x option-Greek x regime conditioning, especially for final VELVET.
6. Multi-event states, e.g. Mark22 basket + Mark55 VELVET flow + current
   VELVET regime, rather than one Mark flag at a time.

## Recommended Next Work

1. Do not spend more uploads on the sell7 Mark family; those are killed.
2. Upload/test only one Mark wrapper on the stack/final-VELVET base first:
   Mark55 passive/execution integration, because that base actually has VELVET
   buy/cover activity.
3. Send the Mark38/HYDROGEL passive-maker evidence to the HYD session; that is
   the largest Mark edge by raw magnitude.
4. Build a tiny Mark22/VEV_5200 paired treatment/control probe if upload budget
   remains unlimited. Treat it as discovery, not a final candidate.

