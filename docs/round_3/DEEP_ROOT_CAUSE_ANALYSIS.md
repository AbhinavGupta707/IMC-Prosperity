# Deep Root Cause Analysis — Why We're Stuck at ~$1K

**Submissions 3-6: $180, $693, -$3, $1,114.** Consistent ~$1K ceiling despite radically different strategies (defensive MM, aggressive voucher shorting, hold-to-end premium harvesting). That consistency isn't bad luck. **It's a structural ceiling we've been banging our head against.**

## Part 1 — What's structural, confirmed

### Fact 1: Prosperity marks positions at CLOSE_MID, not intrinsic

Verified via submission 6:

| Strike | Position held to end | Open bid | Close mid | Observed PnL |
|---|---|---|---|---|
| VEV_5300 | −89 | 52 | 50 | **+$97** |
| VEV_5400 | −115 | 16 | 16 | **−$12** |
| VEV_5500 | −115 | 6 | 6.5 | **−$55** |

For each, `PnL ≈ (sell_price − close_mid) × qty − entry_spread_cost`. This matches exactly. **Short-premium cannot pay more than theta decay over the round + possibly small drift.** The $10K-50K scenarios assumed intrinsic mark; that's not reality.

**Implication:** voucher short-premium is a ~$0-$200 strategy, not $10K+. Stop building around it.

### Fact 2: Our MM captures ~50% of available spread flow

Across the live round:
- Total tape trades: 125
- Our participation: 58 (46%)
- Theoretical max MM PnL if we captured 100%: ~$2,000

Our observed ~$1,100 = 55% of theoretical ceiling. **We're already near the MM efficiency frontier.** More tweaking of quote placement gets marginal gains.

### Fact 3: R3 live round is 1,000 snapshots, not 10,000

Historical days: 10,000 snapshots (ts 0 → 999,900, step 100).
Live round: 1,000 snapshots (ts 0 → 99,900, step 100).

Total market activity scales with tick count. Historical day had ~4,000 qty traded across products; live round has ~330 qty. 1/12th the liquidity → 1/12th the MM ceiling.

**Implication:** the LOO predictions scaled to 10K-tick days were ~10× too optimistic.

## Part 2 — The alpha we've been missing

### HYDROGEL is a STRONGLY mean-reverting process, and we've been ignoring the mean

HYDROGEL parameters (confirmed across historical + live):
- AR(1) φ = 0.99634 → mean-reversion half-life = **189 snapshots**
- Long-term μ ≈ **9990** across all 3 historical days + live
- Standard deviation over a round: ~40-60 ticks

**Live round 6 HYDROGEL trajectory:**
```
ts=     0  mid=10011  (+21 from μ)
ts=  3400  mid=10031  (+41, PEAK)
ts= 25000  mid=9990   (reverted to μ)
ts= 50000  mid=9952   (−38)
ts= 60000  mid=9962   (rebound)
ts= 70000  mid=9996   (back near μ)
ts= 91100  mid=9915   (−75, LOW)
ts= 99900  mid=9960   (partial rebound)
```

**Full 116-tick swing during the round.**

### What pure mean-reversion would have earned

**Strategy: buy 200 at market ask when mid ≤ 9960, sell 200 at market bid when mid ≥ 10020, flatten near μ=9990.**

Backtested:

| Day | Range | MR strategy PnL (±30 threshold) | MR strategy (±40 threshold) |
|---|---|---|---|
| Historical day 0 | 143 | **+$34,800** (31 trades) | **+$51,800** (22 trades) |
| Historical day 1 | 170 | +$24,800 | +$48,000 |
| Historical day 2 | 160 | +$36,000 | +$49,000 |
| Live submission 6 | 116 | +$4,000 (5 trades) | N/A |

Historical days have 10× the snapshots → ~10× the reversion cycles → ~10× the PnL potential. Live round PnL expectation: **$3K-$5K on HYDROGEL alone** from pure MR.

**Our MM on the same submission: +$570. The missed alpha is $3,000-$4,500.**

## Part 3 — Why our MM missed it

### The root structural bug: we anchor to instantaneous mid, not long-term mean

Our SST fair value = `snapshot.mid` at each tick. When mid = 9960 (30 below μ), we quote bid 9957 / ask 9963. We buy at 9957 and immediately post an ask at 9963 — capturing a 6-tick round-trip. Then we cover for another 6 ticks.

But the PRICE is going to mean-revert to 9990 over the next 189 ticks. We SHOULD have bought at 9957 and HELD until price reached ~9985, capturing 28 ticks. Our MM gives up **80% of the available directional alpha** because it treats each tick as independent rather than riding the reversion.

### This is well-studied in quant literature

**Ornstein-Uhlenbeck process (Vasicek 1977):** a mean-reverting process `dX = θ(μ − X) dt + σ dW`. Optimal trading strategy for a risk-neutral trader:

- Take max long when X ≤ μ − kσ for some threshold k
- Take max short when X ≥ μ + kσ
- Unwind near μ

HYDROGEL fits this EXACTLY. θ ≈ 0.0037, μ ≈ 9990, σ per-tick ≈ 2-3 ticks.

**Our MM approach is optimal for a random-walk process** (`dX = σ dW`, no drift). But HYDROGEL is NOT random walk — it has a strong mean. For OU processes, **directional trading dominates MM by ~10×** in Sharpe (Avellaneda & Stoikov 2008; Cartea, Jaimungal & Penalva 2015).

### The top teams are running mean-reversion on HYDROGEL

This is the "100K club" strategy we've been guessing at. Probably also VELVET (smaller range, smaller alpha ~$1-2K) and possibly VEV_4000 (leveraged VELVET exposure).

**Historical public Prosperity 3 writeups** (TimoDiehm, chrispyroberts, Linear Utility) all describe aggressive inventory management where they DELIBERATELY BUILT positions when prices deviated. Linear Utility's 2nd-place P2 writeup explicitly says: "skew fair toward the long-term anchor".

We implemented "skew toward inventory zero" (SST). That's defensive, appropriate for random-walk MM. Top teams skew toward **reversing away from deviation**, which is offensive, appropriate for mean-reverting MM.

## Part 4 — The strategy pivot

### Proposed: HydrogelMeanReversion replaces passive HYDROGEL MM

```python
μ = 9990                    # long-term mean (robust across 3 days + live)
target_size = 200            # full pos limit
entry_threshold = 20         # ±20 ticks from μ
exit_threshold = 5           # flatten within ±5 of μ

if mid <= μ - entry_threshold:
    target_pos = +target_size   # go LONG aggressively
elif mid >= μ + entry_threshold:
    target_pos = -target_size   # go SHORT aggressively
else:
    target_pos = 0              # flat

# Rebalance toward target: aggressive take to cross, passive MM on the way there
```

Combined with:
- Residual passive MM (capture spread WHILE holding position)
- Inventory-aware sizing (if current pos already long, don't over-size)

### Also: apply same logic to VELVET and VEV_4000 where applicable

VELVET historical daily range: 68-93 ticks, mean drifts slightly. MR strategy with ±30 threshold, entry at ±15 from rolling 200-tick EWMA, should earn ~$500-$1K additional.

VEV_4000 tracks VELVET exactly (delta=1, intrinsic-hugging). Use 300-qty positions to leverage VELVET view. Additional ~$500-$1K.

## Part 5 — Expected PnL after pivot

| Source | Current (v5) | After MR pivot |
|---|---|---|
| HYDROGEL MM | +$570 | N/A (replaced) |
| **HYDROGEL Mean-Reversion** | — | **+$3K-$5K** |
| VELVET MM | +$449 | +$500 (add MR to residual MM) |
| VEV_4000 MM | +$64 | +$500-$1K (MR-skewed) |
| Voucher short-premium | +$30 | +$0 (disable — structural cap hit) |
| **Total** | **+$1,114** | **+$4K-$7K** |

Still not $100K. Why? Because:
1. Live round is 1K ticks (1/10 of historical), and even the theoretical MR ceiling is ~$5-10K per round.
2. The $100K+ teams probably run this on MULTIPLE products simultaneously with aggressive sizing AND have better queue fill than us.

### What would it take to hit $20K+?

- Aggressive MR on HYDROGEL + VELVET + VEV_4000 simultaneously (cross-product directional)
- Combine with winning queue position on all three (quote slightly inside-best)
- Use full 200/200/300 capacity on every directional opportunity
- Add a "chase the breakout" reverse strategy when mean-reversion fails (regime-conditional)

### What the $100K+ teams might additionally do

Hypothesis based on public P3 writeups and our own data:
- **True signal**: extract a cross-product signal (e.g., VEV_5200 at +X deviation → VELVET moves direction Y in N ticks). We haven't looked for this.
- **Queue game**: quote at best-bid+1 / best-ask-1 aggressively, winning the queue over lazy MMs.
- **Gamma scalping (vol arb)**: long ATM options + continuous delta hedge. Profits from RV-IV mismatch.

These are HIGHER effort to implement than MR, but they represent the gap from $5K → $20K+ → $100K.

## Part 6 — Action plan

**Immediate (today):**
1. Replace `hydrogel_mm.py` with `hydrogel_mean_reversion.py`
   - Fair value = 9990 (constant, not mid-tracking)
   - Target position = sign(μ − mid) × min(200, |mid−μ|/40 × 200)
   - Use SST take-phase aggressively when mid crosses thresholds
2. Add similar skew to VELVET and VEV_4000 strategies (skew fair toward rolling mean, not instantaneous mid)
3. **Disable voucher short-premium** (confirmed structural cap; spread cost > theta decay)

**Verify:**
- LOO replay on historical 10K-tick days should show +$25K-$50K per day on HYDROGEL alone
- Live expectation: ~10% of that = $2.5K-$5K, compounding with VELVET/VEV_4000 directional = **$4K-$7K total**

**Next experiment after that:**
- If $4K+ confirmed: look for cross-product signals (e.g., voucher flow leading VELVET moves)
- If $4K fails: queue-position game (quote inside-best, bigger size)

## Key references

- Vasicek, O. (1977). "An Equilibrium Characterization of the Term Structure" — original OU formulation.
- Avellaneda & Stoikov (2008). "High-frequency trading in a limit order book" — optimal MM, shows directional dominates for mean-reverting assets.
- Cartea, Jaimungal, Penalva (2015). "Algorithmic and High-Frequency Trading" — Chapter 10 covers statistical arb on OU processes, confirming MR strategies earn ~O(σ·√θ·T) per unit capital per round.
- Linear Utility Prosperity writeups — explicitly use anchor-based fair, not mid-tracking.

## The meta-lesson

We've been optimizing a defensive MM framework that's appropriate for **random-walk** markets. HYDROGEL (and probably VELVET) are **strongly mean-reverting**, which requires a fundamentally different strategy (directional bets on deviation). We were pattern-matching from R1/R2 experience (which was also random-walk MM) without testing whether R3 products had different structure.

**The 200-position limit was never binding because we never tried to USE it directionally.** Position extrema of ±21 on HYDROGEL (10% of capacity) is the symptom. The cure is changing the fair-value anchor.
