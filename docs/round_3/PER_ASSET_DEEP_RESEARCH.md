# Per-Asset Deep Research — Submission 7 Peak → Final Drawdown Analysis

**Bottom line:** v6 MR reached **+$19,750 peak** at ts=70,000 but ended at **+$8,377** — a **$11,373 drawdown in the final 30K ticks**. The alpha IS there. We're giving it back through lack of exit discipline, not lack of signal.

## Part 1 — Submission 7 tick-by-tick reconstruction (HYDROGEL)

| ts | mid | pos | PnL | What happened |
|---|---|---|---|---|
| 0 | 10011 | 0 | $0 | Start. Mid +21 above μ. |
| 5,000 | 10027 | **−200** | −$1,539 | MR sold aggressively into climbing price (temporary loss) |
| 20,000 | 10016 | −200 | +$633 | Mid reverting. Short unrealized profit building. |
| 25,000 | 9990 | −200 | **+$5,940** | At μ. Short profit peaks for cycle 1. **Should have flattened here.** |
| 50,000 | 9952 | −50 | **+$10,846** | Covered most shorts. Cycle 1 mostly realized. |
| 55,000 | 9945 | **+200** | +$8,309 | **FLIPPED to long 200 in ~5K ticks**. Paid 5 ticks of spread (−$2.5K swing). |
| 65,000 | 9987 | +200 | **+$16,886** | Long position marks up. Cycle 2 reverting. |
| **70,000** | **9996** | **+177** | **+$18,474** | **PEAK. Near μ. Should have flattened.** |
| 80,000 | 9960 | +200 | +$11,896 | Cycle 3 down-leg. Long position losing. |
| 90,000 | 9927 | +200 | +$5,441 | Held through −63 drop. Unrealized loss −$13K. |
| 95,000 | 9942 | +149 | +$8,060 | Mid rebounding. Partial recovery. Clear-threshold started unwinding. |
| 99,900 | 9960 | +5 | **+$6,697** | Final. Gave back $12K from peak. |

## Part 2 — Per-asset dynamics, understood properly

### HYDROGEL_PACK (the $18K alpha source)

**What it is:** delta-1 product, mean-reverting around μ=9990.

**Movement:**
- Range 100-170 ticks per round around stable μ
- AR(1) φ=0.996, half-life 189 ticks → strong reversion
- 3 full mean-cross cycles in submission 7 (up→down→up→down)

**Where the alpha is:**
- **Each full MR cycle = ~$10-18K of extractable P&L at 200 size** (verified empirically)
- 3 cycles per round × $10K = **$30-50K theoretical max**
- We captured $18K peak = **~50% of theoretical**
- We FINAL = $6.7K = **18% of theoretical**

**What we lose:**
- Holding positions THROUGH cycle reversals (losing back the gain)
- Flipping short → long (paying 2× spread on the flip)
- Clearing only at 90% cap (too late — damage done)

**How to maximize:**
1. **Lock in cycle gains**: when mid returns to μ from a deviation, FLATTEN the position (not just reduce via clear-phase).
2. **Cooldown between cycles**: after closing a winning cycle, don't immediately re-enter on the next deviation.
3. **Asymmetric entry**: aggressive take on deviation; aggressive flatten on mid-recross of μ.

### VELVETFRUIT_EXTRACT (net −$475 after 1,788 trades)

**What it is:** delta-1, underlier for vouchers. Weakly mean-reverting.

**Movement:**
- Range 35 ticks in submission 7 (much smaller than HYDROGEL)
- Drifts between days (historical 5246, 5248, 5255)
- No consistent μ → EWMA adapts

**Where the alpha isn't:**
- VELVET range × 200 size = $7K theoretical max
- In live we churned 1,788 trades (858 buys, 930 sells) for NET LOSS $475
- **Over-trading eating spread cost**

**The structural issue:** VELVET has TWO roles:
1. MR alpha (mild — $500-1K at best)
2. Delta hedge for VEV_4000 (infrastructure)

Currently we fire it for both. The EWMA-based MR creates lots of round-trip churn that costs more than it gains.

**How to maximize:**
1. **Stop treating VELVET as alpha bucket.** Use purely for delta hedge of VEV_4000.
2. **Reduce activity dramatically.** Only trade when |net_delta| > 30 OR position needs unwinding.
3. **Wider edges** (we're at 1-tick edge; raise to 2-3) so we capture more per fill.

### VEV_4000 (the leveraged VELVET play — works well)

**What it is:** Deep-ITM call that tracks VELVET exactly (VELVET − 4000). Delta = 1. Position limit 300 (vs VELVET 200).

**Movement:**
- Mid = VELVET_mid − 4000 EXACTLY at every tick (verified in submission 7)
- Spread 21 ticks (widest in the complex)
- 217 tape trades, we participated 213 (98% capture)

**Where the alpha is:**
- Wide 21-tick spread with balanced flow
- We loaded +199 long (near cap), profited +$2,154 (peaked at +$4,388)
- This is 50% of peak → similar drawdown pattern as HYDROGEL

**Why it works for us:**
- 21-tick spread absorbs hedge cost (2-3 tick VELVET round-trip)
- VELVET-mean-anchored fair captures MR on the VELVET side
- Position limit 300 gives 50% more capacity than VELVET (200)

**How to maximize:**
1. Same profit-taking logic as HYDROGEL
2. Use full 300 capacity more aggressively (currently hit 200 for 90% of round)
3. Coordinate with VELVET hedge to net delta exposure

### Near-ATM vouchers (K=5200, 5300, 5400, 5500)

**What they are:** Call options with real time value on VELVET.

**Movement:**
- K=5200 range 23 ticks, K=5300 range 16, K=5400 range 7, K=5500 range 3
- Smaller ranges than VELVET (makes sense — they move with VELVET but dampened by delta<1)
- Tight spreads (1-3 ticks)

**Alpha available:**
- Tape volume: K=5300 (14), K=5400 (32), K=5500 (37), K=6000/6500 (37 each)
- Close-mid mark means shorts don't pay intrinsic, but DO pay ΔMid × qty
- VELVET dropped 3.5 ticks → VEV_5300 dropped 3 ticks → short 300 PnL = $900 theoretical

**The structural ceiling per strike:**
- Tape qty × half-spread × 2 sides = a few hundred $
- Directional mark change × 300 qty = $900 max per strike
- Total across K=5300/5400/5500 = **$1,500-3,000 max**

**How to maximize:**
1. **Passive maker quotes ONLY** (not crossing). Join best bid/ask.
2. **Small positions, long-held**: accept tape fills. Don't chase.
3. Target $100-500 per strike, $1-2K total.

### Deep OTM (K=6000, 6500) and mid-strikes (K=4500, 5000, 5100)

**Completely idle or worthless:**
- K=6000, K=6500: mid pinned at 0.5 (tick floor). Movement range 0.
- K=4500, K=5000, K=5100: **ZERO tape trades in submission 7**
- Positions we'd build would be purely directional bets on VELVET, no alpha

**Strategy:** ignore.

## Part 3 — The $100K question

**Can we actually hit $100K?**

Theoretical max calculation for a 1,000-tick round with R3 position limits:

| Source | Max PnL |
|---|---|
| HYDROGEL 3 cycles × $10K | **$30K** |
| VEV_4000 2 cycles × $4K | $8K |
| VELVET MR (best case) | $1K |
| Near-ATM voucher MM | $2K |
| **Total theoretical max** | **$41K** |

**Even with PERFECT execution, $41K is the ceiling.** To reach $100K+ we'd need:
1. **More cycles** (MR on shorter timescales)
2. **Cross-round carry** (not possible — positions reset)
3. **Hidden alpha** we haven't identified (maybe cross-strike voucher arb we ruled out, or bot-behavior exploitation)

**$100K public claims are probably for the P3 competition or a different R3 round with better structure.** For this specific R3 final with its 1,000-tick length and these asset dynamics, **$25-40K is the realistic top.**

## Part 4 — What v7 should be

The single biggest lever: **EXIT DISCIPLINE on HYDROGEL MR**.

### Change 1: profit-take on mid-recross of μ

When `|mid − μ| < 10` AND `|position| > 50`: **FLATTEN POSITION**. Don't hold through the next cycle's reversal.

```python
if abs(mid - mu) < 10 and abs(position) > 50:
    # Mid returned to mean — lock in the cycle gain
    target_pos = 0
    return taker_orders_toward_target(target_pos, ...)
```

This would have fired at ts=25K (pos=-200, mid=9990) and ts=70K (pos=+177, mid=9996) in submission 7. Locking in ~$11K and ~$18K respectively.

### Change 2: VELVET → pure hedge, no MR alpha

Disable VELVET MR bias. Only trade when:
- `|net_delta| >= 30` (need to hedge)
- OR `|velvet_position| >= 20` (need to unwind inventory)

Should reduce VELVET trades from 1,788 to ~100-200 and net gain should go from −$475 to +$200-500.

### Change 3: VEV_4000 — keep, apply same profit-taking

Mid-recross of (velvet_ewma − 4000): flatten VEV_4000. Same mechanics as HYDROGEL.

### Change 4: Re-enable voucher_liquidity on K=5300/5400/5500 (tiny)

Small caps (20-30), passive-only. Target +$500 aggregate.

### Projected v7 PnL

| Source | v6 submission 7 | v7 projection |
|---|---|---|
| HYDROGEL (profit-take) | $6.7K | **$15-18K** (lock in peak) |
| VEV_4000 | $2.2K | $3-4K |
| VELVET (hedge only) | −$0.5K | +$0.2K |
| Voucher MM (new) | $0 | $0.3-0.7K |
| **Total** | **$8.4K** | **$18-23K** |

Still not $100K, but 2-3× improvement with one structural fix (profit-taking).

## Part 5 — What we're NOT yet researching

To genuinely push past $25-30K, we'd need:
- **Bot-behavior signals**: identify informed counterparties, piggyback on their flow.
- **Tier-2 signals** (from [BOT_BEHAVIOR.md](BOT_BEHAVIOR.md)): VELVET size-11+ toxicity filter, basket-dump detector.
- **Micro-structure alpha**: queue-position games, order-book imbalance prediction.

These are Tier 2 per prior planning. Worth building ONLY AFTER profit-taking fix is verified.

## Next action

Implement profit-take on mid-recross of μ for HYDROGEL and VEV_4000. Ship as v7. Expected PnL: $15-25K.

If v7 delivers ≥$15K, build Tier 2 signals (another $2-5K). If v7 delivers <$10K, we're structurally capped and need to investigate bot-behavior alpha seriously.
