# V2_clean submission bundle — metadata

Companion record for
`outputs/submissions/round_1/limit_80/trader_round1_v2_clean.py`.
Source of truth for what is embedded in the V2_clean upload.

## File fingerprint

| Field | Value |
|---|---|
| Output file | `outputs/submissions/round_1/limit_80/trader_round1_v2_clean.py` |
| Size | **90 056 bytes** (~88 KiB) — minified, under IMC's 100 KiB upload cap |
| SHA256 | `c59781ec1fcd0b52a1a2f0ea30bee00a6307c271edcd794919a541b7a6e6f5e4` |
| Source commit | `043faac` (`043faac88e87eb1a41dfc5d1302d966a7906d947`) |
| Datamodel mode | `platform` (production) |
| Validator result | `OK` (0 errors, 0 warnings; 88 % of 100 KiB cap) |
| Exporter | `src.scripts.round_1.export_round1_v2_clean` (minifies before writing) |

## Size history

| Pass | Size | Note |
|---|---:|---|
| V2_clean (initial export, verbose) | 116 207 B | docstrings + comments intact; did not fit under IMC 100 KiB cap |
| V2_clean (minified — this file) | **90 056 B** | strategy logic byte-identical; docstrings + pure-comment lines stripped; 26 151 B saved (22.5 %) |

**Minification is docstring + comment stripping only.** No executable
code was altered. The bundle is functionally byte-identical to the
verbose version at runtime — the engine never introspects
`__doc__` or source comments. The minifier also preserves the
auto-generated top header and the V2_clean banner for on-disk
identification / audit trail.

Re-export with:

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_1.export_round1_v2_clean
shasum -a 256 outputs/submissions/round_1/limit_80/trader_round1_v2_clean.py
```

Re-exports at the same commit produce different SHAs because the
banner embeds `# Built : <UTC timestamp>`. Compare body-only (skip
the banner region) to verify semantic equality across re-exports.

## Position limits — confirmed

| Product | position_limit |
|---|---:|
| ASH_COATED_OSMIUM | **80** |
| INTARIAN_PEPPER_ROOT | **80** |

Verified at bundle-build time by the exporter (pulls from
`round1_v2_clean_engine_config()` → `_round1_engine_with` →
Round-1 base config → `position_limit=80` per product) AND verified
at runtime by the smoke test (`Trader().config.product_config(p).position_limit`
returns `80` for both products).

## Exact config composition

### ASH_COATED_OSMIUM — byte-identical to H1 / F5 / Alt

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
    quote_size=5,
    max_aggressive_size=10,
    # ... remaining fields carry Round-1 base defaults.
)
```

ASH leg is the frozen wall-based leg used by every variant that
clears ASH on the official day. The V2_clean pass did NOT explore
ASH; this leg is the input contract.

### INTARIAN_PEPPER_ROOT — V2_clean leg

```python
INTARIAN_PEPPER_ROOT = dict(
    position_limit=80,
    strategy_name="pepper_core_long",      # <-- routes to PepperCoreLongStrategy
    fair_value_method="linear_drift",
    fair_value_fallbacks=("depth_mid", "hybrid_wall_micro", "mid"),
    maker_edge=1.0,
    taker_edge=2.0,
    max_aggressive_size=20,                # <-- bumped from shipped 8 so `step` is the binding per-tick cap
    quote_size=10,
    inventory_skew=2.0,
    flatten_threshold=0.7,
    history_length=32,
    # early/asymmetric-taker fields unused (V2_clean doesn't need them)
)
```

The `max_aggressive_size=20` bump is REQUIRED — matches exactly what
the v2 search ran. Without it, the simulator's 8-per-tick cap would
dominate the strategy's `step=8` rate limit and the acquisition curve
would differ from the search.

### PEPPER strategy — `PepperCoreLongStrategy` with V2_clean CoreLongParams

```python
_V2_CLEAN_CORE_LONG_PARAMS = CoreLongParams(
    base_long=50,
    add_thresh=3.0,
    trim_thresh=5.0,
    add_gain=5.0,
    trim_gain=1.0,
    floor=0,
    ceiling=80,
    step=8,
    exec_style='hybrid',
    hybrid_threshold=2.0,
    maker_edge_offset=0.0,
    open_seed_size=60,
    open_window=1000,
    open_no_short=True,
)
```

**These values match EXACTLY** the V2_clean canonical row in
`outputs/round_1/pepper_corelong_v2/shortlist.md` §2 and
`outputs/round_1/pepper_corelong_v2/final_recommendation.md` §1.
See also `pepper_candidates.csv` row
`L3_s0_add_mid_trim_mid_size_medium` (the canonical V2_clean label;
5 sibling rows tied on every metric).

The strategy is NOT in the shipped `STRATEGY_REGISTRY`. The V2_clean
bundle inlines `src/strategies/pepper_core_long.py` at the bundle tail
and extends both `KNOWN_STRATEGY_NAMES` and `STRATEGY_REGISTRY` with
a factory that pins `_V2_CLEAN_CORE_LONG_PARAMS` — so
`strategy_name="pepper_core_long"` resolves correctly only inside
this bundle.

## What this bundle does NOT modify

- `round1_promoted_engine_config` / `round1_alt_engine_config` /
  `round1_h1_engine_config` / `round1_f5_engine_config` /
  `round1_test_engine_config` — untouched.
- Shipped `STRATEGY_REGISTRY` (`src/strategies/__init__.py`) —
  untouched (still `{"buy_and_hold", "market_making"}`).
- Shipped `KNOWN_STRATEGY_NAMES` (`src/core/config.py`) — untouched
  (still `("buy_and_hold", "market_making")`).
- Existing submission bundles under
  `outputs/submissions/round_1/limit_80/*.py` — all unchanged,
  SHAs unchanged (see `README.md` fingerprint table).

## Changes made to enable this export

Additive-only. No behavior changes to any existing bundle.

1. `src/core/config.py` — **added** factory
   `round1_v2_clean_engine_config()` (same pattern as
   `round1_f5_engine_config()`).
2. `src/scripts/validate_submission.py` — **retuned** caps to match
   the real IMC upload limit: soft `72→96 KiB`, hard `96→100 KiB`.
   Existing bundles (~97 KiB) now sit above the soft cap and emit
   the `size_approaching_limit` warning; none exceed the 100 KiB
   hard cap. (Briefly tried hard=120 KiB during V2_clean development
   under an incorrect IMC-ceiling assumption; reverted to 100 KiB
   once minification brought V2_clean under the real cap.)
3. `src/scripts/round_1/export_round1_v2_clean.py` — **new** export
   script. Reuses `build_submission_source()` and `strip_module()`
   from the live exporter; inlines the research-only
   `PepperCoreLongStrategy` at the bundle tail plus a wiring block
   that extends `KNOWN_STRATEGY_NAMES` and `STRATEGY_REGISTRY` with
   the V2_clean factory. Final step: minifies the assembled bundle
   (strips docstrings + comment-only lines + collapses blank
   runs) so the output fits under IMC's 100 KiB cap. No executable
   code is modified by the minifier.

Zero changes to `src/trader.py`, `src/strategies/__init__.py`,
`src/strategies/market_making.py`, `src/strategies/buy_and_hold.py`,
or `src/strategies/pepper_core_long.py` (the strategy source is
unchanged from the v2 search; the bundle just inlines it).

## Validation summary

```
Validation target: outputs/submissions/round_1/limit_80/trader_round1_v2_clean.py
Size: 90056 bytes (soft 98304, hard 102400, 92% of soft / 88% of hard)
Issues: 0 error(s), 0 warning(s)
Result: OK
```

Clean: 0 errors, 0 warnings. Fits under the real IMC ~100 KiB upload
cap with ~12 KiB of headroom.

## Runtime smoke test

The bundle was loaded with a stubbed `datamodel` module and exercised
by constructing a `Trader()` and calling `trader.run(state)` at
`timestamp=0` and `timestamp=10_000`. Observed:

- `Trader().config.product_config('INTARIAN_PEPPER_ROOT').position_limit == 80` ✓
- `Trader().config.product_config('ASH_COATED_OSMIUM').position_limit == 80` ✓
- `Trader().config.product_config('INTARIAN_PEPPER_ROOT').strategy_name == 'pepper_core_long'` ✓
- `Trader().config.product_config('INTARIAN_PEPPER_ROOT').max_aggressive_size == 20` ✓
- `type(Trader().strategies['pepper_core_long']).__name__ == 'PepperCoreLongStrategy'` ✓
- V2_clean `CoreLongParams` pinned on the strategy instance — all 14 fields verified ✓
- At `t=0`: PEPPER orders include aggressive crosses at the best ask
  (`(12006, +10), (12009, +10)`) — the opening seed fires ✓
- At `t=10_000` (past `open_window=1000`): PEPPER emits only the
  passive bid (no aggressive cross), consistent with post-opening
  behavior ✓

## Test suite

Full pytest run: **498 passed, 0 failed** at commit `043faac`.

## Upload instruction

Upload this file EXACTLY as-is to IMC Prosperity. Do NOT edit the
file. If you need a smaller bundle (for example if IMC rejects for
size), regenerate via the exporter — do NOT hand-edit.

See `docs/round_1/upload_plan.md` for recommended upload order.
