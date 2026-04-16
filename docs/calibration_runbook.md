# Round-N calibration & strategy-audit runbook

A reusable, day-by-day playbook for getting from "round opens" to
"shipped a structurally validated strategy" using the calibration
infra in `src/analysis/calibration/` and `src/scripts/calibration/`.

This pipeline runs in pure Python with the existing `.venv`. No Rust,
no extra services. Everything is product-name agnostic.

---

## Day 1 — submit hold-1 probe

**Action**: upload `outputs/submissions/calibration/trader_hold_one.py`
to round-N as your first submission.

**What it does**: buys 1 unit of every visible product at t=0 and
holds forever. Product-name agnostic.

**Cost**: trivial (a few cents of PnL impact). Fits within any
submission budget.

**Why it matters**: this is the only way to recover the server-side
continuous fair value without solving an under-identified inverse
problem. Without it, every downstream step is using mid-price as a
noisy proxy.

**Download after run**: the activity log JSON from the submissions
page. Drop into `data/raw/round_N_hold1/<submission_id>.json`.

---

## Day 2 — calibrate

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.calibration.run_calibration \
    --log data/raw/round_N_hold1/<submission_id>.json \
    --trades-csv data/raw/round_N/trades_round_N_day_0.csv \
    --out outputs/calibration/round_N_hold1
```

Optional: pass multiple `--trades-csv` flags to combine days.

**Outputs in `outputs/calibration/round_N_hold1/`:**
- `fits.json` — machine-readable parameters per product
- `calibration_report.md` — human-readable summary tables
- `plots/<product>/01_fv_path.png` ... `10_trade_locations.png` —
  10 diagnostic plots per product

**Sanity checks (do these in order):**

1. **Open `02_return_law.png`**. Δfv histogram should be roughly
   bell-shaped centered near zero. If asymmetric or fat-tailed,
   the Gaussian RW model is misspecified — note this and consider
   regime-switching extensions.
2. **Open `01_fv_path.png`**. The path should look like a smooth
   curve (no jumps). Discontinuities mean either FV recovery
   failed or the product has discrete events (settlements,
   announcements).
3. **Check `fits.json` -> per-product -> `fair_value.ar1_phi`**.
   With drift correctly subtracted, |phi| should be < 4 * phi_se.
   Otherwise there's real autocorrelation (rare; investigate).
4. **Check `quote_rules` match rates**:
   - Outer wall rules: expect 95%+ match
   - Inner wall rules: expect 80%+ match (lower if multi-bot at inside)
5. **Check `trade_arrivals.geometric_ks_stat`**. Below ~0.10 means
   trade arrivals are reasonably memoryless Bernoulli. Higher means
   the model is misspecified — consider clustered arrival models.

**Red flags to escalate:**
- Match rates < 80% on outer walls → calibration broken
- p_active = 0.0 → trade-CSV path wrong or empty
- p_buy = 0.5 exactly → trade-direction inference disabled

---

## Day 3 — audit candidate strategies

For each candidate strategy you've built:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.calibration.run_strategy_audit \
    --strategy outputs/submissions/round_N/<candidate>.py \
    --hold1-log data/raw/round_N_hold1/<submission_id>.json \
    --trades-csv data/raw/round_N/trades_round_N_day_0.csv \
    --product <PRODUCT_1> --product <PRODUCT_2> \
    --out outputs/calibration/audit_<candidate>
```

**Outputs:**
- `quote_scores.csv` — per-quote: timestamp, side, quote_price,
  edge_at_quote (vs server FV), filled_qty, markout_h{1,5,20,50}
- `summary.md` — aggregated metrics

**Decision criteria — rank candidates by:**

| Metric | Good | Bad |
|---|---|---|
| `mean_edge_per_quote` | > 0 | <= 0 (strategy quotes on adverse side of FV) |
| `mean_edge_per_fill` | > 0 | <= 0 (filled quotes have negative selection) |
| `markout_h1`, `h5`, `h20`, `h50` per fill | All POSITIVE | Mixed signs OR all negative |
| Positive markouts on BOTH sides | yes | only one side |

**Single-day caveat**: the audit replays one day. Edge signs are
robust to passive-fill model assumptions, but PnL absolute level is
not. Use sign + magnitude of markouts to rank — not the realized PnL
number from the replay.

**Promotion gate**:

> Ship the candidate with the highest `markout_h5_per_fill` (medium
> horizon — long enough to escape noise, short enough to not be a
> regime artifact) AND positive markouts on both sides.

---

## Day 4-5 — submit and monitor

Submit the promoted candidate. Compare official PnL on day-0 to:
- Replay's `realized_pnl` (will not match — replay model is
  conservative)
- Quote-level edge prediction (extrapolated by side: `n_fills_official
  ≈ n_fills_replay * adjustment_factor`, `realized_pnl_official ≈
  n_fills_official * mean_edge_per_fill`)

**After official results land**: update
`docs/transfer_ratio_history.md` (create on first round) with this
round's `(local_replay_PnL, official_PnL)` pair so future rounds
know the typical transfer ratio for similar strategies.

---

## What to do when the calibration looks wrong

| Symptom | Most-likely cause | Fix |
|---|---|---|
| Bot rule match rates all < 80% | FV recovery incorrect | Check `mode='hold_one'` actually fired (logs); verify hold-1 trader actually held position 1 throughout |
| Multi-day jumps in FV path | Day boundaries not handled | Pass `--trades-csv` for each day; the runner concatenates |
| `n_quotes` per product is 0 in audit | Trader code threw an exception | Run audit with `-v`; check stderr |
| Fill rate in audit << what you saw officially | Passive fill model too conservative | Known limitation; trust edge sign not absolute PnL |
| Wrong product names in `fits.json` | Round-N product list differs from previous rounds | Hold-1 trader is product-agnostic — it picks up whatever's in `state.order_depths`. No code change needed. |

---

## Reusable artifacts checklist

When round-N closes, these artifacts go in `outputs/calibration/round_N_*/`:

- [ ] `round_N_hold1/fits.json` (calibration)
- [ ] `round_N_hold1/calibration_report.md`
- [ ] `round_N_hold1/plots/` (10 diagnostic plots per product)
- [ ] `audit_<candidate>/summary.md` for each candidate audited
- [ ] `audit_<promoted_candidate>/VERDICT.md` (hand-written
      structural-edge analysis like `f3a_retrospective/VERDICT.md`)
- [ ] Update `docs/transfer_ratio_history.md` with the
      (local_replay_PnL, official_PnL) pair after results land

---

## Future infra (NOT yet built)

The pieces below are NOT implemented yet. Build only when there's a
specific question they're needed for.

### Generative Monte Carlo simulator (~2-3 days to build)

- `src/analysis/calibration/generative_simulator.py` — uses fitted
  params to spawn synthetic 100k-tick sessions with the calibrated
  bot model + trade arrivals
- `src/scripts/calibration/run_monte_carlo.py` — N sessions x
  candidate config grid, output PnL distribution + per-session
  alpha + R^2 stability metric

When to build: when you need to filter overfit configs that look good
on one day but might be unstable across regimes. The audit pipeline
above answers "is this strategy structurally good on THIS day"; the
Monte Carlo would answer "is this strategy stable across MANY days
of similar structure".

### Joint side-+-location trade classifier

The current `(price > FV → buy)` heuristic misclassifies ~25% of
trades on products with asymmetric quotes (TOMATOES, possibly
round-N analogs). When trade-direction information is needed at
high precision (e.g., for adverse-selection breakdown), implement
a joint EM model that fits side-+-location together.

### Per-mechanism transfer-ratio tracker

After ~5 rounds of (local_replay_PnL, official_PnL) pairs, fit a
per-mechanism family (wall_mid + AS, weighted_mid + skew, etc.)
transfer-ratio distribution. Use it to calibrate raw replay
predictions to expected official PnL.
