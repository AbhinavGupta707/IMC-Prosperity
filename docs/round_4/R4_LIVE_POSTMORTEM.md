# R4 Live Day 4 Post-mortem — What We Got, What We Missed

Date: 2026-04-28

## Headline numbers

- Final live D4 PnL: **143,528**
- Top scorers: 200k+ (gap of ~$60k+)
- Submitted: `submission_r4_final_probe_stack_hyd_abortgate18_long80_60.py`
- Peak intraday PnL: **+171,781 at ts=400,000**
- Trough after peak: 91,068 at ts=625,000 (peak-to-trough drawdown ≈ -$80,000)

## What was the actual day-4 regime?

**Decisively bearish across all option strikes.** Every product closed lower than it opened:

| Product | Open | Close | Δ | Range (peak-trough) | Vol stdev |
|---|---:|---:|---:|---:|---:|
| HYDROGEL_PACK | 10000.0 | 10001.0 | +1.0 | **180.5** ticks | 2.20 |
| VELVETFRUIT_EXTRACT | 5232.5 | 5223.5 | -9.0 | 96.5 | 1.13 |
| VEV_4000 | 1233.0 | 1223.5 | -9.5 | 99.5 | 1.46 |
| VEV_4500 | 733.0 | 723.5 | -9.5 | 99.0 | 1.27 |
| VEV_5000 | 235.0 | 225.0 | -10.0 | 93.5 | 1.00 |
| VEV_5100 | 142.0 | 130.0 | -12.0 | 85.5 | 0.89 |
| VEV_5200 | 70.0 | 57.0 | -13.0 | 63.5 | 0.66 |
| VEV_5300 | 26.5 | 17.5 | -9.0 | 35.5 | 0.39 |
| VEV_5400 | 5.5 | 2.5 | -3.0 | 11.5 | 0.20 |
| VEV_5500 | 1.5 | 0.5 | -1.0 | 3.0 | 0.08 |
| VEV_6000/6500 | 0.5 | 0.5 | 0 | 0 | 0 |

**Two critical regime features:**
1. HYD had a 180-tick swing — by far the most volatile of any historical day. Peak 10061 at ts=435,400, trough 9880.5 at ts=651,400.
2. Every voucher CLOSED lower than open. Pure-bearish day for the option complex.

## Mark 22's NEW behavior — expanded basket including ITM strikes

Historical pattern: Mark 22 sells only deep OTM (5300+). Live D4 expanded:

| Strike | Mark 22 sells (count) | Mark 22 qty | Avg price | Historical pattern |
|---|---:|---:|---:|---|
| VEV_6500 | 116 | 415 | 0.00 | matches |
| VEV_6000 | 116 | 415 | 0.00 | matches |
| VEV_5500 | 115 | 411 | 0.54 | matches |
| VEV_5400 | 109 | 389 | 4.12 | matches |
| VEV_5300 | 75 | 264 | 22.92 | matches |
| **VEV_5200** | **44** | **164** | **64.14** | **NEW (more aggressive)** |
| **VELVET** | **39** | **269** | **5236.02** | **NEW (heavier)** |
| **VEV_4000** | **4** | **15** | **1224.33** | **NEW** |
| **VEV_4500** | **3** | **11** | **725.55** | **NEW** |
| **VEV_5000** | **1** | **4** | **240.00** | **NEW** |
| **HYDROGEL_PACK** | **5** | **22** | **9974.14** | **NEW (rare)** |

**This was a strong bearish signal.** Mark 22 selling ITM strikes that historically it never touched = the systematic short program is anticipating a broader down move.

We didn't pivot off this signal. Our base strategy kept buying ITM/ATM longs at fixed thresholds.

## Where we made money vs where we lost it

**Per-unit realized profit (avg sell - avg buy) tells the trade quality:**

| Product | Avg buy | Avg sell | Qty traded | Per-unit | Total realized |
|---|---:|---:|---:|---:|---:|
| HYDROGEL_PACK | 9974.0 | 10026.4 | 1085 | **+52.4** | $56,870 ✓ |
| VEV_4500 | 729.6 | 753.0 | 812 | +23.4 | $19,000 |
| VEV_5000 | 238.6 | 260.2 | 900 | +21.6 | $19,440 |
| VEV_4000 | 1230.9 | 1247.7 | 726 | +16.8 | $12,177 |
| VELVET | 5241.3 | 5257.5 | 600 | +16.2 | $9,720 |
| VEV_5100 | 158.2 | 173.8 | 1500 | +15.6 | $23,400 |
| VEV_5200 | 85.3 | 92.1 | 1025 | +6.8 | $6,941 |
| **VEV_5300** | **27.2** | **17.8** | **300** | **-9.4** | **-$2,820** |
| **VEV_5400** | **6.0** | **2.0** | **300** | **-4.0** | **-$1,200** |

**The sleeves where we lost money were exactly the products where Mark 22 was most aggressively selling.** We bought VEV_5300 at avg 27.2 (near top of its 13.5-49 range), then prices crashed to 17.5 close. Same for VEV_5400.

## What top scorers likely did differently

### 1. Pure-short voucher basket from open (~$13-22k missed alpha)

Simply going short 300 on every voucher at open and holding to EOD:

| Product | Δ × 300 short | 
|---|---:|
| VEV_5500 | +300 |
| VEV_5400 | +900 |
| VEV_5300 | +2,700 |
| VEV_5200 | +3,900 |
| VEV_5100 | +3,600 |
| VEV_5000 | +3,000 |
| VEV_4500 | +2,850 |
| VEV_4000 | +2,850 |
| VELVET | +1,800 |
| **Total static short** | **+21,900** |

We had VEV_5500/6000/6500 effectively **untraded** (sell threshold at 7+ never triggered in the 0-3 mid range). A short-from-open on VEV_5500 alone was a free $300. Mark 22 was selling them all day at avg 0.54; we could have joined.

### 2. HYD swing capture (~$30k+ missed alpha)

HYD swung 180 ticks. Best static hold options:
- Long 200 from trough (9880) to peak (10061): **+$36,100**
- Even capturing half this range: +$18k

We earned $56,870 on HYD which is ~~good~~. But could have been **$80-100k** with active swing capture.

### 3. VELVET wider trading band (~$10-15k missed alpha)

Our schedule had buy at 5247, sell at 5264 (17-tick band). Live VELVET hit:
- Trough: **5196** (51 ticks BELOW our buy threshold)
- Peak: **5292** (28 ticks ABOVE our sell threshold)

If we'd had a wider buy band (e.g., buy below 5240 with size scaling), we'd have caught the 5196 trough and made an extra ~$10-15k.

### 4. Multi-tier scale-in/out by absolute deviation (~$10-20k)

Our strategy uses fixed thresholds. A SCALE strategy:
- Buy 100 at threshold
- Buy +100 at threshold-10
- Buy +100 at threshold-25 (scale into the falling knife)
- Sell back as price recovers

Would have captured the V-shape recovery on multiple products.

### 5. Mark 22 expanded basket as a CONFIRMED bearish signal

When Mark 22 starts hitting ITM strikes (VEV_4000/4500), that's an outlier event. We'd expect it to predict broader VELVET decline (which happened). **A regime-adapter trader would have reduced longs on observation, or even flipped short.**

We never built such an adapter. The Mark research focused on Mark 38 fade, Mark 22 OTM (which we already-passively-traded), Mark 67 sequence — none of which would have caught this.

## Our peak-to-final drawdown analysis

PnL trajectory (Kevin BT-anchored interpretation):

| Window | Δ PnL | What was happening |
|---|---:|---|
| 0–50k | +3,018 | warmup |
| 50k–200k | **+78,516** | strong ramp — capturing initial down-moves |
| 200k–400k | **+90,247** | continued ramp, HYD trending up, vouchers stable |
| **400k–500k** | **-43,189** | **vouchers crashed; HYD reversed; we got whipsawed** |
| 500k–700k | +14,605 | recovery |
| 700k–800k | -38,090 | another whipsaw |
| 800k–900k | +59,442 | strong recovery |
| 900k–end | -20,061 | **final flatten gave back accumulated marks** |

**The biggest leak**: in the 400k-450k window we lost -$52,691 because:
- Held +300 long on every voucher (5300/5400 at peak)
- Held -200 short on HYD as it trended UP +20 ticks
- Vouchers crashed -30+ ticks each in 5k ticks
- All position-sized losses materialized simultaneously

Then at 700k-750k (-$40,960) and 800k+ another swing. **We were path-dependent.**

## What would Mark 38 fade have done?

Mark 38 HYD trades on Live D4: 683 buys + 697 sells. Roughly the same volume as historical. With pos<=0 gate:
- During 25k-70k window: pos was positive (+17 to +44). **Fade gate skipped most events.**
- 100k onwards: pos hit -200 limit several times. **Fade gate fires but no capacity to sell more.**
- Mid-day: pos swung wildly +200 to -200 multiple times. Fade fires when pos≤0 → some captured.

**Best estimate: Mark 38 fade contribution on Live D4: -$200 to +$300, near zero.** Confirms it would not have helped meaningfully. Conservative choice was correct.

## What we missed: structural strategy gaps

### A. No volatility / momentum regime adapter

Our base strategy is **fixed-threshold market-making**. Live D4 had volatility 2-3x historical day 3 across most products. We needed:
1. Detection of volatility expansion (e.g., 30-tick mid move in 10k ticks).
2. Switching from "fade" to "follow" when volatility breaks out.

### B. No symmetric short-bias for vouchers

We have `VEV_5500 sell at 7+` but no aggressive shorting on other strikes. The 5400/5500/6000/6500 strikes were never properly utilized for downside capture.

### C. No cross-strike correlation gate

When ALL vouchers move together (cross-strike correlation), it's a regime shift. We have no such detection. Our products operate in isolation.

### D. No Mark 22 basket-aggression detector

Mark 22 selling ITM strikes is qualitatively new. We have no rule that says "if Mark 22 sells VEV_4000/4500/5000 → strong bearish signal → reduce all OTM longs". Our prior research dismissed Mark 22 as "pegged structural" — we missed that the basket COMPOSITION carries information beyond price discovery.

### E. Position-flatten mid-day vs end-of-day decision

We ended at flat on every product. Top scorers may have:
- Held strategic short positions through close (vouchers all expired LOWER)
- Or aggressively flattened earlier when volatility was high

### F. No HYD swing trader

HYD's 180-tick range was the single biggest alpha source. Our HYD logic captured it OK ($56k), but a dedicated swing trader (buy at +/-30 from open mid, take profits) could have captured $80-100k.

## What the gap to top scorers (200k+) most likely consists of

| Category | Estimated missed alpha |
|---|---:|
| Static short voucher basket | $15-20k |
| HYD swing capture (better timing) | $20-40k |
| VELVET wider band | $10-15k |
| Mark 22 ITM basket flip → bearish trigger | $10-15k |
| Voucher cross-strike correlation hedging | $5-10k |
| **Total potential gap** | **$60-100k** |

This is consistent with a 200k+ top score (us at 143k + 60k of these strategies).

## Critical takeaways for next round

1. **REGIME ADAPTERS ARE THE ALPHA, not Mark IDs.** We spent enormous effort on Mark fade analysis. The big alpha was simpler: detect when the day is trending and follow it.

2. **STATIC SHORT IS A DEFENSIBLE POSITION** when prices are clearly bearish. We had no static-short logic in vouchers. Top scorers probably had at minimum a "sell-and-hold" position on the deep OTM strikes alongside Mark 22.

3. **VOLATILITY EXPANSION NEEDS DETECTION.** Live D4 volatility was 2-3x historical day 3 on most products. Our schedule didn't recognize this and continued trading the same band.

4. **CROSS-PRODUCT CORRELATION SIGNALS REGIME SHIFTS.** When all vouchers drop together, it's a different regime than when only one drops. We need composite signals, not per-product schedules.

5. **MARK 22 BASKET COMPOSITION CARRIES INFORMATION.** Beyond just "Mark 22 sold OTM," the SET of strikes Mark 22 hits matters. Live D4: extension to ITM = bearish. Future: build a basket-composition state variable.

6. **PEAK-TO-FINAL DRAWDOWN OF 28k IS BAD POSITIONING.** We hit $171k peak. We finished at $143k. That $28k giveback is a positioning failure, not a market failure. Strategies that flatten near peaks (or hold longer) would preserve more.

7. **SCHEDULE-BASED STRATEGIES HAVE FAT LEFT TAILS.** When the regime shifts, schedules buy into falling knives. Either:
   - Add stop-loss / position-reduction logic
   - Or add momentum overlay that turns off the schedule on breakouts

8. **WIDER LIMIT BANDS** would have captured the VELVET 96-tick range. Don't tune buy/sell bands so tight that 50%+ of the live range falls outside them.

## Specific concrete suggestions for next round

### S1: Volatility-expansion detector

Track mid-price changes per 5k window. If any product's |Δmid| > N × historical_avg, flip from market-making to trend-following.

### S2: Static short basket on deep OTM

VEV_5500/5400/6000/6500 are systematically declining strikes. Maintain a -200 short position throughout the day. Worst case: -$1,500 if prices stable; usual case: +$1,000-3,000.

### S3: Mark 22 basket aggression detector

Track the *set* of products in each Mark 22 basket. If basket includes ITM (VEV_4000/4500/5000), it's a regime signal. Trigger: reduce all long voucher exposure by 50%.

### S4: HYD swing trader

Independent of the regime gate, build a HYD trader that:
- Buy 100 below open_mid - 30
- Sell 100 above open_mid + 30
- Accumulate up to position limit, scale out as price moves favorably

### S5: Wider VELVET schedule with scaling

Replace fixed band with: buy 50 at mid-10, buy +50 at mid-20, buy +100 at mid-35. Same on sell side.

### S6: Drawdown-triggered de-risking

If realized PnL drops $20k+ in 50k ticks, halve all open positions and pause re-entry for 25k ticks.

These are all REGIME-AGNOSTIC structural improvements that would have benefited Live D4 AND historical days.
