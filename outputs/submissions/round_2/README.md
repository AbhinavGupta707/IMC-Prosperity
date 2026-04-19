# Round-2 submission bundle — provenance manifest

This is the **single Round-2 upload candidate** built from the
batch-E factory + export pipeline. One bundle, one decision.

## Variant

| Field | Value |
|---|---|
| Variant name | `round2_promoted` |
| File | [`trader_round2_promoted.py`](trader_round2_promoted.py) |
| Source factory | `src.core.config.round2_v5micro_wide113_engine_config` |
| Export script | `src.scripts.round_2.export_round2_submission` |

## Embedded configurations

### ASH_COATED_OSMIUM (batch-D1 sweep winner)

`AshLadderStrategy` with `LadderParams`:

| Field | Value |
|---|---|
| `edges` | `(3.0, 5.0, 8.0)` (wide) |
| `size_mults` | `(1.0, 2.0, 3.0)` |
| `weights` | `(1, 1, 3)` (outer-heavy) |
| `skew_coef` | `1.0` |
| `flatten_threshold` | `0.7` |
| `fair_value_method` | `weighted_mid` |
| `taker_edge` | `0.5` |

Local PnL expectation on R2 tape: **+11 785** across 3 days
(+3 755 / +3 988 / +4 042 per day, σ = 153). Beats the R1 L1
ladder by +20% / +1 938 XIRECs. See
[`outputs/round_2/ash_sweep.md`](../../round_2/ash_sweep.md) for
the full sweep evidence (73 candidates).

### INTARIAN_PEPPER_ROOT (R1 v5_micro winner, unchanged)

`PepperCoreLongStrategy` with `CoreLongParams`:

| Field | Value |
|---|---|
| `base_long` / `ceiling` | `80` / `80` |
| `add_thresh` / `trim_thresh` | `3.0` / `8.0` |
| `add_gain` / `trim_gain` | `5.0` / `2.0` |
| `step` | `8` |
| `exec_style` | `taker` |
| `open_seed_size` / `open_window` | `65` / `500` |
| `open_no_short` / `open_take_mode` | `True` / `level1_only` |
| `guard_window` / `guard_negative_slope` / `guard_target` | `32` / `0.01` / `0` |
| `micro_residual_threshold` / `_imbalance_threshold` | `3.0` / `0.30` |
| `micro_add_size` / `_trim_size` | `2` / `2` |
| `fair_value_method` | `linear_drift` |
| `quote_size` / `max_aggressive_size` | `10` / `20` |
| `flush_history_on_day_rollover` | `True` (no-op on this stack but enabled for hygiene) |

**Kill switches deliberately DISABLED.** Batch-D2 sweep confirmed
they are redundant with the strategy's existing `guard_negative_slope`
machinery on this stack — the kill code stays in the codebase for
guardless variants but is not activated here.

Local PnL expectation on R2 tape: **+239 528** across 3 days
(+79 341 / +79 959 / +80 228 per day, σ = 374 = 0.5% of mean).
PEPPER strategy is effectively a deterministic +80k/day annuity
across 6 independent day realisations (3 R1 + 3 R2).

### MAF auction bid (`Trader.bid()`)

| `--bid` value | Use |
|---:|---|
| `0` (default) | Local development, paper testing — abstain from auction. |
| **`350`** | **Recommended for final upload** (revised after seeing official-test data). |

#### Revised bid: `350` (was `2300`)

The original D3 model assumed `v ≈ 10 000` (private value of winning
the +25% access bonus). After running 16 official tests across 4
variants we have actual PnL data, and the original `v` baked in a
generous PEPPER uplift assumption that the data refutes.

**Why v dropped from 10 000 → 3 000:**
- PEPPER pins at +80 for ~99% of the run (open_no_short=True,
  base_long=80, ceiling=80, taker exec → fills the long fast and
  holds). Extra ask access past the position limit is unconsumed.
  PEPPER uplift from extra access ≈ +0.7-1.4k (opening accumulation
  only), not +6-10k.
- ASH benefits symmetrically: 25% extra book volume ≈ +25% × +7.2k
  scored ASH PnL = +1.8k.
- **v_central ≈ 3 000 XIRECs** (range 2-4k).

**Decision at v = 3 000 (full grid: `outputs/round_2/maf_bid_decision.md`):**
- EV-max bid: **`350`** → mixture EV +2 220 XIRECs (P_win 84%).
- Floor-EV-max bid: `1800` → floor EV +957 XIRECs (gives up ~25%
  mixture EV for consensus-collapse protection).
- Bid `2300` (old recommendation): EV ≈ +691 XIRECs at v=3k —
  positive but ~3× worse than bid 350.
- Bid `0`: EV = 0 (guaranteed loss; ties go to losers per the wiki).

**Why not bid 0?** Every prior has at least 15-50% of opponents
bidding 0 — you tie at the bottom and lose. Even at the pessimistic
v=2 000, bid 350 yields +1 382 EV vs +0 for bid 0.

**Why 350 over 1800?** 350 captures the naive-heavy quintile (~50%
of opponents bid 0; 30% bid in [10, 100]) for cheap. The robust bid
1800 only matters under the aggressive-prior tail (~15% probability)
and the consensus-collapse stress, both of which are speculative —
and we'd rather expose +200 of dead-cost in the worst case than pay
+1 450 of certain cost across all scenarios.

## Build provenance

| Field | Value |
|---|---|
| Built at | 2026-04-19 (batch E + post-review fixes F1/F2/F3/F4/F5/F6) |
| Source commit | `4bd826e` + post-review fixes |
| Bundle size | 84 017 bytes (68% of validator hard cap) |
| Validator | `0 errors, 0 warnings` |
| Bundle SHA256 (`--bid 350`) | `885d9cec6eeda3c06f3a88ffd55ac3f150b8180ffbe4cc8da8f51fbeba3a2218` |
| Bundle SHA256 (`--bid 2300`, deprecated) | `a4a17c8e66e00dde6f67fb7ef970a54f8d3a402d5f90348fee7e18d37540325c` |
| Smoke test | `Trader().bid()` returns 350 ✅; `Trader.run()` produces well-formed orders for both products ✅; pytest `tests/test_round2_export_e2e.py` 19/19 ✅; full pytest suite 733/733 ✅ |
| Banner redaction | Strategy parameter dump removed from upload banner (F6) — competitors cannot grep ladder edges / weights / kill-switch thresholds from the uploaded file. |

## Reproducing the bundle

```bash
# Final upload bundle (revised MAF bid):
PYTHONPATH=. .venv/bin/python -m src.scripts.round_2.export_round2_submission --bid 350

# Local development bundle (no MAF bid):
PYTHONPATH=. .venv/bin/python -m src.scripts.round_2.export_round2_submission

# Validate before upload:
PYTHONPATH=. .venv/bin/python -m src.scripts.validate_submission outputs/submissions/round_2/trader_round2_promoted.py

# Verify fingerprint:
shasum -a 256 outputs/submissions/round_2/trader_round2_promoted.py
```

The build timestamp lives in the embedded banner so two consecutive
exports of the same `--bid` value differ ONLY in that one line.
For SHA256-stable rebuilds, compare the body of the file (skip
the banner) or rebuild against the same source commit.

## Local-tape PnL expectation (batch C + D1 stack)

| Component | PnL (3 R2 days × 10k snaps) |
|---|---:|
| ASH (`wide_w113_s1_f0.7`) | +11 785 |
| PEPPER (v5_micro, kill-off) | +239 528 |
| **Total before MAF bid** | **+251 313** |
| MAF bid (paid only if won) | −2 300 |
| **Total local (if MAF won)** | **+249 013** |

Translation to official:
- R1 final showed local→official compression of ~3× on the same
  v5_micro PEPPER stack.
- Expected R2 official total: **+80–90k** (algo) + MAF EV +7-8k
  − MAF bid 2 300 = **net ~+85-95k**.
- Combined with R1 cumulative (~+170k), Round-2 total expected:
  **~+255-265k** — comfortably above the 200k Phase-2 gate.

## What we deliberately did NOT do

- **No kill-switch activation** on this submission (batch D2 evidence).
- **No alt / hybrid / experimental variants** — one bundle, one decision.
  R1 had three (baseline / promoted / alt); R2 ships one because the
  v5_micro stack is empirically dominant and the ASH winner is a clean
  plateau, not a marginal pick.
- **No re-tuning of PEPPER** — it is already a deterministic annuity
  and unforced changes are all downside.
- **No bid value other than 0 or 2300** — analysis grid is exhaustive
  enough that any other choice is hand-tuning into noise.
