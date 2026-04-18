# ASH target-position candidates (sorted by score)

- `off_*` columns: official-cadence view (day 0 filtered to
  `ts % 1000 == 0`, ~1000 snapshots).
- `local_*` columns: full 3-day × 10k replay.
- `delta_vs_h1`: `off_ash` minus the C_h1_alt row's `off_ash`.
- Scoring formula (see `run_ash_target.py:score`):

        score = off_ash
              + 0.20 * min(off_b0..b3)
              + 0.02 * local_ash
              - 0.5  * |off_final_pos|
              - 1.0  * off_near_limit

All candidates share the Promoted PEPPER leg.


| label | note | off_ash | off_b0 | off_b1 | off_b2 | off_b3 | off_trades | off_maker | off_taker | off_maker_pct | off_avg_size | off_final_pos | off_near_limit | off_mk1 | off_mk5 | off_mk20 | off_pep | local_ash | local_trades | local_final_pos | local_near_limit | score | delta_vs_h1 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| D7_deep_dz | dz d=4 a=5 cap=30 hybrid th=4.0 me=1.5 | 558.00 | -6.00 | 72.00 | -35.00 | 25.00 | 33 | 1 | 32 | 0.03 | 7.36 | -31 | 0 | -4.13 | -2.96 | -1.93 | 16321.00 | 7383.00 | 391 | -30 | 1001 | 683.16 | 346.00 |
| L5_mild | linear a=2 cap=20 hybrid th=2.0 | 523.00 | -6.00 | 72.00 | -35.00 | 25.00 | 32 | 1 | 31 | 0.03 | 6.91 | -21 | 0 | -2.77 | -1.72 | -0.50 | 16321.00 | 6751.00 | 382 | -27 | 0 | 640.52 | 311.00 |
| D6_mild | dz d=2 a=3 cap=20 hybrid th=3.0 me=1.5 | 514.00 | -6.00 | 72.00 | -35.00 | 25.00 | 32 | 1 | 31 | 0.03 | 6.88 | -22 | 0 | -2.81 | -1.75 | -0.53 | 16321.00 | 6459.00 | 373 | -27 | 0 | 625.18 | 302.00 |
| C_promoted | Promoted (ewma_mid m=1.0 t=0.25) | 357.00 | 4.50 | 40.50 | -11.50 | 12.50 | 19 | 0 | 19 | 0.00 | 6.95 | -4 | 0 | 1.84 | 1.41 | 3.36 | 16321.00 | 6447.00 | 472 | 4 | 0 | 481.64 | 145.00 |
| D4_taker | dz d=1 a=8 cap=40 taker th=2.0 me=1.5 | 605.00 | -6.00 | 72.00 | -35.00 | 25.00 | 39 | 0 | 39 | 0.00 | 7.51 | -37 | 334 | -3.91 | -2.81 | -2.13 | 16321.00 | 8252.00 | 470 | -38 | 7852 | 410.54 | 393.00 |
| L3_taker | linear a=5 cap=40 taker th=2.0 | 605.00 | -6.00 | 72.00 | -35.00 | 25.00 | 39 | 0 | 39 | 0.00 | 7.51 | -37 | 334 | -3.91 | -2.81 | -2.13 | 16321.00 | 8144.00 | 461 | -44 | 9098 | 408.38 | 393.00 |
| L2_hybrid_hi | linear a=10 cap=40 hybrid th=2.0 | 605.00 | -6.00 | 72.00 | -35.00 | 25.00 | 39 | 0 | 39 | 0.00 | 7.51 | -37 | 334 | -3.91 | -2.81 | -2.13 | 16321.00 | 8110.00 | 460 | -42 | 11556 | 407.70 | 393.00 |
| D2_hybrid_hi | dz d=2 a=10 cap=40 hybrid th=2.0 me=1.5 | 605.00 | -6.00 | 72.00 | -35.00 | 25.00 | 39 | 0 | 39 | 0.00 | 7.51 | -37 | 334 | -3.91 | -2.81 | -2.13 | 16321.00 | 8103.00 | 459 | -36 | 6502 | 407.56 | 393.00 |
| D5_wide_maker | dz d=2 a=10 cap=40 hybrid th=3.0 me=2.0 | 605.00 | -6.00 | 72.00 | -35.00 | 25.00 | 39 | 0 | 39 | 0.00 | 7.51 | -37 | 334 | -3.91 | -2.81 | -2.13 | 16321.00 | 8103.00 | 459 | -36 | 6502 | 407.56 | 393.00 |
| L1_hybrid | linear a=5 cap=40 hybrid th=2.0 | 605.00 | -6.00 | 72.00 | -35.00 | 25.00 | 39 | 0 | 39 | 0.00 | 7.51 | -37 | 334 | -3.91 | -2.81 | -2.13 | 16321.00 | 8091.00 | 456 | -41 | 9333 | 407.32 | 393.00 |
| D1_hybrid | dz d=1 a=8 cap=40 hybrid th=2.0 me=1.5 | 605.00 | -6.00 | 72.00 | -35.00 | 25.00 | 39 | 0 | 39 | 0.00 | 7.51 | -37 | 334 | -3.91 | -2.81 | -2.13 | 16321.00 | 8055.00 | 457 | -38 | 5995 | 406.60 | 393.00 |
| V1_gamma15 | convex g=1.5 a=3 cap=40 hybrid th=2.0 | 605.00 | -6.00 | 72.00 | -35.00 | 25.00 | 39 | 0 | 39 | 0.00 | 7.51 | -37 | 334 | -3.91 | -2.81 | -2.13 | 16321.00 | 8055.00 | 457 | -38 | 5995 | 406.60 | 393.00 |
| V2_gamma20 | convex g=2.0 a=1.5 cap=40 hybrid th=3.0 | 605.00 | -6.00 | 72.00 | -35.00 | 25.00 | 39 | 0 | 39 | 0.00 | 7.51 | -37 | 334 | -3.91 | -2.81 | -2.13 | 16321.00 | 7966.00 | 454 | -43 | 8617 | 404.82 | 393.00 |
| C_baseline | Baseline ASH (wall_mid m=1.0 t=1.0) | 248.00 | -10.50 | 31.50 | -0.50 | 7.50 | 29 | 0 | 29 | 0.00 | 7.17 | -12 | 0 | 1.66 | 1.55 | 2.97 | 16321.00 | 7301.00 | 650 | -5 | 100 | 385.92 | 36.00 |
| C_h1_alt | H1/Alt/F5 ASH leg (wall_mid m=1.5 t=0.5) | 212.00 | -10.50 | 31.50 | -0.50 | 7.50 | 30 | 0 | 30 | 0.00 | 7.13 | -18 | 0 | 1.66 | 1.55 | 2.97 | 16321.00 | 7747.00 | 766 | -9 | 110 | 355.84 | 0.00 |
| W2_wall_dz0 | wall-mean dz d=0 a=5 cap=40 hybrid th=2.0 | 98.00 | -10.50 | 31.50 | -0.50 | 7.50 | 27 | 0 | 27 | 0.00 | 6.93 | -11 | 0 | 1.73 | 1.67 | 3.02 | 16321.00 | 8453.00 | 639 | 28 | 405 | 259.46 | -114.00 |
| W1_wall_dz1 | wall-mean dz d=1 a=8 cap=40 hybrid th=2.0 | 38.00 | -10.50 | 31.50 | -0.50 | 7.50 | 27 | 0 | 27 | 0.00 | 7.04 | -14 | 0 | 1.72 | 1.43 | 2.80 | 16321.00 | 8735.00 | 644 | 36 | 1596 | 203.60 | -174.00 |
| D3_maker | dz d=1 a=8 cap=40 maker th=2.0 me=1.5 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 0 | 0 | 0.00 | 0.00 | 0 | 0 |  |  |  | 16321.00 | 12.00 | 5 | 0 | 0 | 0.24 | -212.00 |
| L4_maker | linear a=5 cap=40 maker th=2.0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 0 | 0 | 0.00 | 0.00 | 0 | 0 |  |  |  | 16321.00 | 8.00 | 4 | 0 | 0 | 0.16 | -212.00 |

## Interpretation

Three structurally different clusters emerged from the 19-candidate grid.

### Cluster 1 — saturated taker/hybrid (L1/L2/L3, D1/D2/D4/D5, V1/V2)

All nine high-cap (`cap=40`) anchor-based candidates produce **identical
off-cadence PnL (+605)** and **identical near-limit exposure (334 of
1000 snapshots)**. They pin the position at **−37** before flatten
engages. Mechanism: residual of +6 produces target −40 in one step,
taker fills move pos past the flatten threshold (−35) in one step, so
the flatten valve only fires *after* we've already saturated. 3-day
local shows the same effect amplified: `local_near_limit` between
5 995 and 11 556 (20–38 % of 30 000 snapshots).

**Disqualified.** Extra +346 / +393 `off_ash` vs H1/Alt is paid for
entirely by a ~15× increase in tail-risk vs Alt's already-flagged 22
near-limit snapshots.

### Cluster 2 — maker-only (L4, D3)

Zero fills (off-cadence) and ~10 fills (3-day local). The local
simulator's passive fill model is extremely sparse on ASH: even the
shipped **C_h1_alt only books 9 maker fills in 30 000 local
snapshots** (757 of its 766 fills are taker). Any maker-only
strategy therefore looks broken under this simulator regardless of
logic quality.

**Inconclusive from local.** Can only be tested by running
maker-only in the official environment, which this pass explicitly
does not do.

### Cluster 3 — mild target (D6, D7, L5)

Smaller alpha (2–5) and smaller cap (20–30) keep the target inside
the flatten threshold at all times.

| Candidate | off_ash | Δ vs H1 | off_near_limit | 3-day local ash | Δ vs H1 local | 3-day near_limit | off_markouts (1/5/20) |
|---|---:|---:|---:|---:|---:|---:|---|
| **D7_deep_dz** | +558 | **+346** | **0** | +7383 | −364 | 1001 | −4.1 / −3.0 / −1.9 |
| **L5_mild**    | +523 | +311 | 0 | +6751 | −996 | 0 | −2.8 / −1.7 / −0.5 |
| **D6_mild**    | +514 | +302 | 0 | +6459 | −1288 | 0 | −2.8 / −1.8 / −0.5 |
| C_h1_alt (ref) | +212 | 0 | 0 | +7747 | 0 | 110 | +1.7 / +1.6 / +3.0 |

**Split signal.** The mild variants beat H1/Alt by +300–346 under the
official-cadence sampling rate but lose by −364 to −1288 under the
dense 3-day sampling rate. They also show **negative markouts** at
every horizon (the strategy sells into rising prices expecting
reversion; the realized PnL captures the reversion over the full
horizon, but the short-horizon markout is against us).

### Cluster 4 — wall_mean (W1, W2)

`target_mean_source="fair"` with `wall_mid` makes the residual
structurally near-zero, so the target-position logic almost never
engages. These degenerate into a passive MM with slightly different
quoting: 3-day local PnL is **+8735 / +8453** (above H1/Alt's
+7747) but off-cadence PnL is *worse* (+38 / +98 vs +212). They're
not really testing the target-position hypothesis.

## Confidence / risk map

| Row | `off_ash` vs H1 | `local_ash` vs H1 | off_near_limit | 3d near_limit | Verdict |
|-----|---:|---:|---:|---:|---|
| D7_deep_dz | **+346** | −364 | 0 | 1001 | Promising on single-day view only |
| L5_mild    | +311 | −996 | 0 | 0   | Promising on single-day view only |
| D6_mild    | +302 | −1288 | 0 | 0 | Promising on single-day view only |
| L1/L2/L3/D1/D2/D4/D5/V1/V2 | +393 | +308..+505 | **334** | 5 995..11 556 | Disqualified (saturation) |
| W1/W2 | −114 / −174 | +988 / +706 | 0 | 405 / 1596 | Not really target-position |
| L4/D3 maker-only | −212 | −7739 | 0 | 0 | Fill-model-limited, inconclusive |

See `final_recommendation.md` for the upload decision.
