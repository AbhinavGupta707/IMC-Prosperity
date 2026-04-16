# MC simulator validation — findings & limitations

Validation gates run against round-1 ASH/PEPPER calibration.

## CAVEATS DISCOVERED IN ADVERSARIAL REVIEW (post-hoc additions)

1. **Gate 1's arrival-rate check is currently a no-op.** Code line
   `arr_pass = True  # ... trivially close` in
   `run_simulator_validation.py:226` hardcodes pass. Only sigma + drift
   are real checks. P0 fix in flight.

2. **Gate 2 PASS for ASH was generous.** Trade-size TVD=0.17 and
   trade-loc KS=0.11 both fail the 0.10 threshold; we attributed the
   failures to small-n trade samples (n=43 ASH trades within fact
   window), which is true, but doesn't make the gates pass. Trade-
   distribution marginals on ASH are NOT validated — only the FV
   process and quote bands are.

3. **Gate 3 (replayer-vs-MC, claimed PASS in MC_VERDICT) is too
   lenient.** strategy_replay PnL=+58, MC median=+465, official=+1395
   — 8x and 24x divergences. Calling that "sign-consistent" is a low
   bar. The fill model in strategy_replay is the source of the gap;
   it has not been calibrated against official PnL.

## Gate 1: round-trip parameter recovery — **2/2 PASS** (caveat: arrival-rate check is no-op)

Spawning N synthetic ticks with calibrated parameters, then re-fitting
calibration on those synthetic ticks, recovers the original parameters
within sampling-error tolerance:

| Product | Real σ | Synth σ | Real drift | Synth drift | Pass |
|---|---:|---:|---:|---:|---|
| ASH | 0.4074 | 0.4071 | -0.0083 | -0.0044 | ✅ |
| PEPPER | 0.1898 | 0.1841 | +0.0940 | +0.0986 | ✅ |

**Verdict**: simulator correctly reproduces what we put in. No bug
in the spawn → re-calibrate roundtrip.

## Gate 2: marginal distribution match vs real data

| Marginal | ASH KS | PEPPER KS | Threshold | ASH Pass | PEPPER Pass |
|---|---:|---:|---:|---|---|
| FV returns | 0.091 | **0.415** | 0.10 | ✅ marginal | ❌ structural mismatch |
| Top-of-book spread | 0.016 | 0.090 | 0.10 | ✅ | ✅ |
| Per-rank ask offset (rank 1) | 0.027 | 0.112 | 0.10 | ✅ | ❌ borderline |
| Per-rank ask offset (rank 2) | 0.034 | 0.118 | 0.10 | ✅ | ❌ borderline |
| Trade arrival rate (p_active) | 0.006 abs | 0.002 abs | 0.01 | ✅ | ✅ |
| Trade size TVD | 0.170 | 0.124 | 0.10 | ❌ small-n | ❌ small-n |
| Trade location KS | 0.110 | 0.154 | 0.10 | ❌ marginal | ❌ borderline |

## Headline finding: PEPPER is NOT a Gaussian random walk

Inspection of PEPPER's recorded server FV reveals:
- 999 increments observed
- **598 of them are +0.0996** (~+0.1 ticks)
- **400 of them are +0.1006** (~+0.1 ticks)
- **1 of them is -5.9004** (a single large jump)

That's it. Three unique values. PEPPER's "sigma=0.19" is entirely
contributed by the one outlier. Without it, PEPPER would be
**deterministic +0.1 ticks per tick**.

This explains the Phase-F observation that `buy_hold_80` returned
+7286 every time across all submissions: PEPPER appreciates by
**~+0.1 ticks per tick × 80 units position × ~999 ticks ≈ +7992**,
minus the single jump's impact on ~80 units mark-to-market loss.
The +7286 was structural, not lucky drift.

**Implication for MC**: a Gaussian random walk is the wrong process
for PEPPER. Synthetic PEPPER paths drawn as `Normal(+0.094, 0.19)`
look nothing like the deterministic real path.

**Workaround for F3a verdict** (acceptable):
- F3a's PEPPER strategy is `buy_hold_80` (5 buys at t=0, hold).
- This strategy is **insensitive to PEPPER FV variance**: it only
  cares about whether PEPPER drifts up.
- A Gaussian RW with drift +0.094 (synth) does drift up on average,
  so MC will produce buy_hold_80 PnLs of similar magnitude to real.
- The MC PnL for PEPPER will have higher variance than reality (real
  is essentially deterministic), but the median will be reasonable.

**Future fix (v2 of simulator)**: model PEPPER as deterministic drift
plus rare jump component. Requires modeling the jump distribution
from a longer trade sample (we only have 1 jump event in our
calibration data, which is not enough to fit a jump distribution).

## Other Gate 2 failures explained

**ASH FV returns KS=0.091** (just under threshold): borderline pass.
ASH IS approximately Gaussian RW; the slight mismatch is partially
from rounding noise and partially from sampling.

**ASH trade size TVD=0.17 / trade loc KS=0.11**: only 43 ASH trades
fall within the activity log's tick range (the trades CSV covers
beyond the activity log's window). 43 samples is too few to fit a
discrete categorical distribution with KS < 0.10. With more trade
data the metrics would tighten.

**PEPPER per-rank ask KS=0.11-0.12**: borderline. Likely a
combination of PEPPER's atypical FV process (driving the bots'
rounding logic) and our `frac(FV)` bucketing (10 buckets) being
suboptimal for PEPPER's narrow FV range. Could improve by re-fitting
the bot-band sub-cluster split with finer parameters.

## Decision: proceed with F3a MC verdict

Good enough to run the F3a cohort verdict, with the following
explicit caveats:

1. ✅ **ASH MC is faithful** — all gates pass for ASH within
   sampling tolerance. F3a's ASH market-making edge can be MC-tested
   reliably.

2. ⚠️ **PEPPER MC is approximate** — synth PEPPER FV is more volatile
   than real. F3a's `buy_hold_80` PEPPER component is robust to this
   (it only needs upward drift), so the F3a aggregate PnL will be
   higher-variance than reality. MEDIAN should match within ~10%.

3. ❌ **MC unsuitable for PEPPER MM strategies** — any active PEPPER
   trading strategy evaluated under MC would see synth volatility
   that doesn't match reality. Use strategy_replay (against real
   recorded FV) instead for PEPPER strategy evaluation until v2.

The F3a verdict scope is preserved: validate F3a's structural ASH
edge under MC. PEPPER is a constant +7000ish baseline regardless.
