# Phase A — Frozen PEPPER controls

Reference numbers for every PEPPER candidate in this pass. All values
are extracted directly from the **official** IMC result files
(`outputs/round_1/official_results/*/…log` and `.json`), not from
local replay. Local-replay numbers are secondary; official is the
source of truth (`CLAUDE.md` Evidence Calibration).

Official PEPPER-attributed PnL is read from the `profit_and_loss`
column of the bundle's `activitiesLog` (last value at or before the
bucket cutoff, per product). Trade-level stats (end-of-bucket
positions, max long/short, SUBMISSION buy/sell count) are
reconstructed from `tradeHistory` by summing SUBMISSION-side
quantities. The `.log` does NOT tag trades as maker or taker, so the
maker/taker split is **not inferable from the official log alone**;
the column below is marked `n/a` and is tagged as an uncertainty.

## A1. Top-line official numbers

| Variant | Submission ID | Total PnL | ASH PnL | **PEPPER PnL** | Final PEPPER pos |
|---|---|---:|---:|---:|---:|
| baseline | 115117 | **+2 276.15** | +832.25 | +1 443.90 | +1 |
| promoted | 115254 | **+2 518.11** | +720.91 | +1 797.20 | −2 |
| alt      | 115380 | **+3 040.22** | +982.81 | +2 057.41 | +6 |
| h1       | 151053 | **+2 780.01** | +982.81 | +1 797.20 | −2 |
| f5       | 152878 | **+3 117.72** | +982.81 | +2 134.91 | +21 |
| buy-and-hold | 160658 | **+5 541.81** | +982.81 | +4 559.00 | +50 |

All six were uploaded at `position_limit = 50`. The PEPPER numbers
are what the core-long search is trying to beat; buy-and-hold is the
**directional upper-bound reference** (+4 559 PEPPER PnL at a held
+50 long is pure drift MTM minus one taker cross at t=0).

## A2. PEPPER PnL by bucket (official activitiesLog)

| Variant | 0–25k | 25k–50k | 50k–75k | 75k–end | Full day |
|---|---:|---:|---:|---:|---:|
| baseline     | **−58.00** | +115.00 | +898.00  | +488.90  | +1 443.90 |
| promoted     | +31.00     | +410.00 | +942.00  | +414.20  | +1 797.20 |
| alt          | +31.00     | +333.00 | +1 084.00 | +609.41 | +2 057.41 |
| h1           | +31.00     | +410.00 | +942.00  | +414.20  | +1 797.20 |
| f5           | +31.00     | +458.00 | +970.00  | +675.91  | +2 134.91 |
| buy-and-hold | **+814.00** | +1 250.00 | +1 250.00 | +1 245.00 | +4 559.00 |

**Key observation.** The first 25k window is where market-making
variants leak or barely participate (+31 at best for every MM
variant vs +814 for buy-and-hold). Every MM PEPPER variant sits
**roughly flat through bucket 0**, then picks up once the drift
accumulates. Baseline is the only variant that loses in bucket 0
(−58) because of its `flatten_threshold = 0.8` combined with
symmetric taker edges — it sells into the early rise.

**First 50k cumulative:**

| Variant | first 25k | first 50k |
|---|---:|---:|
| baseline     | −58   | +57    |
| promoted     | +31   | +441   |
| alt          | +31   | +364   |
| h1           | +31   | +441   |
| f5           | +31   | +489   |
| buy-and-hold | +814  | +2 064 |

Buy-and-hold has **captured 45% of its final PnL by the halfway
mark**; every MM variant has captured less than 25%. This is the
central problem the core-long + overlay family is trying to address.

## A3. PEPPER SUBMISSION trade & position statistics

Reconstructed from `tradeHistory` (SUBMISSION-side trades only; other
trades are counterparty-observed and do not move our position).

| Variant | SUBMISSION trades | Buys (qty) | Sells (qty) | Max long | Max short | End of 25k | End of 50k | End of 75k |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 48 | 27 (112) | 21 (111) | **+40** | **−17** | −8 | +21 | +26 |
| promoted | 41 | 23 (95)  | 18 (97)  | +37 | −8  | +1 | +35 | +23 |
| alt      | 45 | 26 (108) | 19 (102) | **+45** | −8  | +1 | +30 | +31 |
| h1       | 41 | 23 (95)  | 18 (97)  | +37 | −8  | +1 | +35 | +23 |
| f5       | 36 | 22 (92)  | 14 (71)  | +38 | −8  | +1 | +36 | +24 |
| buy-and-hold | 3 | 3 (50) | 0 (0) | **+50** | 0 | +50 | +50 | +50 |

**Unintended shorting.** Every MM variant went short at some point —
deepest on baseline (−17) but promoted / alt / h1 / f5 all dipped to
−8 at some point. Buy-and-hold is the only variant that never went
short, by construction.

**Near-limit behaviour** (limit = 50 for these runs; near-limit
threshold = 0.75 × 50 = 37.5):

| Variant | Max long | Time spent near limit |
|---|---:|---|
| baseline     | +40 | 1 observation near limit, 0 at limit |
| promoted     | +37 | 0 observations near-limit (peak +37, just below 37.5 on a snapshot basis) |
| alt          | +45 | some near-limit at peak (entered 37.5–45 zone) |
| h1           | +37 | 0 observations near-limit |
| f5           | +38 | 1 brief near-limit crossing |
| buy-and-hold | +50 | **at or near limit for the entire session after tick 0** |

## A4. Maker/taker split

**Not inferable from the official `.log` alone.** The `tradeHistory`
records only `buyer`/`seller`/`price`/`quantity`; it does not tag
whether SUBMISSION was passive (maker) or aggressive (taker) on each
fill. A counterparty-vs-own-price check could be used as a proxy,
but the bot's own quote history is not in the log and the backtest
simulator does not record it either at the current cadence.

Local-replay maker/taker splits from
`outputs/round_1/official_results/analysis/bucket_breakdown.csv` are
available for baseline / promoted / alt but not h1 / f5 / buyhold.
This is an **uncertainty flag**, not a candidate-selection gate.

## A5. Diagnosis, one line each

| Variant | Diagnosis |
|---|---|
| baseline     | Symmetric flatten=0.8, eager early sells into the drift → **−58 in bucket 0** and a −17 short visit. Drift still bails it out overall. |
| promoted     | `taker=2.0` widens the cross threshold enough that bucket 0 avoids the baseline loss; `flatten=0.7` caps the inventory ride at ±35 → mid-day long capped. |
| alt          | Identical to promoted on edges, but `skew=1.0 + flatten=0.9` lets it ride the drift to **+45**. Bucket-2 lift vs promoted is the payoff. |
| h1           | Promoted PEPPER + alt ASH. PEPPER leg identical to promoted → **same PEPPER PnL as promoted** (+1 797). The H1 improvement is entirely on ASH. |
| f5           | Promoted PEPPER + **asymmetric taker (buy=1.5 / sell=3.0)**. Wider sell edge cuts some mid-day trims; finishes long (+21) → late-day drift capture lifts PEPPER PnL to +2 135. Best MM PEPPER result on record. |
| buy-and-hold | Commits full +50 on tick 0, holds. **PEPPER PnL = +4 559.** This is the single-axis directional upper-bound: no spread capture, no residual harvesting, just drift MTM at full capacity. |

## A6. Frozen ASH leg for this pass

The H1 / Alt / F5 / buy-and-hold bundles share the exact same wall-
based ASH leg. Local replay of that leg scored `+982.81` on the
official day (identical across those four variants). The PEPPER
core-long search treats that leg as **byte-identical fixed input**:

```python
ASH_COATED_OSMIUM = dict(
    fair_value_method="wall_mid",
    fair_value_fallbacks=("mid", "microprice"),
    taker_edge=0.5,
    maker_edge=1.5,
    inventory_skew=4.0,
    flatten_threshold=0.7,
    history_length=48,
)
```

No ASH dimension is explored in this pass.
