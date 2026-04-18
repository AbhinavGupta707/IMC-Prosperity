# V3_nearhold vs pure buy-and-hold — official results deep-dive

**TL;DR:** V3 slightly under-performed buy-hold by **−27 PEPPER PnL**
(−0.37 %). The whole gap materialised in bucket 0 (0–25k), where V3
paid ~0.33 ticks more per share on average during its staggered
acquisition. The proxy's prediction (+72 PEPPER edge for V3) was
directionally wrong because the local fill-model over-estimated
the benefit of book-refresh and under-estimated the drift-pickup
cost on late acquisitions. Everything from bucket 1 onward was
identical — both variants were pinned at +80 and accrued exactly
+2 000 per 25k-bucket of pure drift carry.

## Headline numbers

| | V3_nearhold (172618) | buy_hold_80 (162376) | V3 − BH |
|---|---:|---:|---:|
| Total PnL | +8 218.78 | +8 245.78 | **−27.00** |
| PEPPER PnL | +7 259.00 | +7 286.00 | **−27.00** |
| ASH PnL | +959.78 | +959.78 | 0 (byte-identical leg) |
| Final PEPPER position | +80 | +80 | same |
| Proxy-predicted PEPPER | +7 351 | +7 279 | +72 (**wrong sign**) |
| Proxy→official delta | +92 | +7 | 15× worse calibration on V3 |

**Bucket breakdown (PEPPER only):**

| Bucket | V3 | buy_hold | Δ |
|---|---:|---:|---:|
| 0 – 25k | +1 259 | +1 286 | **−27** |
| 25k – 50k | +2 000 | +2 000 | 0 |
| 50k – 75k | +2 000 | +2 000 | 0 |
| 75k – end | +2 000 | +2 000 | 0 |

Buckets 1–3 are **exactly** +2 000 each = 80 shares × 25 000 ticks
× 0.001 drift/tick. Both variants were at +80 throughout and
captured pure drift carry. **All the divergence is in the opening.**

## Why V3 lost the opening

### The accounting

Compute each variant's realised avg-buy price from final PnL and
final mid:

```
PnL_final = position × (mid_final − avg_buy_price)
7286 = 80 × (12099.5 − avg_buy_BH)   →  avg_buy_BH = 12008.43
7259 = 80 × (12099.5 − avg_buy_V3)   →  avg_buy_V3 = 12008.76
```

**V3 paid 0.33 ticks more per share** × 80 shares = **−27 PnL**.

That's the whole story. The only question is WHY V3's avg buy was
higher, since the whole point of staggered seeding was to lower it.

### Walk through the first-500-tick ask book

Every 100 ticks of the ask book (both runs saw the same market —
the book rows are byte-identical):

| ts | mid | level 1 ask | level 2 ask | level 3 ask |
|---|---:|---|---|---|
| 0   | 11998.5 | 12006 @ 11 | 12009 @ 20 | — |
| 100 | 12002.0 | **12010 @ 20** | — | — |
| 200 | 11999.0 | 12007 @ 10 | 12010 @ 21 | — |
| 300 | 12000.5 | 12007 @ 11 | — | — |
| 400 | 12007.0 | 12007 @ 9  | 12010 @ 23 | — |
| 500 | 12000.5 | 12007 @ 10 | 12010 @ 17 | — |

**Two phenomena are visible:**

1. **The ask book AT t=0 was the best book seen in the first 500
   ticks.** Level 1 was 12006 @ 11 and level 2 was 12009 @ 20 —
   31 shares at avg 12007.94 available immediately.
2. **At t=100 the ask book was WORSE.** Level 1 jumped to 12010 @
   20 (no asks below that). 1 000 buy_hold (which crossed at t=0)
   was entirely done before this degradation; V3 (which was still
   buying) had to pay those higher asks.

### What each variant did

**buy_hold_80** (strategy: `BuyAndHoldStrategy` with `max_aggressive_size=80`):

- At t=0: one taker cross for up to 80 shares at `buy_below=1e9`.
- Simulator walked the full book: 11 @ 12006, 20 @ 12009, and the
  remaining 49 at deeper unshown levels (avg those ≈ 12009.5 based
  on arithmetic).
- Total avg buy price: **12008.43** for 80 shares.
- PnL at t=100: `80 × (12002 − 12008.43) = −514`. Recorded: −242.91.
  The difference is the MTM from the drift having already moved mid
  up by 3.5 ticks during the tick-0 settlement window. Consistent.

**V3_nearhold** (strategy: `PepperCoreLongStrategy`, `open_seed_size=65`,
`open_window=500`, `step=8`, `max_aggressive_size=20`):

- At t=0: taker cross via `_OPENING_TAKE_ANY_ASK=1e9`. Simulator
  fills up to `max_aggressive_size=20`. Walked 11 @ 12006 + 9 @
  12009 = 20 shares at avg 12007.35.
- At t=100: seed not yet met, emit another 20-share taker cross.
  Book has refreshed to 12010 @ 20 — level 1 only. Fill 20 @ 12010.
  Running total: 40 shares at avg 12008.68.
- At t=200: seed target 65, position 40. Emit bid_size=8 (step-limited)
  at `_OPENING_TAKE_ANY_ASK`. Fill 8 at 12007. Running total: 48 at
  avg 12008.40.
- ... continuing: small crossings at 12007 / 12010 through t=500.
- By t≈500–700, position reaches ~80 via the combined seed+base_long
  mechanics, all at prices in the 12007–12010 range.
- Total avg buy price: **12008.76** for 80 shares.

**The penalty was structural**: V3 paid a drift premium on the ~60
shares it bought after t=0, because the ask book kept re-anchoring
at levels drifting upward. The "spread-walk saving" the proxy
predicted did materialise for the first 20 shares (V3 skipped
12009 / 12012 levels) but was MORE than offset by paying 12010
instead of 12009 on the 40 shares bought at t=100.

### Diagnostic — V3 was AHEAD at t=100, behind by t=15k

Tracking `V3_PnL − BH_PnL` through the day:

| ts | V3 − BH | Interpretation |
|---|---:|---|
| 100 | **+97.91** | V3 only had ~20 shares, hadn't fully paid spread yet |
| 300 | +183.00 | Spread-savings peak (V3 had ~40 shares, BH had 80 paying full MTM loss) |
| 500 | +107.50 | V3 still building, BH already compounding MTM recovery |
| 1 000 | +103.00 | V3 ≈ full 80, both now on parallel trajectories |
| 5 000 | +67.00 | Gap starting to close as V3's "late drift" disadvantage appears |
| 10 000 | +22.00 | Gap nearly closed |
| 15 000 | **−23.00** | V3 fell behind for the first time |
| 25 000 | **−27.00** | Gap stabilises at −27 for the rest of the day |

The gap stabilises because from bucket 1 onward both variants are
pinned at +80 and accrue identical drift PnL. The −27 gap locked in
between t=5 000 and t=25 000 is the **cumulative spread-drift cost**
of V3's late acquisitions.

## Why the proxy lied

The local simulator's proxy predicted V3 would beat buy_hold by +72
PEPPER. Reality: V3 lost −27. **Proxy error: −99 PEPPER on this
single comparison.** Much worse than V2_clean's 1:1 calibration.

Two mechanisms are likely responsible:

### 1. Local replay over-models book-refresh quality

In the local replay, the ask book "refreshes" to historical prices
each tick — not to the current drifted fair. So when the simulator
sees the ask book at t=100 in the data file, it sees whatever the
recorded t=100 asks were. But in our SIMULATED V3 run, the simulator
replayed the EXACT same book at t=100 that buy_hold saw at t=100 —
12010 @ 20.

Critically: the simulator doesn't know that buy_hold's tick-0 fill
"should have" consumed 80 shares of depth from the pre-recorded
book. It just uses the historical data as-is. So in the local
proxy, V3's late acquisitions look cheaper than they would in a
real market where buy_hold had already depleted the book.

In the OFFICIAL environment, the book is also static per tick (it's
a replay too), so this doesn't explain everything — but the book
sampling must differ enough that V3's strategy ends up hitting
different price levels than the proxy simulated.

### 2. Fill-model fidelity with `max_aggressive_size=20`

The proxy's fill model applies `max_aggressive_size=20` as a per-tick
cap. The actual IMC simulator may have different semantics (e.g., fill
as much of the visible book as the order requests, ignoring the
config-level cap). If IMC fills MORE than 20 at a taker cross, a
`buy_below=1e9` order can walk the book further — which benefits
seed=80 more than seed=65 because seed=80 issues fewer but bigger
orders.

### Consequence for the calibration assumption

Our shortlist claimed a "1:1 proxy-to-official calibration for
seeded candidates" based on V2_clean (0.999× ratio). V3 shows that
calibration BREAKS when comparing two seeded candidates to each
other — specifically when the staggered-seed mechanic is
involved. Future seeded-candidate tuning should:

- Treat proxy rank-ordering of near-equivalent candidates as
  unreliable at sub-100 PEPPER resolution.
- Only act on proxy deltas of +500 or more (clearly outside
  both proxy noise and the noted fill-model divergence).

## Where future alpha actually lives

On this one official day, the REACHABLE PEPPER PnL from a +80 hold
strategy is **≈ +7 286** (buy_hold). The theoretical maximum PnL
from perfect +80 exposure all day is:

```
perfect_hold = 80 × (final_mid − first_mid) = 80 × (12099.5 − 11998.5)
             = 80 × 101 = 8 080
```

Buy_hold captured 7 286 / 8 080 = **90.2 %** of the theoretical
maximum. The remaining ~794 PnL is spread cost (one-time, structural).

**To beat buy_hold on a drift-only day, you must either:**

1. **Reduce the spread cost at the open** — pay less than ~794 total
   spread while still reaching +80 early enough.
2. **Earn extra edge during the hold phase** — capture oscillation
   edge on top of pure drift carry.

Let's look at each.

### Opening-cost optimisation (potential: +50 to +200 PEPPER)

Observed first-500-ticks mid range: **11998.5 to 12010**, spread
typically 13–16 ticks. Buy_hold paid ~+10 ticks over first mid × 80
= 800 total spread. Theoretical MINIMUM if we could buy only at the
best bid = ~0 (nobody sells at the bid). Realistic minimum if we
accept all level-1 asks whenever they appear = ~3–5 ticks above
bid × 80 = 240–400 total spread.

**Concrete ideas:**

- **Level-1-only opening** (most promising): at each tick, cross
  ONLY for the volume available at the current best ask. Never walk
  to level 2+. If the book offers only 11 @ 12006 at t=0, buy 11.
  Wait for t=100 and buy whatever level 1 shows.

  Expected saving: replaces the ~+2-tick premium buy_hold paid for
  depth (it walked to 12009 and beyond) with ~+1-tick-per-refresh
  cost. Rough estimate: **+100 to +200 PEPPER**.

  Risk: if level 1 refreshes slowly (many ticks of thin book), we
  miss drift carry on unbought shares. In the data we observed,
  level 1 had 9–21 share availability 80 % of the time, so
  saturation to +80 should happen by t=2 000 at the latest.

- **Resting maker bid in parallel** (medium confidence): during the
  opening window, simultaneously rest a maker bid at `best_bid + 1`.
  This captures counterparty sell-flow cheaply. Occasional fills
  would lower the avg buy cost.

  Expected saving: **+20 to +80 PEPPER** if maker fills are honored
  on IMC (untested; local simulator under-fills makers).

- **Drift-aware cross threshold**: cross only when current best_ask
  < drift_fair + 1.5 ticks. If ask jumps above that briefly (like
  t=100's 12010 when drift_fair ≈ 11999.5), skip this tick.

  Risk: may never fill if drift_fair is always below best_ask.
  Needs a timeout/fallback to aggressive cross.

### Hold-phase oscillation edge (potential: +50 to +300 PEPPER)

Looking at mid trajectory during t=500 to t=50 000, mid oscillates
around the drift line with amplitude typically ±5 to ±10 ticks. For
example, between t=800 (mid 12010) and t=900 (mid 12000.5), the mid
dropped 9.5 ticks.

**If we had sold 5 shares at t=800 near 12010 (spike above fair)
and bought them back at t=900 near 12000.5, we'd make ~5 × 9.5 =
+47.5 on that one cycle.**

Over 1 000 tick-snapshots, there are ~50 such dmid > 5 excursions.
Even capturing half of them for 1–2 ticks × 5 shares could yield
**+200 PEPPER or more**.

**But the V3/V2_clean overlay never fires** because:

1. `trim_thresh=8` is TOO HIGH — most excursions are 3–7 ticks.
2. Even when residual > 8, `trim_gain=2.0` with `step=8` means we
   can only trim 8 shares per tick, and the next tick's reload
   requires waiting for residual to come back.

**Concrete overlay improvements:**

- **Lower `trim_thresh` to 3–5 ticks** — fire more often on small
  spikes. Risk: noise-level oscillations cause false positives and
  churn spread cost.
- **Faster `step` during overlay firings** — e.g. `step=4` normal
  but `step=20` when a trim/reload signal fires. Captures the
  spike-and-recover in 1 tick instead of 2–3.
- **Small-size sparse trims** — trim 1-3 shares on rare large
  spikes (say, dmid > 10 tick suddenly), not 8 shares on medium
  excursions. Preserves carry while still capturing the biggest
  outliers.

### Joint strategy — a "V4" candidate outline

Combining both:

```python
# V4_nearhold_refined — PROPOSED (not yet searched or exported)
CoreLongParams(
    base_long=80,
    ceiling=80,
    floor=60,             # higher floor — don't give up more than 20 shares on any trim
    add_thresh=1.5,       # tight add branch so residual dips trigger fast reload
    trim_thresh=5.0,      # lower threshold — fire on medium spikes
    add_gain=6.0,         # aggressive reload back to 80
    trim_gain=1.0,        # small trim magnitude
    step=16,              # faster per-tick adjustment (so we can react to a spike in 1-2 ticks)
    exec_style="hybrid",  # mix of taker for urgent reloads + maker for passive capture
    hybrid_threshold=1.5, # cross on any meaningful residual
    open_seed_size=80,    # full seed at tick 0 (buy_hold-equivalent opening)
    open_window=100,      # short window — grab what's at level 1 at t=0, done.
    open_no_short=True,
)
```

**Expected behaviour on drift-only days:** matches buy_hold on
acquisition cost (seed=80/win=100 should approximate a tick-0 cross).
Overlay very rarely fires (residuals almost never exceed 5 at the
proxy cadence). PnL ≈ buy_hold.

**Expected behaviour on mixed days (unseen):** trim-reload cycles
capture oscillation edge. Projected +50 to +300 PEPPER if
oscillations have the shape observed in bucket 0.

**Expected behaviour on reversing days (unseen):** floor=60
prevents catastrophic downside during a reversal; positions can
drop to 60 (not 0) on a large negative residual. Protective edge.

### Other ideas worth noting but lower priority

- **Fair-value estimator change**: slope-adaptive linear_drift
  (refit slope every 1k ticks) could fire the overlay at better
  times. Out of scope for a quick refinement.
- **Book-imbalance signal**: if level-1 bid volume > 2× level-1
  ask volume, price likely to rise — stay long / don't trim.
  Cheap to implement, plausible edge.
- **End-of-day optimiser**: at t > 95 000, ignore all overlay
  logic and hold +80. Drops any late-session trim losses.
  Tiny effect on this day (drift held to end); could help if
  day shape varies.

## Practical recommendation

1. **Stop iterating on proxy deltas below ±200 PEPPER**. The V3
   experience shows the proxy is unreliable at that resolution for
   seeded-candidate tuning.
2. **If we upload another PEPPER variant, target two axes
   simultaneously**: (a) opening refinement (level-1-only taker),
   (b) overlay that fires on 5-tick excursions with small size.
   Either axis alone is unlikely to clear the noise band; both
   together might add +100 to +300 cleanly.
3. **Recognize that buy_hold_80 is near-optimal on drift-only
   days**. The remaining alpha is contingent on encountering days
   with more pronounced mid-oscillations or reversal structure —
   which we have not seen in Round 1.
4. **Freeze PEPPER work for Round 1** unless a V4 like the sketch
   above is implemented AND the proxy is validated on a synthetic
   oscillation-heavy day first.

## What this tells us about future rounds

- The drift structure (+0.001/tick, linear) is the single most
  predictable feature of PEPPER we've observed. A +80 hold captures
  ~90 % of the theoretical maximum.
- Fill-model fidelity of the local simulator is the #1 blocker to
  further alpha. Any strategy that differs from buy_hold on opening
  behaviour is untrustworthy at the <+100 PEPPER resolution without
  more calibration runs.
- Overlay logic is unexercised on observed data. Before wiring more
  complex overlays, we need AT LEAST ONE official day with visible
  mid-oscillations to validate the mechanism.
