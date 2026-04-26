# V5 — Hold-To-End Short-Premium

**Bundle:** `outputs/submissions/submission_r3_v5_hold.py` (69KB)

## What went wrong in v4 (submission 381248, −$2.66)

The short strategy WORKED at entry — we successfully shorted to cap on K=5400/5500/5300. But we DESTROYED the edge by flattening:

| Strike | Buys qty | Sells qty | Min pos | Final pos | PnL |
|---|---|---|---|---|---|
| VEV_5300 | 115 | 115 | −115 | **0** | **−$228** |
| VEV_5400 | 201 | 201 | −201 | **0** | **−$319** |
| VEV_5500 | 201 | 201 | −201 | **0** | **−$201** |

All three strikes: **sold at bid (entry), covered at ask (exit) → paid bid-ask spread twice on every round trip**. Net −$748 on 517 qty of voucher round-trips purely to spread costs.

**Cause 1:** `_COVER_AFTER_TS = 90_000` in short_premium forced us to buy back.
**Cause 2:** `voucher_liquidity` on the same strikes bid at best-bid while we were short — public sells hit our bid (we BOUGHT), covering our short at no benefit.

Critical insight: **the whole point of short-premium is to NOT flatten.** The hidden end-of-round FV does that. Whatever model it uses (intrinsic / BSM fair / end-mid), it's ≤ open-mid for OTM → we profit.

## V5 changes

### 1. Remove cover logic entirely

`voucher_short_premium.py` no longer has `_COVER_AFTER_TS`. Once positioned, we HOLD to final tick. Platform marks against hidden FV.

### 2. Disable voucher_liquidity for R3

`r3_engine.py` no longer calls `voucher_liquidity_orders`. Code retained for future rounds.

### 3. Bounded-cost aggressive seeding

New `ShortTarget` schema:
- `seed_bid_hit_qty`: one-time aggressive entry at bid (pays spread ONCE)
- `seed_ticks`: number of ticks the bid-hit remains active
- Passive ask orders continue through `entry_window_end` (zero spread cost)

Target sizes:
| Strike | Seed qty | Spread | Entry cost | Intrinsic upside |
|---|---|---|---|---|
| K=5500 | 200 | 1 | $200 | $1,300 |
| K=5400 | 200 | 2 | $400 | $3,400 |
| K=5300 | 100 | 2 | $200 | $5,300 |
| **Total** | | | **$800** | **$10,000** |

Target upside ≈ $10K if platform marks at intrinsic, bounded entry cost ≈ $800 if marks at end-mid.

## Expected PnL scenarios

| Scenario | Delta-1 MM (HYDROGEL+VELVET+VEV_4000) | Voucher shorts | Total |
|---|---|---|---|
| Mark = intrinsic | +$700–1,000 | **+$9,000–12,000** | **+$9.7K–13K** |
| Mark = BSM fair (true σ) | +$700–1,000 | +$6,000–9,000 | +$6.7K–10K |
| Mark = end-mid | +$700–1,000 | +$500–1,500 | +$1.2K–2.5K |
| Mark = (entry cost only, no hold payoff) | +$700–1,000 | −$800 | ~$0 |

Worst case is roughly breakeven. Best case is **15–20× prior submission**.

## Orders at ts=0 (verified)

```
HYDROGEL_PACK: BUY  10008 x50,  SELL 10014 x50       (MM top-of-book)
VEV_4000:      BUY  1264  x30,  SELL 1271  x30       (MM hedge-aware)
VEV_5300:      SELL 52    x100 (SEED bid-hit),  SELL 54 x50 (passive ask)
VEV_5400:      SELL 16    x200 (SEED bid-hit),  SELL 18 x50 (passive ask)
VEV_5500:      SELL 6     x200 (SEED bid-hit),  SELL 7  x50 (passive ask)
VELVETFRUIT_EXTRACT: (idle guard active at pos=0, net_delta=0)
```

After first 5 ticks, bid-hits stop. Only passive asks continue through the entry window. If asks never fill (likely — voucher flow is bid-side only), we hold seed positions to round end.

**No cover orders are ever generated.**

## Key risk

VELVET could rip up. If S moves +3σ (>50 ticks to 5320) in the round:
- K=5300 short 100 × intrinsic 20 = −$2,000 (vs received $5,200 at seed → net +$3,200)
- K=5400 short 200 × 0 = 0 (still OTM)
- K=5500 short 200 × 0 = 0 (still OTM)

Even under 3σ move, net PnL is positive. The strategy has **structural positive EV** as long as VELVET stays below 5400 (which it did in every historical day and sub 381248).

## To ship

1. Submit `outputs/submissions/submission_r3_v5_hold.py` (69KB, 988 tests pass)
2. Observe voucher PnL in result:
   - If ≈ +$9K+ total: platform marks at intrinsic. Double down next submission (increase seed caps to 300 each).
   - If ≈ +$3–6K: marks at BSM fair. Stay the course.
   - If ≈ +$500–1,500: marks at end-mid. Shift back to pure MM; short-premium is marginal.
   - If ≈ $0 or negative: something else wrong — investigate logs.
