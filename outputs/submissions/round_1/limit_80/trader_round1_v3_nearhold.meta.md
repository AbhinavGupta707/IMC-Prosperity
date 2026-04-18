# V3_nearhold submission bundle — metadata

Companion record for
`outputs/submissions/round_1/limit_80/trader_round1_v3_nearhold.py`.
Source of truth for what is embedded in the V3_nearhold upload.

## File fingerprint

| Field | Value |
|---|---|
| Output file | `outputs/submissions/round_1/limit_80/trader_round1_v3_nearhold.py` |
| Size | **90 946 bytes** (~89 KiB) — minified, under IMC's 100 KiB upload cap |
| SHA256 | `73fc0f8e8dbeac7cf3295b860fefb92d2e4a5c7aaecca6ef50f8b004138d695b` |
| Source commit | `043faac` (`043faac88e87eb1a41dfc5d1302d966a7906d947`) |
| Datamodel mode | `platform` (production) |
| Validator result | `OK` (0 errors, 0 warnings; 89 % of 100 KiB cap) |
| Exporter | `src.scripts.round_1.export_round1_v3_nearhold` |

Re-exports at the same commit produce different SHAs because the
banner embeds a build timestamp; compare body-only bytes to verify
semantic equality across re-exports.

Re-export with:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_1.export_round1_v3_nearhold
shasum -a 256 outputs/submissions/round_1/limit_80/trader_round1_v3_nearhold.py
```

## Position limits — confirmed

| Product | position_limit |
|---|---:|
| ASH_COATED_OSMIUM | **80** |
| INTARIAN_PEPPER_ROOT | **80** |

Verified at runtime by the smoke test
(`Trader().config.product_config(p).position_limit == 80` for both
products). Also verified that the V3 runner reproduces the search's
+7 351.0 proxy PEPPER PnL exactly with end-of-bucket positions
[80, 80, 80, 80].

## Exact config composition

### ASH_COATED_OSMIUM — byte-identical to V2_clean / H1 / F5 / Alt

```python
ASH_COATED_OSMIUM = dict(
    position_limit=80,
    strategy_name="market_making",
    fair_value_method="wall_mid",
    fair_value_fallbacks=("mid", "microprice"),
    maker_edge=1.5,
    taker_edge=0.5,
    inventory_skew=4.0,
    flatten_threshold=0.7,
    history_length=48,
)
```

Not explored in the sparse-overlay pass; preserved unchanged.

### INTARIAN_PEPPER_ROOT — V3_nearhold leg

```python
INTARIAN_PEPPER_ROOT = dict(
    position_limit=80,
    strategy_name="pepper_core_long",      # routes to PepperCoreLongStrategy
    fair_value_method="linear_drift",
    fair_value_fallbacks=("depth_mid", "hybrid_wall_micro", "mid"),
    maker_edge=1.0,
    taker_edge=2.0,
    max_aggressive_size=20,                # required so strategy step is the binding cap
    quote_size=10,
    inventory_skew=2.0,
    flatten_threshold=0.7,
    history_length=32,
)
```

### PEPPER strategy — `PepperCoreLongStrategy` with V3_nearhold CoreLongParams

```python
_V3_NEARHOLD_CORE_LONG_PARAMS = CoreLongParams(
    base_long=80,
    add_thresh=3.0,
    trim_thresh=8.0,
    add_gain=5.0,
    trim_gain=2.0,
    floor=40,
    ceiling=80,
    step=8,
    exec_style='taker',
    hybrid_threshold=2.0,
    maker_edge_offset=0.0,
    open_seed_size=65,
    open_window=500,
    open_no_short=True,
)
```

**These values match EXACTLY** the canonical V3_nearhold config in
`outputs/round_1/pepper_sparse_overlay/shortlist.md` §2 and
`final_recommendation.md` §1. Every layer past L1 was inert on the
one official day's data — `floor=40`, `trim_thresh=8`, `trim_gain=2`,
`step=8`, and `hybrid_threshold=2` are chosen for sensible behavior
on unseen days rather than for on-day optimality.

**Key differences from V2_clean:**

| Param | V2_clean | V3_nearhold | Effect |
|---|---|---|---|
| `base_long` | 50 | **80** | Default rest state is the position limit, not a mid-level target |
| `floor` | 0 | **40** | Never flatten past 40 long; protect core carry |
| `open_seed_size` | 60 | **65** | Slight spread-saving edge at tick 0 (seed=65 beats seed=80 by +72 proxy PnL) |
| `open_window` | 1000 | **500** | Shorter window (step=8 fills 65 in ~8 ticks; 500 is sufficient) |
| `trim_thresh` | 5.0 | **8.0** | Trims only on rich-price excursions |
| `trim_gain` | 1.0 | **2.0** | When a trim fires, it's decisive (but still bounded by floor=40) |
| `exec_style` | 'hybrid' | **'taker'** | Taker-first for reload; hybrid tied on proxy but taker is conceptually cleaner for a directional family |

All other params identical.

## Search evidence

The V3_nearhold config is the winner of the
`pepper_sparse_overlay` search:

- Proxy PEPPER PnL: **+7 351.0** (vs V2_clean proxy +5 472.5 and buy_hold_80 proxy +7 279.0)
- First-25k PEPPER: **+1 571** (vs V2_clean +1 204, buy_hold +1 594)
- First-50k PEPPER: **+3 451** (vs V2_clean +2 758, buy_hold +3 474)
- Avg PEPPER position: **+79.0** (vs V2_clean ~+55, buy_hold +79.9)
- Max long: **+80**, max short (first-half): **0**, near-limit: **998/1000**

Proxy-to-official calibration for seeded / directional candidates is
1:1 (V2_clean proxy 5 472.5 vs official 5 426 = 1.009×; buy_hold_80
proxy 7 279 vs official 7 286 = 0.999×). Projected V3_nearhold
official PEPPER: **≈ +7 350 ± ~50** (and ± single-day noise band of
±~300).

## What this bundle does NOT modify

- No shipped `round1_*_engine_config` factory other than adding
  `round1_v3_nearhold_engine_config()` (same pattern as V2_clean).
- Shipped `STRATEGY_REGISTRY` unchanged (still
  `{buy_and_hold, market_making}` — the bundle extends it in its
  own tail appendix).
- Shipped `KNOWN_STRATEGY_NAMES` unchanged (still
  `(buy_and_hold, market_making)` — the bundle extends it in the
  same appendix).
- All six pre-existing submission bundles under
  `outputs/submissions/round_1/limit_80/*.py` (baseline, promoted,
  alt, h1, f5, test, v2_clean) are unchanged; SHAs unchanged.

## Changes to enable this export

1. `src/core/config.py` — **added** factory
   `round1_v3_nearhold_engine_config()` (same pattern as
   `round1_v2_clean_engine_config()`).
2. `src/scripts/round_1/export_round1_v3_nearhold.py` — **new**
   export script (copy of the V2_clean export script with the
   V3_nearhold params and banner swapped in; the minifier, wiring
   appendix, and validator-cap handling are byte-identical to the
   V2_clean pipeline).

Zero changes to `src/trader.py`, `src/strategies/*`, tests, or the
live exporter.

## Validation summary

```
Validation target: outputs/submissions/round_1/limit_80/trader_round1_v3_nearhold.py
Size: 90946 bytes (soft 98304, hard 102400, 93% of soft / 89% of hard)
Issues: 0 error(s), 0 warning(s)
Result: OK
```

## Runtime smoke test

- `Trader().config.product_config('INTARIAN_PEPPER_ROOT').position_limit == 80` ✓
- `Trader().config.product_config('ASH_COATED_OSMIUM').position_limit == 80` ✓
- `Trader().config.product_config('INTARIAN_PEPPER_ROOT').strategy_name == 'pepper_core_long'` ✓
- `Trader().config.product_config('INTARIAN_PEPPER_ROOT').max_aggressive_size == 20` ✓
- `type(Trader().strategies['pepper_core_long']).__name__ == 'PepperCoreLongStrategy'` ✓
- V3_nearhold `CoreLongParams` pinned on the strategy instance — all 14 fields verified ✓
- At `t=0`: PEPPER orders include aggressive crosses at the best ask
  (`(12006, +10), (12009, +10)`) — the opening seed fires ✓
- Full proxy run via `outputs/round_1/pepper_sparse_overlay/run_search.py`
  infra: V3 config reproduces **+7 351.0 PEPPER, avg_pos +79.0,
  end-of-bucket positions [80, 80, 80, 80]** ✓

## Test suite

Full pytest run: **498 passed, 0 failed** at commit `043faac`.

## Upload instruction

Upload this file EXACTLY as-is to IMC Prosperity. Do NOT edit. If
you need to regenerate, run the exporter — do NOT hand-edit.

See `docs/round_1/upload_plan.md` for the recommended upload order
(V3_nearhold is the current next upload, after V2_clean).
