# Phase A — Frozen PEPPER controls (sparse-overlay pass)

Reference numbers for every candidate in this pass. Values are read
directly from the IMC official result files
(`outputs/round_1/official_results/*/*.json`), not from local replay.
Per `CLAUDE.md` Evidence Calibration, official is the source of truth
and local is a secondary ranking signal.

**v2 pass updated the picture materially**: buy_hold_80 (+7 286
PEPPER) now dominates every market-making variant by a 3× margin,
and V2_clean (+5 426 PEPPER) — the best non-directional variant —
still gives up **−1 860 PEPPER PnL** to buy-hold. That gap defines
the problem this pass is trying to close.

## A1. Top-line official numbers

| Variant | Submission | Total PnL | ASH PnL | **PEPPER PnL** | Final PEPPER pos |
|---|---|---:|---:|---:|---:|
| promoted     | 115254 | +2 518.11 | +720.91 | +1 797.20 | −2 |
| alt          | 115380 | +3 040.22 | +982.81 | +2 057.41 | +6 |
| f5           | 152878 | +3 117.72 | +982.81 | +2 134.91 | +21 |
| **V2_clean** | 169807 | +6 385.78 | +959.78 | **+5 426.00** | +50 |
| **buy_hold_80** | 162376 | **+8 245.78** | +959.78 | **+7 286.00** | **+80** |

ASH leg (+959.78) is **byte-identical** across V2_clean and buy_hold_80
— the same wall-based ASH leg. The +1 860 total-PnL gap between
V2_clean and buy_hold_80 is **entirely a PEPPER-leg difference**.

## A2. PEPPER PnL by bucket (official activitiesLog)

| Variant | 0–25k | 25k–50k | 50k–75k | 75k–end | Full day |
|---|---:|---:|---:|---:|---:|
| promoted     | +31    | +410   | +942   | +414   | +1 797.20 |
| alt          | +31    | +333   | +1 084 | +609   | +2 057.41 |
| f5           | +31    | +458   | +970   | +676   | +2 134.91 |
| **V2_clean** | **+907** | **+1 544** | **+1 680** | **+1 295** | **+5 426.00** |
| **buy_hold_80** | **+1 294** | **+2 000** | **+2 000** | **+1 992** | **+7 286.00** |

Cumulative through first 25k / 50k:

| Variant | first 25k | first 50k | first 75k |
|---|---:|---:|---:|
| promoted     | +31    | +441    | +1 383 |
| alt          | +31    | +364    | +1 448 |
| f5           | +31    | +489    | +1 459 |
| V2_clean     | +907   | +2 451  | +4 131 |
| **buy_hold_80** | **+1 294** | **+3 294** | **+5 294** |

**V2_clean already closed 61 %** of the F5 → buy_hold gap on first-25k
and 64 % on full-day. The remaining gap is:

| Bucket | V2_clean − buy_hold | Interpretation |
|---|---:|---|
| 0–25k | **−387** | Opening seed reached +60, not +80 (missing 20 units × drift) |
| 25k–50k | −456 | Trim/rebuy cycles gave up some carry mid-day |
| 50k–75k | −320 | Same mid-day give-up, continued |
| **75k–end** | **−697** | **Biggest gap.** V2_clean finished at +50 (base_long), buy_hold at +80 (limit) — 30 units × drift over the final quarter |

**The 75k–end gap is the single most actionable signal.** V2_clean
reverted to `base_long=50` by end-of-day, surrendering 30 units of
long exposure for the last quarter of the session. A near-buy-hold
family that defaults to +80 instead of +50 would, in the best case,
close roughly +697 of that.

## A3. PEPPER trade & position statistics (from official tradeHistory)

| Variant | Trades | Max long | Max short | End of 25k | End of 50k | End of 75k | Final |
|---|---:|---:|---:|---:|---:|---:|---:|
| promoted     | 41 | +37 | −8  | +1  | +35 | +23 | −2  |
| alt          | 45 | +45 | −8  | +1  | +30 | +31 | +6  |
| f5           | 36 | +38 | −8  | +1  | +36 | +24 | +21 |
| V2_clean     | ~30| ~+60 | 0  | +60 | ~+50| ~+50| +50 |
| **buy_hold_80** | **3** | **+80** | 0 | +80 | +80 | +80 | **+80** |

(V2_clean trade/position details reconstructed approximately; full
SUBMISSION tape available in `169807.json`.) Buy_hold_80 crossed
once at tick 0 and held; V2_clean seeded to +60 then oscillated
around +50 for the day.

**Unintended shorting.** Promoted/alt/f5 each dipped to −8; V2_clean
and buy_hold_80 never went short (both `open_no_short` or
buy-and-hold-by-construction).

## A4. Maker/taker split

Not inferable from the official `.log` alone — `tradeHistory` has no
maker/taker tag. Known uncertainty; not a decision gate for this pass.

## A5. Diagnosis, one line each

| Variant | Diagnosis |
|---|---|
| promoted     | Symmetric chassis, flatten=0.7, PEPPER pinned at ±35 by flatten. Pre-V2 reference. |
| alt          | Same PEPPER chassis, flatten=0.9 loosens the cap → rides to +45 → +260 PnL over promoted. Still mean-reverting. |
| f5           | Asymmetric taker (buy=1.5/sell=3.0) widens the sell side → avoids early wrong-side shorts → +2 135 PEPPER. Best pre-V2. |
| **V2_clean** | **Opening-seeded core-long at base=50.** First candidate to break +5k PEPPER. But defaults to +50, not +80 — gives up ~30 units of carry for long stretches. |
| **buy_hold_80** | **Pin +80 at tick 0, hold.** Directional upper bound at the true 80 limit. No overlay, no execution edge — pure drift MTM minus one spread cost. **The number to beat with <+80 near-limit time.** |

## A6. Frozen ASH leg for this pass

Identical to V2_clean / H1 / F5 / Alt — the wall-based leg that
scored +959.78 officially on 2 of the 2 most recent uploads:

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

No ASH dimension is explored. Any total-PnL comparison across this
pass's candidates is a pure PEPPER-leg comparison at a fixed
+959.78 ASH contribution.

## A7. In-family anchor control — `C_v2_clean_ref`

V2_clean's PEPPER config re-run through this pass's runner so every
sparse-overlay candidate compares against it under the **same
proxy** (corrected 100-tick cadence), not against v2's local
numbers.

```python
CoreLongParams(
    base_long=50, add_thresh=3.0, trim_thresh=5.0,
    add_gain=5.0, trim_gain=1.0, floor=0, ceiling=80,
    step=8, exec_style="hybrid", hybrid_threshold=2.0,
    open_seed_size=60, open_window=1000, open_no_short=True,
)
```

## A8. Calibration update

V2_clean's proxy-to-official ratio is now measurable (PEPPER +5 472.5
proxy vs +5 426 official = **1.009×**). Combined with buy_hold_80
(proxy +7 279 vs official +7 286 = **0.999×**), the seeded/directional
family's calibration is **essentially 1:1**. That is much better than
the 1.3–1.8× ratio measured on the pure-MM controls and strongly
validates the corrected official-range proxy for seeded candidates.

**Implication for this pass:** proxy PEPPER numbers can be
compared to official PnL directly (±5 %). A proxy lift of +500
PEPPER over V2_clean projects to roughly +500 official.
