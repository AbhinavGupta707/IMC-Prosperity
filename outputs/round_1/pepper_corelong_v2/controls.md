# Phase A — Frozen PEPPER controls (v2)

Reference numbers for every PEPPER candidate in the v2 pass. Official
values are read directly from the IMC result files
(`outputs/round_1/official_results/*/…log` and `.json`), not from local
replay — per `CLAUDE.md` Evidence Calibration, official is the source
of truth and local is a secondary ranking signal.

**v2 delta vs v1 controls:** identical numbers for the four public
controls (they are the same official runs), but this pass adds a new
in-family anchor control — `C_corelong_v1_base50` — which is the v1
recommendation re-run in the v2 runner so v2 candidates can be
compared against v1's best directly, not just against the shipped
references. No new public (uploaded) controls were added.

## A1. Top-line official numbers

| Variant | Submission ID | Total PnL | ASH PnL | **PEPPER PnL** | Final PEPPER pos |
|---|---|---:|---:|---:|---:|
| baseline       | 115117 | +2 276.15 | +832.25 | +1 443.90 | +1 |
| promoted       | 115254 | +2 518.11 | +720.91 | +1 797.20 | −2 |
| alt            | 115380 | +3 040.22 | +982.81 | +2 057.41 | +6 |
| h1             | 151053 | +2 780.01 | +982.81 | +1 797.20 | −2 |
| **f5** (best MM ref) | 152878 | **+3 117.72** | +982.81 | **+2 134.91** | +21 |
| buy-and-hold (directional ref) | 160658 | **+5 541.81** | +982.81 | **+4 559.00** | +50 |

All six were uploaded at `position_limit = 50`. The PEPPER numbers are
what v2 is trying to beat; buy-and-hold is the **directional upper-
bound reference** (+4 559 PEPPER PnL = pure drift MTM minus one taker
cross at t=0).

Current live shipped best is **F5 (+2 134.91 PEPPER, +3 117.72 total)**.

## A2. PEPPER PnL by bucket (official activitiesLog)

| Variant | 0–25k | 25k–50k | 50k–75k | 75k–end | Full day |
|---|---:|---:|---:|---:|---:|
| baseline     | **−58.00** | +115.00 | +898.00  | +488.90  | +1 443.90 |
| promoted     | +31.00     | +410.00 | +942.00  | +414.20  | +1 797.20 |
| alt          | +31.00     | +333.00 | +1 084.00 | +609.41 | +2 057.41 |
| h1           | +31.00     | +410.00 | +942.00  | +414.20  | +1 797.20 |
| f5           | +31.00     | +458.00 | +970.00  | +675.91  | +2 134.91 |
| buy-and-hold | **+814.00** | +1 250.00 | +1 250.00 | +1 245.00 | +4 559.00 |

Cumulative through the first 25k / 50k:

| Variant | first 25k | first 50k |
|---|---:|---:|
| baseline     | −58   | +57    |
| promoted     | +31   | +441   |
| alt          | +31   | +364   |
| h1           | +31   | +441   |
| f5           | +31   | +489   |
| **buy-and-hold** | **+814**  | **+2 064** |

**This is the v2 thesis in one table.** Every MM PEPPER variant
captures < +500 by the halfway mark; buy-and-hold captures +2 064 —
~45% of its full-day PnL. The gap between F5 (+489 by 50k) and buy-
and-hold (+2 064 by 50k) is **+1 575 PEPPER PnL sitting in the first
half of the day that no MM variant currently harvests.**

That is what v1 flagged as the "unsolved early-day gap." V2 Layer 1
(opening acquisition) is the lever designed to close it without
adopting the buy-and-hold failure mode (held +50 at the limit for the
entire session).

## A3. PEPPER SUBMISSION trade & position statistics

Reconstructed from `tradeHistory` (SUBMISSION-side trades only).

| Variant | Trades | Buys (qty) | Sells (qty) | Max long | Max short | End of 25k | End of 50k | End of 75k |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 48 | 27 (112) | 21 (111) | +40 | **−17** | −8 | +21 | +26 |
| promoted | 41 | 23 (95)  | 18 (97)  | +37 | −8  | +1 | +35 | +23 |
| alt      | 45 | 26 (108) | 19 (102) | **+45** | −8  | +1 | +30 | +31 |
| h1       | 41 | 23 (95)  | 18 (97)  | +37 | −8  | +1 | +35 | +23 |
| f5       | 36 | 22 (92)  | 14 (71)  | +38 | −8  | +1 | +36 | +24 |
| buy-and-hold | 3 | 3 (50) | 0 (0) | **+50** | 0 | +50 | +50 | +50 |

**Unintended shorting.** Every MM variant went net short at some
point. Baseline −17 is the worst; promoted/alt/h1/f5 all dipped to
−8. Buy-and-hold is the only variant that never shorts, by
construction.

**Near-limit behaviour** (`near-limit = 0.75 × position_limit`; limit
= 50 for all public controls, so threshold = 37.5):

| Variant | Max long | Near-limit observations |
|---|---:|---|
| baseline     | +40 | 1 crossing |
| promoted     | +37 | 0 (peak just below threshold) |
| alt          | +45 | some near-limit (entered [37.5, 45]) |
| h1           | +37 | 0 |
| f5           | +38 | 1 brief crossing |
| buy-and-hold | +50 | **at or near-limit for the full session after tick 0** |

## A4. Maker/taker split

**Not inferable from the official `.log` alone.** `tradeHistory`
records `buyer`/`seller`/`price`/`quantity` only; no maker/taker tag.
A counterparty-vs-own-quote proxy would require the bot's own quote
history, which the official log does not include. Known uncertainty;
flagged, not a decision gate.

## A5. Diagnosis, one line each

| Variant | Diagnosis |
|---|---|
| baseline     | Symmetric flatten=0.8; eager early sells → −58 bucket 0, −17 short. Drift rescues full-day. |
| promoted     | Wider cross (taker=2.0) + flatten=0.7 caps inventory at ±35 → mid-day long capped. |
| alt          | Same edges, skew=1.0 + flatten=0.9 → rides to +45; bucket-2 lift vs promoted is the payoff. |
| h1           | Promoted PEPPER + alt ASH. PEPPER PnL == promoted; H1 improvement is entirely on ASH. |
| f5           | Promoted PEPPER + asymmetric taker (buy=1.5/sell=3.0). Wider sell edge → finishes +21 → +2 135. Best MM on record. |
| buy-and-hold | Full +50 at tick 0, hold. **PEPPER PnL = +4 559.** Directional upper-bound. No spread capture; just drift MTM. |

## A6. Frozen ASH leg for this pass

H1 / Alt / F5 / buy-and-hold all share the same wall-based ASH leg.
Local replay of that leg scored +982.81 on the official day
(identical across those four variants). **The v2 PEPPER search
treats this leg as byte-identical fixed input:**

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

No ASH dimension is explored in v2.

## A7. In-family anchor control — `C_corelong_v1_base50`

v1 recommended `B_base50` (`base_long=50, add_thresh=3.0,
trim_thresh=5.0, add_gain=3.0, trim_gain=1.0, floor=0, ceiling=80,
step=8, exec="hybrid", hybrid_threshold=2.0`) but **did not upload
it** — v1's projected lift over F5 was within measurement noise (~+150
to +450 PEPPER PnL). v2 re-runs this exact config as a reference
inside the v2 runner so every v2 candidate is comparable not only
against F5 but against v1's best-of-family.

Local-to-official calibration from v1 (10–11×):

- C_f5 local +25 055 vs official +2 135 = 11.7×
- C_promoted local +19 225 vs official +1 797 = 10.7×
- C_alt local +22 324 vs official +2 057 = 10.9×

v1 also used a **mis-described** official-cadence proxy: it filtered
local day-0 by `timestamp % 1000 == 0`, which yields 1000 snapshots
but at 10× sparser cadence over a 10× longer time window than the
real official day. v2 fixes this — see Phase B and the v2 runner
docstring for the correct **official-range proxy** (day 0,
`0 ≤ timestamp ≤ 99_900` at native 100-tick cadence = 1000 snapshots
over the real official day's time range). The v1 numbers above are
re-usable because they are **official**, not local; the v1 *local*
numbers are not directly comparable to v2 local numbers and v2 will
re-measure them with the corrected proxy.
