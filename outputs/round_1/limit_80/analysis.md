# Position-limit 50 → 80: critical analysis

IMC's confirmed Round-1 position limit is **80 per product**. This
memo is the pre-change review of what actually changes in the engine,
where the coupling is silent but material, what we will and will NOT
retune, and what the implications are for the six submission bundles.

## 1. Direct usages of `position_limit`

Every site where the field is actually read. I searched for this
exhaustively before touching the code.

### Live path (in every uploaded bundle)

| File | What it does |
|---|---|
| `src/core/config.py` → `ProductConfig.position_limit` | Typed field, validated `> 0` |
| `src/core/signals.py` line 82 | `position_ratio = snapshot.position / config.position_limit` — drives **skew** and **flatten** |
| `src/trader.py` lines 172, 179 | Passed to `RiskManager.clip_orders` — the hard ceiling on our own order sizes |
| `src/backtest/simulator.py` lines 104, 403-404 | Used by the backtest's near-limit counter (triggers at `0.75 × limit`) |

### Research / non-shipped path

| File | What it does |
|---|---|
| `src/strategies/ash_target_position.py` lines 130-131, 218 | Uses limit as the cap for target position and denominator for position ratio. Research-only; not in STRATEGY_REGISTRY, never ships. |
| `src/scripts/round_1/run_round1_fv_compare.py` lines 51, 65 | Hardcoded 50 in a standalone research-script config. One-shot. |

### Historical artefacts — DO NOT edit

| File | What it does |
|---|---|
| `outputs/round_1/official_results/*/*.py` | Previously-uploaded bundles, embedded limit=50 in their banner. These ran on IMC and their results are what they are. They must stay as-is as evidence of what produced the recorded PnL. |
| `outputs/round_1/review_packs/**/manifest.json` | Phase-5 diagnostic packs. Historical. |
| `outputs/round_1/eda/**/*.json` | Phase-1 EDA dumps. Historical. |

## 2. Silent coupling — what actually moves when limit changes

`position_limit` isn't just a ceiling. Because `signals.py` uses
`position_ratio = position / limit` as the driver for both skew and
flatten, changing the denominator silently rescales two knobs:

### Skew (inventory-aversion)

```python
skew = position_ratio × inventory_skew
```

At limit=50, a promoted PEPPER position of +30 yields
`skew = (30/50) × 2.0 = 1.2 ticks` of downward shift on both taker
thresholds.

At limit=80, the **same absolute position** (+30) yields
`skew = (30/80) × 2.0 = 0.75 ticks`.

**Implication**: with unchanged `inventory_skew`, the bot is
**meaningfully less cautious** at mid-sized long positions. It buys
more aggressively when holding 20-50 units than it did at limit=50,
because the internal "how close am I to the cap" signal is scaled
down.

### Flatten threshold

```python
flattening = |position_ratio| >= flatten_threshold
```

At limit=50, promoted's `flatten=0.7` triggered recovery at ±35.
At limit=80 with the same `flatten=0.7`, recovery now triggers at ±56.

| Variant | flatten | trigger @ limit=50 | trigger @ limit=80 |
|---|---:|---:|---:|
| Baseline | 0.8 | ±40 | ±64 |
| Promoted | 0.7 | ±35 | ±56 |
| H1       | 0.7 | ±35 | ±56 |
| F5       | 0.7 | ±35 | ±56 |
| Alt      | 0.9 | ±45 | ±72 |

**Implication**: every variant now rides meaningfully larger
positions before recovery kicks in. For Alt this is +27 extra units
of long-capacity on the +0.001/tick drift day — a direct PnL lift
on drift days AND a direct loss multiplier on reversing days.

### Near-limit metric

`_NEAR_LIMIT_FRACTION = 0.75` in the simulator. Triggers at:

- limit=50: |pos| ≥ 37.5
- limit=80: |pos| ≥ 60

The *same absolute position* that read as "near-limit" at 50 no
longer does at 80. The **counts are not comparable across the
change**. Any PnL-vs-near-limit risk metric in
`fastsearch/pepper_candidates.md` or `official_results/analysis/
bucket_breakdown.md` is a limit=50 artefact; recomputing at limit=80
requires a fresh run.

### Hard ceiling (RiskManager)

`RiskManager.clip_orders` clips order quantities to
`limit − current_position` on buys, `limit + current_position` on
sells. This is the binding cap on raw inventory size. At limit=80
the cap is simply higher; no behavior change until a variant
actually wants to go past ±50.

## 3. Per-variant impact estimate

Assumption: keep every **other** knob unchanged. This is the
conservative "limit-only" change the user asked for. (Retuning
skew / flatten against the new scale is a deliberate follow-up;
see §7.)

| Variant | Max official pos (limit=50) | Likely behaviour @ limit=80 | Expected PnL lift | Expected risk lift |
|---|---:|---|---|---|
| **Baseline** | −8 / +23 PEPPER | Same wrong-direction early sells still happen. Late long leg can now grow past +23; mid-day drift MTM scales up. | Small (maybe +200-500). Does not fix bucket-0 problem. | Minor. |
| **Promoted** | +32 PEPPER | Flatten was hitting at ±35; now ±56. The bot rides bucket-2 long to ~+50-56 instead of topping out at +32. Bigger drift MTM in bucket 2-3. | Moderate (+300-700 projected). | Moderate; now approaches ±60 on the near-limit metric. |
| **H1** | +32 PEPPER | Same PEPPER as promoted. ASH leg unaffected. | Same as promoted. | Same. |
| **F5** | +32 PEPPER | Same inventory profile as promoted (flat=0.7, skew=2.0). Plus per-side asymmetric taker edges. Same mechanics: rides to ~+56. | Moderate (+300-700), same direction as promoted's lift. | Moderate. |
| **Alt** | +45 PEPPER | Flatten was hitting at ±45 (0.9 × 50). Now hits at ±72. Bot runs to ~+70 on the drift day. On drift: **large** PnL lift (~+1000-2000 PEPPER). On reversal: **large** drawdown. | Large. | **Large**. |
| **test** | +50 (full cap) | Buy-and-hold just fills the new cap. PnL is linear in limit: +50 → +80 is 1.6× drift capture. But `max_aggressive_size=50` only fills 50 in one tick; second tick adds 30. Slight degradation unless we bump `max_aggressive_size` to 80. | Linear (1.6×). | Linear. |

## 4. What we are changing

- `src/core/config.py` → `default_engine_config()` → `ASH_COATED_OSMIUM.position_limit` 50 → 80
- `src/core/config.py` → `default_engine_config()` → `INTARIAN_PEPPER_ROOT.position_limit` 50 → 80
- `src/core/config.py` → `round1_test_engine_config()` → `INTARIAN_PEPPER_ROOT.max_aggressive_size` 50 → 80 so the test bundle still fills the cap in one tick (preserves that variant's entire identity; not a tuning decision)
- `src/scripts/round_1/run_round1_fv_compare.py` → two hardcoded 50 → 80 (research script, cleanup)
- `tests/test_buy_and_hold.py` → hardcoded assertions on `position_limit == 50` and `max_aggressive_size == 50` → 80

## 5. What we are explicitly NOT changing

The user's instruction was "update this position limit". These are
natural follow-ups but deliberately **not touched in this pass**:

- `inventory_skew` on any variant. At limit=80 the same numerical
  skew produces a smaller tick shift per unit of inventory. To
  preserve the same tick-shift-at-position-30 behaviour, we would
  scale skew by `80/50 = 1.6`. We do not — each variant keeps its
  identity; the effect is acceptable bot-aggression drift.
- `flatten_threshold` on any variant. Same story: 0.7 at 80 is a
  bigger absolute capacity than 0.7 at 50. We accept this as the
  expressed intent of "raise the limit".
- `max_aggressive_size` on market-making variants (kept at 8 for
  PEPPER, 10 for ASH). Low per-tick taker size is intentional —
  the strategies were tuned to accumulate gradually. Only the test
  bundle's `max_aggressive_size=50` is bumped, because its
  contract was "fill the cap in one tick".
- The shipped `trader_round1_*.py` files already uploaded with
  limit=50 embedded. Those are historical artefacts in
  `outputs/round_1/official_results/*` / the current
  `outputs/submissions/round_1/*.py` on disk. They are NOT
  re-written. New limit=80 bundles go to a separate subfolder
  (`outputs/submissions/round_1/limit_80/`) so every old SHA256
  remains a valid reference to what actually ran at IMC.

## 6. Tests we must update

- `tests/test_buy_and_hold.py::test_round1_test_factory_composition` —
  hardcoded `position_limit == 50` and `max_aggressive_size == 50`.
  Update to 80 for both.
- `tests/test_ash_target_position.py` — sets a test-local config
  with `position_limit=50`. This is test-local scaffolding for the
  research strategy, NOT asserted to track the live config. Leave
  as-is; the strategy math does not care about the specific value.
- `tests/test_signals.py::_config` — sets `position_limit=20` as a
  test-local default. Unchanged. These are signal-engine mechanics
  tests at arbitrary limits, not Round-1-specific.
- `tests/test_config.py::test_round1_f5_uses_asymmetric_taker_edges_on_pepper`
  etc. — do not assert `position_limit`. No update needed.

## 7. Future work (deliberately out of scope here)

Natural next-step retunes (NOT in this pass):

- **Alt re-tuning**: `flatten=0.9` was tuned to ride ±45 out of 50.
  At limit=80, keeping `flatten=0.9` lets it ride to ±72. That may
  be too aggressive for a single-point decision. A safer re-tune is
  `flatten = 45/80 = 0.5625` (preserves absolute capacity) — but
  this is itself an opinionated choice that should only land if a
  second official run confirms ±45 was the right absolute target.
- **Skew re-tuning**: `inventory_skew × (80/50) = 1.6×` to preserve
  the previous tick-shift-per-position relationship. Promoted's
  `skew=2.0` → `3.2`; Alt's `skew=1.0` → `1.6`. Ship only when we
  have a controlled comparison.
- **F5 re-derivation at limit=80**: F5 was selected in the Phase-9
  fastsearch at limit=50. Its asymmetric taker-edge widths were
  chosen against that tuning surface. At limit=80, the slightly
  softer skew may change the optimal `(buy, sell)` pair. Re-running
  the fastsearch at limit=80 is a reasonable follow-up; NOT done
  here because the user asked for a limit update, not a retune.

## 8. Re-export plan

After the code change:

1. Re-export all six variants with `--variant ...` for each,
   writing outputs to `outputs/submissions/round_1/limit_80/` (new
   subfolder). This preserves the old limit=50 bundles on disk
   untouched.
2. Validate each with `src/scripts/validate_submission`. Expect the
   same "size_approaching_limit" warning we saw on the limit=50
   bundles; no error-level issues.
3. Record SHA256 + byte size per bundle in
   `outputs/submissions/round_1/limit_80/README.md`.
4. Update `docs/round_1/upload_plan.md` to note the new bundles
   and clear the "position_limit is placeholder" caveat.

## 9. Uncertainty flags

These are the things I am NOT certain about after this change:

1. **The relative ranking between variants** is a limit=50 result.
   Nothing in this pass reruns the fastsearch comparison. The
   limit=80 rankings may differ — plausibly Alt's advantage grows
   (bigger inventory capacity on drift days), and F5 may or may not
   keep its lead over H1 depending on how sensitive the asymmetric
   taker signal is to the softened skew.
2. **Near-limit counts are no longer comparable** to the recorded
   official results (which were limit=50). A limit=80 run's
   near-limit metric uses a ±60 threshold; the limit=50 runs used
   ±37.5. Do not compare these across the change.
3. **The Alt tail-risk estimate** is limit=50 data. At limit=80
   Alt's peak long on a drift day is likely ~+70-72; the
   consequences of being at +72 on a reversing tick are worse than
   being at +45 on a reversing tick.
