# V7 — Profit-Taking on Mid-Recross of μ

**Bundle:** `outputs/submissions/submission_r3_v7_profit_take.py` (68.5 KB, r3 profile, minified)

## The single lever

Submission 7 (v6 MR) reached **+$18,474 peak** at ts=70,000 but ended at **+$6,697**
— a **$12K drawdown in the final 30K ticks**. The alpha IS there; we were giving
it back by holding winning positions through the next cycle's reversal.

**v7 fixes exit discipline, nothing else.** The MR entry logic, fair-value anchors,
EWMA tracking, delta budget, and terminal ramp are all unchanged from v6.

## The change (two files)

### `src/strategies/round_3/hydrogel_mm.py`

New override executed **before** the SST take/clear/make pipeline:

```python
if abs(mid - 9990.0) < 10 and abs(position) >= 30:
    return _profit_take_orders(snapshot, position)
```

`_profit_take_orders` emits a single market-crossing order for the full position:
- Long → sell at best_bid
- Short → buy at best_ask

No child splitting (speed > stealth). Full position in one order.

### `src/strategies/round_3/vev_4000_mm.py`

Mirror logic, anchored to `velvet_mean − 4000`:

```python
if velvet_mean is not None and vev_snapshot.mid is not None:
    vev_mid = float(vev_snapshot.mid)
    if (
        abs(vev_mid - fair_value) < 8
        and abs(position) >= 40
    ):
        return _vev4000_profit_take_orders(vev_snapshot, position)
```

Band is 8 ticks (vs HYDROGEL's 10) and min-pos is 40 (vs 30) — tuned for
VEV_4000's wider 21-tick spread and 300-position limit.

## Why this is a high-confidence change

**Submission 7 replay with v7 logic (verified by tick-by-tick reconstruction in
PER_ASSET_DEEP_RESEARCH.md):**

| ts | mid | pos before | v6 action | v7 action | Expected lock-in |
|---|---|---|---|---|---|
| 25,000 | 9990 | −200 | hold (near cap, no clear) | **FLATTEN (buy 200 @ ask)** | ~$5.9K realized |
| 70,000 | 9996 | +177 | hold through reversal | **FLATTEN (sell 177 @ bid)** | ~$18.5K realized |

v6 held +200 from ts=70K→80K→90K as mid fell 9996→9960→9927, losing back $13K
unrealized. v7 exits at ts=70K locking in the peak, then re-enters on the
next deviation (ts=75K+).

## Expected PnL

Per the deep research doc:

| Source | v6 submission 7 | v7 projection |
|---|---|---|
| HYDROGEL | $6.7K | **$15–18K** |
| VEV_4000 | $2.2K | $3–4K |
| VELVET (hedge) | −$0.5K | −$0.5K (unchanged) |
| Voucher MM | $0 | $0 (still disabled) |
| **Total** | **$8.4K** | **$18–23K** |

**Theoretical ceiling for this 1K-tick round is ~$41K (3 HYDROGEL cycles ×
$10K + $8K VEV + residuals).** v7 targets ~50% of that ceiling. The remaining
gap requires tier-2 alpha (bot-behavior signals, micro-structure) which should
be built ONLY after v7 verifies the profit-take thesis.

## Risks

1. **Re-entry whiplash:** v7 flattens at μ, then the NEXT deviation re-enters
   at full size. If the cycle period shortens, we could pay the 2-tick spread
   cost twice in a short span. Mitigation: min-pos threshold (30/40) prevents
   tiny round-trips.
2. **Band too narrow:** if mid oscillates ±10 around μ without ever pushing
   out to ±25 (our take_width), we exit with small gains and miss the full
   cycle. Current empirical data (sub-7) shows clean ±30-60 tick deviations,
   so the band should trigger cleanly.
3. **Asymmetric fill risk:** crossing the spread on a 200-unit order pays
   ~1 tick slippage on average ($200 cost), negligible vs the $10K+ cycle gain
   we're locking in.

## Tests

6 new unit tests in `tests/test_r3_primitives.py`:

- `test_profit_take_flattens_long_near_mean` — long 150 + mid 9990 → flatten
- `test_profit_take_flattens_short_near_mean` — short 120 + mid 9990 → flatten
- `test_profit_take_skipped_when_small_position` — pos 15 → normal SST logic
- `test_profit_take_skipped_when_far_from_mean` — mid 10005 → MR take, not flatten
- `test_vev4000_profit_take_flattens_long_near_mean` — flatten VEV long
- `test_vev4000_profit_take_skipped_without_velvet_mean` — no anchor → no flatten

Full suite: **994 tests passing.**

## Ship decision

Submit `submission_r3_v7_profit_take.py`. This is the highest-conviction change
since the v6 MR pivot:

- v6 proved MR alpha exists (+$18K peak)
- v7 captures the peak instead of giving it back

If v7 realizes ≥$15K → validate thesis, proceed to Tier 2 (bot-behavior signals).
If v7 realizes $8–15K → partial win, refine band/min-pos parameters.
If v7 realizes <$8K → profit-take fired in the wrong regime; need live-session
tick data to diagnose whether bands are off or the MR cycles differ from sub-7.
