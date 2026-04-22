# Diagnostic Findings — What The Data Actually Says

**Compiled:** 2026-04-22. After running D1-D5 on R1/R2 data and cross-referencing
local backtest vs official IMC test-upload results.

**Bottom line: the dominant failure mode is NOT what I hypothesized in the critical analysis. It's F7 (backtest/live calibration mismatch), catastrophically so.**

---

## 1. Updated failure-mode ranking (evidence-based)

| Rank | Failure | Status | Evidence |
|---|---|---|---|
| **1** | **F7 — Backtest/live fill-model mismatch** | **CONFIRMED CATASTROPHIC** | Backtest over-predicts by 13%+; ranking REVERSES on live |
| 2 | F5 — FairValueEngine reactive-only | **SIGNAL REAL, NEEDS DIFFERENT FIX** | OBI IC=0.52 but MM cannot exploit via FV skew |
| 3 | F4 — Per-product architecture | **DORMANT (critical for R3)** | No cross-product ρ in R1/R2, mechanical in R3 baskets |
| 4 | F2 — Residual allocator disabled | **MARGINAL ON R1/R2** | +350 best, -134 worst; R1/R2 MM already saturated |
| 5 | F1 — FlowAnalyzer observational | **UNTESTABLE ON REPLAY** | Buyer/seller empty in replay CSVs; live-only |
| 6 | F8 — Plateau vs peak bias | **SUBSUMED BY F7** | Whole sweep landscape is miscalibrated |
| 7 | F3 — Silent exception swallow | Not tested | Risk remains, but not the P&L driver |
| 8 | F6 — Three MM models | Not tested | Engineering cost, not P&L cost |
| 9 | F9 — No aggression mode | Not tested | Secondary |

---

## 2. The catastrophic finding — F7 in detail

**What the diagnostics proved.** Our R2 promoted config `wide_w113` was selected from a local backtest claiming +20% over the L1 baseline. On **actual IMC official test uploads**, the ranking REVERSED:

| Variant | Local backtest claim | Official live mean (n=4) | σ |
|---|---|---|---|
| **Promoted (wide_w113)** | "+20% winner" | **7,654** | 366 |
| Ash L1 (baseline) | baseline | **7,952** | 248 |
| Killswitch | equivalent-ish | 7,812 | 166 |
| v5 | untuned | **7,972** | 442 |

**We shipped a config that was 4% WORSE than the baseline.** The entire R2 sweep infrastructure selected a loser. The backtest fill model (`passive_allocation=0.3`) over-predicts P&L by ~13% absolute AND misranks neighboring configs.

**This alone explains the 20-25% gap:**
- Top teams got ~11-12k on their backtests
- We got ~12k on our backtest too (11,785 wide_w113)
- Top teams' live numbers are likely close to their backtest (they've calibrated fill)
- Our live numbers collapsed to 7,654 (we haven't calibrated fill)
- **We didn't underperform top teams on signal. We underperformed on CALIBRATION.**

Every R2 decision is now suspect: the kill-switch ablation, the residual gate, the MAF bid calibration, the sweep winners. All made on a biased objective function.

---

## 3. F5 refined — the OBI signal finding

**What the data shows.**

| Product | Horizon | OBI IC (Pearson) | OBI IC (Spearman) |
|---|---|---|---|
| ASH_COATED_OSMIUM | 10 ticks | **+0.52** | +0.51 |
| ASH_COATED_OSMIUM | 100 ticks | +0.32 | +0.30 |
| INTARIAN_PEPPER_ROOT | 10 ticks | **+0.57** | +0.61 |
| INTARIAN_PEPPER_ROOT | 100 ticks | +0.52 | +0.54 |

These are **enormous** — typical quant-fund ICs are 0.03-0.08. OBI at +0.52 is essentially deterministic. The predictive signal is real.

**BUT — the counterfactual failed.** When I added `β × book_imbalance × spread` to the `weighted_mid` fair value for ASH, every non-zero β HURT P&L:

| β | ASH P&L | Δ vs β=0 |
|---|---|---|
| -0.5 | 7,439 | -2,408 |
| 0.0 | 9,847 | 0 |
| +0.5 | 5,764 | -4,083 |
| +1.0 | -69,602 | -79,449 |

**Why the signal has 0.52 IC but fair-value skew fails:**

When OBI says "price will drift up by N ticks in 10 steps", the **whole book** re-prices — best_bid moves up, best_ask moves up in sync. An MM that shifts fair value up simply quotes higher on both sides:
- Higher bid → buys at elevated price (just before it moves up further) — OK
- Higher ask → doesn't get lifted (because the book moved with us) — neutral

Net: no edge captured. The OBI alpha is **directional** (take + hold), not **reservation-price** (skew the MM quote).

**Correct architecture to capture OBI:**
1. **Asymmetric quoter**: when OBI > threshold, quote bid ONLY; when OBI < -threshold, quote ask ONLY. Stops you from selling into a rising market.
2. **Directional taker overlay**: when OBI > strong-threshold, cross the spread (take the ask). Unwind after N ticks or when OBI flips. Pure alpha extraction.

Neither exists in your codebase today. The AshLadderStrategy always quotes both sides.

**This reframes F5.** The critical analysis said "all 12 FV estimators are reactive, none predictive." True, but the fix isn't "add a predictive FV estimator" — that doesn't help MM strategies. The fix is to restructure how signals feed through to orders. **The architecture must support one-sided quoting and directional takes, triggered by predictive signals.**

---

## 4. F4 — confirmed DORMANT in R1/R2, critical for R3

| Pair | Round | ρ at any lag |
|---|---|---|
| ASH ↔ PEPPER | R1 | max ≤ 0.02 |
| ASH ↔ PEPPER | R2 | max ≤ 0.01 |

Products are truly independent in R1/R2. F4 is not a R1/R2 leak. **But in R3, baskets and constituents will have ρ ≈ 0.7 by construction** — so the cross-product architectural investment is the correct preparation, just not a retrofit for R1/R2.

---

## 5. F2 — marginal on MM products

Residual allocator A/B on R2 baseline:

| Variant | Total P&L | Δ vs off |
|---|---|---|
| baseline (off) | 249,375 | 0 |
| edge=3, size=2 | 249,725 | **+350** |
| edge=2, size=2 | 249,241 | -134 |

Small effect — R1/R2 MM strategies (Pepper + ASH ladder) already saturate the book. Residual allocator fires after the main strategy; if main strategy left no slack, residual adds nothing. **Will matter for R3 baskets** where spread-arb uses only a fraction of position limits.

---

## 6. F1 — untestable on replay, but the hypothesis is still alive

R1/R2 trade CSVs have empty `buyer` and `seller` fields for market trades (only bot-to-market, no counterparty IDs). So signed-flow signals have zero variance in replay. Can't measure the FlowAnalyzer's IC against next-tick returns.

**In live submission**, `TradePrint.buyer/seller` are populated. The FlowAnalyzer's architectural limitation (observational-only) is still a concern — we just can't quantify it offline.

Action: wire FlowAnalyzer output into quote-skew behind a config gate; turn on in R3 once live IC is measured.

---

## 7. The corrected build plan — for real this time

### Step 0 — CALIBRATE FILL MODEL FIRST (before anything else)

Everything else is downstream of `passive_allocation`. Plan:

1. Download 2-3 top-team P3 repos (chrispyroberts, TimoDiehm, CarterT27).
2. Port each to run through OUR backtest/simulator.
3. Read their published live/official P&L from their READMEs.
4. Sweep `passive_allocation ∈ {0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50}`.
5. Find the value that reproduces their published number for each repo.
6. If 3 repos converge on a value (say 0.15), adopt that as the true fill rate.
7. Re-run every historical R1/R2 sweep on corrected fill model.
8. Check which configs ACTUALLY win under the corrected model.

**Budget: 2-3 days.** This is the single highest-ROI work we can do. Every other calibration decision depends on it.

### Step 1 — Asymmetric quoter for OBI alpha

Not "predictive FV estimator." Instead: a new strategy layer that takes OBI as input and:
- One-sided quote when OBI > threshold (suppress the side that will be adversely filled)
- Optional: directional taker overlay when OBI > strong threshold

Test counterfactually against D4 target. If asymmetric quoting captures any of the +0.52 IC, F5 is closed.

### Step 2 — Directional overlay on top of MM

On any product where OBI IC > 0.1 (confirmed with live data once fill model is calibrated): add a directional-trade overlay. When OBI crosses high threshold, take up to 20% of position limit; unwind after the predicted horizon (10-100 ticks) or when signal flips.

Budget a small fraction of position capacity for this — don't compete with MM for the same inventory slots.

### Step 3 — Infrastructure for R3

Only AFTER Steps 0-2 show lift:

- Cross-product `PortfolioContext` for basket engine (F4 preparation)
- Residual allocator default=True specifically for basket/arb strategies (F2 preparation)
- FlowAnalyzer → SignalBus wiring for live counterparty signals (F1 preparation)

These are architectural investments whose payoff is contingent on R3 having baskets, which is 8/10 per the prior-editions research.

### Step 4 — The rest of Tier X/Y from the blue-sky plan

- Bayesian ensemble FV (still worth doing; existing estimators all reactive, a blended predictive+reactive beats pure)
- Counterparty intelligence engine (A1 in hidden-alpha)
- Cross-edition regression + DP execution (R5 only)

But EVERY one of these needs the fill model fixed first. Otherwise they're tuned on biased numbers.

---

## 8. What I got wrong in the critical analysis

My original critical-analysis doc ranked F1/F2/F5 as top leaks. The data says:

- **F1 not testable on replay, deferred to live.**
- **F2 marginal on R1/R2, matters for R3.**
- **F5 has real signal but wrong fix proposed.**

And it missed the dominant failure entirely: **F7 was already observable in outputs/round_2/Official Results/ but nobody had cross-referenced local backtest against live scores.** The 20-25% gap you cited isn't a signal gap — it's a calibration gap.

The lesson for R3-5: **before building any new engine, validate that the backtest reproduces live numbers on a reference strategy.** If the backtest is biased, every sweep result is a Rorschach test.

---

## 9. Recommended action sequence

| Step | Task | Budget | Gate |
|---|---|---|---|
| 0 | Fill model calibration (port 2-3 top-team repos) | 2-3 days | Finds true passive_allocation |
| 1 | Re-run R1/R2 sweeps with corrected fill model | 1 day | Identifies true optimum; may un-promote wide_w113 |
| 2 | Asymmetric quoter for OBI | 1 day | Tests if +0.52 IC is capturable |
| 3 | Directional overlay (if Step 2 works) | 1-2 days | Adds take-based alpha stream |
| 4 | FlowAnalyzer → SignalBus wiring (behind gate) | 1 day | Ready for live-counterparty-ID data |
| 5 | Cross-product PortfolioContext (R3 prep) | 2 days | Unblocks basket engine |
| 6 | Residual allocator default=True for arb | 0.5 days | R3 basket alpha |
| 7 | Tier X/Y/Z items from blue-sky plan | As planned | All measured under corrected fill model |

**Total before R3: ~9 days** if done sequentially, ~5 days if parallelized across a 2-person team.

---

*Want me to start Step 0 — port a top-team P3 repo into our backtest for fill-model calibration? That's the single highest-leverage next action.*
