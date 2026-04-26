# Postmortem: R3 submission 379928 — +$179.77 (expected +$5K–$10K)

**Status:** Fixes applied. New bundle at `outputs/submissions/submission_r3_v3_fixed.py` (67KB).

## What happened

Submission 379928 executed cleanly — no crashes, no errors, no wrong-symbol orders (the two previous classes of bugs are fixed). But it only earned **+$179.77** vs the LOO-predicted **+$14,896**.

Breakdown from the platform tape:

| Product | Platform trades in round | Our trades | Our PnL |
|---|---|---|---|
| HYDROGEL_PACK | 20 | **0** | **+0.0** |
| VELVETFRUIT_EXTRACT | 54 | 6 (2 buy, 4 sell) | +113.2 |
| VEV_4000 | 9 | 9 (5 buy, 4 sell) | +66.6 |
| VEV_5300–6500 | 42 combined | 0 | +0.0 |
| **Total** | **125** | **15** | **+179.8** |

The dominant alpha source (HYDROGEL) got **zero fills**. Two fixable root causes.

## Root cause 1: R3 live round is 10× SHORTER than historical data

The activitiesLog shows **1,000 snapshots** (ts 0 → 99,900 in steps of 100), NOT 10,000 like the historical per-day CSVs we used for LOO. This means:

- Our terminal ramp started at `t=850_000` — **never fires** in a round that ends at `99_900`. We ran at full-bands through the final tick and were exposed to end-of-round FV marking on open positions.
- Our `R3DeltaBudget.TERMINAL_START = 850_000` never triggered — same issue.
- **All LOO P&L predictions were scaled to 10K-tick days**; live R3 = 1K ticks, so realistic predictions are **~1/10 of LOO numbers**.

### Fix

| File | Change |
|---|---|
| `src/core/primitives/terminal_ramp.py` | `_RAMP_START` 850_000 → 85_000, `_RAMP_END` 950_000 → 95_000 |
| `src/core/primitives/r3_delta_budget.py` | `TERMINAL_START` 850_000 → 85_000 |
| `tests/test_r3_primitives.py` | All test constants updated to new thresholds |

Now the ramp starts at t=85K (85% through the round) and flat-liquidation region starts at t=95K, aligning with the actual live round length.

## Root cause 2: HYDROGEL quote placement was BEHIND best on both sides

With `quote_inside_wall=True`, SST pegged HYDROGEL quotes to "one tick inside the largest-volume wall":

- Wall bid = 10001 (vol 21, L2), wall ask = 10022 (vol 21, L2)
- Our bid = 10002, our ask = 10021
- Market best-bid = **10003** (vol 13), best-ask = **10019** (vol 13)

**Our bid 10002 was 1 tick BELOW market best-bid 10003. Our ask 10021 was 2 ticks ABOVE market best-ask 10019.** We were behind the best on both sides. Fills require BOTH the market best to be consumed first AND the subsequent flow to reach our price. In a 1,000-tick round with only 20 HYDROGEL trades total, this never happened.

### The inside-wall assumption failed because HYDROGEL's best-bid wasn't a penny-jumper

The inside-wall pattern (from R1/R2 top-team strategies on ASH/RR) assumes the best-bid/ask is a lone penny-jumper and the deep wall is the "true" market. In R3 HYDROGEL:

- best-bid vol 13 vs deep vol 21 — both credible, not a penny-jumper situation
- spread 16 ticks with layer-2 visible on every tick
- market trades happen AT the best-bid or best-ask offsets (±8 from mid), not at the wall offsets (±10)

The strategy mis-read the order book structure.

### Historical trade-price distribution (offset from mid, pooled 3 days)

```
offset  -8: qty 1918 ████████████████████████  (best-bid)
offset  -4: qty   42 (rare — inside spread)
offset  +4: qty   95 (rare — inside spread)
offset  +8: qty 2023 ████████████████████████  (best-ask)
```

**97% of trades happen AT the best-bid or best-ask.** Zero trades at ±3 offset. This also means the local fill model (which matches at exact price) would never fill our old quotes at mid ± 9–10.

### Fix

| File | Change |
|---|---|
| `src/strategies/round_3/hydrogel_mm.py` | `quote_inside_wall=False` (was True), `default_quote_size=10` (was 5) |

**New quote placement** (real R3 day-0 ts=0 book):
- Fair value = mid = 10011
- Bid = fair − edge = 10008 (5 ticks BETTER than market best-bid 10003)
- Ask = fair + edge = 10014 (5 ticks BETTER than market best-ask 10019)
- Size doubled to 10 (matches bot shot sizes 2–6 with room to absorb multiple hits)

On the live platform, an aggressive seller who would have historically hit 10003 now sees our 10008 (a better price for them) and will hit us first. Same for aggressive buyers hitting 10014 instead of 10019.

**Expected edge/fill math:**
- Historical aggressive-sell flow: ~1,900 qty at mid−8 per 10K-tick day → **~190 qty per 1K-tick live round**
- We're top-of-book at mid−3, size 10. Fills up to size-10 per aggressive event before flow walks down.
- Conservatively assume we capture 50% of flow = ~95 qty on buy side over the round.
- Edge per trade = 3 ticks (mid-3 entry, mean-reverts to mid). PnL ~ 95 × 3 = **+$285 on buys alone**.
- Similar on asks. Round-trip PnL estimate: **+$500–$800 HYDROGEL** for the live round.

## What didn't break

- VEV_4000: **9/9 platform trades participated**. Correct symbol, correct prices, 100% participation. +$66 on 20 qty = $3.3/trade edge.
- VELVET hedge: active when needed (net_delta > idle threshold). +$113 from hedge legs + drift.
- VEV_6000/6500 zero-bid lottery: orders placed at price 0, filled if platform accepts.
- Bundle integrity (post-previous-fix): no crashes, no wrong symbols, no missing orchestrator.step.

## What's now missing / still fragile

1. **Live fill model is an open question.** Our LOO harness uses a simplified model (+fixed edge × 15% fill probability). Live platform matching is different. The HYDROGEL fix works IF the platform fills inside-spread top-of-book quotes; if it only fills at historical prices, we still won't fill.
2. **Voucher liquidity (K=5400/5500) remains disabled.** LOO negative. Live would be ~1/10 of LOO loss (~−$14 max) but upside is also ~1/10 (+$15 max). Marginal to re-enable.
3. **Aggressive-take opportunities not exploited.** In a 1K-tick round, passive MM alone won't pile up enough trades. We could add: "if market ask < fair − take_threshold, cross to buy". Currently `take_width=8` on HYDROGEL means we only take when price moves >8 ticks against fair — essentially never fires. Could reduce to 3–4.
4. **Size could go higher on HYDROGEL.** Pos limit 200 with 20 market trades × size 6 max = 120 qty max flow each side. Our size 10 is probably right. Could bump to 15 if confident.

## New bundle

- Path: `outputs/submissions/submission_r3_v3_fixed.py`
- Size: 67,266 bytes (well under 128KB target)
- Passes all 988 tests including 13 bundle regression tests.

Smoke-test output on real R3 day-0 ts=0 book:

```
HYDROGEL_PACK: px=10008 qty=+10 (top-of-book, 5 ticks better than market)
HYDROGEL_PACK: px=10014 qty=-10 (top-of-book, 5 ticks better than market)
VEV_4000:      px=1264  qty=+5
VEV_4000:      px=1271  qty=-5
VEV_6000:      px=0     qty=+300 (lottery)
VEV_6500:      px=0     qty=+300 (lottery)
VELVETFRUIT:   (no orders — idle guard active at pos=0, net_delta=0)
```

## Expected live performance

Under the stated assumption that Prosperity fills inside-spread top-of-book quotes:

| Source | Prior submission | v3 estimate |
|---|---|---|
| HYDROGEL MM | +0 | +500 to +800 |
| VEV_4000 MM | +66 | +150 to +250 (doubled from better VELVET hedge) |
| VELVET hedge | +113 | +100 to +200 |
| Vouchers 5300+ | +0 | +0 (disabled) |
| Zero-bid lottery | +0 (rejected?) | 0 to +300 |
| **Total estimate** | **+180** | **+750 to +1,550** |

If HYDROGEL fill assumption is wrong (platform won't fill inside-spread), PnL stays ~+200. Would need to join-best (edge=8) or increase take-side aggression instead.

## Action items for user

1. **Re-submit** `outputs/submissions/submission_r3_v3_fixed.py`.
2. If HYDROGEL still shows 0 fills, the next fix is `default_edge=8` (join market best bid/ask) with `quote_inside_wall=False` to join the queue.
3. Manual Bio-Pod bids 751/841 still pending UI submission.
