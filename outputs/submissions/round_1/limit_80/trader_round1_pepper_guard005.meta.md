# pepper_guard005 submission bundle — metadata

Companion record for `outputs/submissions/round_1/limit_80/trader_round1_pepper_guard005.py`.

## Summary

- Label: Round-1 PEPPER guarded carry (defensive)
- Purpose: Most reversal-defensive PEPPER guarded-carry candidate. Uses the same level-1 opening core as the balanced bundle, but triggers the flat guard earlier at slope <= 0.005.
- Expectation: Expect the strongest protection on shallow/noisy negative PEPPER regimes, with a bit more risk of de-risking on temporary dips.
- Source commit: `9ea0d43`
- SHA256: `c3dd5dbf4cb650727708c3f23ea09918b32caaf3fa863e27cd433010dbb57e6a`
- Size: `75499` bytes
- Exporter: `src.scripts.round_1.export_round1_pepper_guard005`

## PEPPER CoreLongParams

```python
_PEPPER_GUARD005_CORE_LONG_PARAMS = CoreLongParams(
    base_long=80,
    add_thresh=3.0,
    trim_thresh=8.0,
    add_gain=5.0,
    trim_gain=2.0,
    floor=0,
    ceiling=80,
    step=8,
    exec_style='taker',
    hybrid_threshold=2.0,
    maker_edge_offset=0.0,
    open_seed_size=65,
    open_window=500,
    open_no_short=True,
    open_take_mode='level1_only',
    guard_window=32,
    guard_negative_slope=0.005,
    guard_r2_min=0.0,
    guard_target=0,
    micro_residual_threshold=0.0,
    micro_imbalance_threshold=1.0,
    micro_add_size=0,
    micro_trim_size=0,
    adaptive_caps_enabled=False,
    adaptive_r2_min=0.0,
    adaptive_mid_slope=0.0,
    adaptive_high_slope=0.0,
    adaptive_low_cap=0,
    adaptive_mid_cap=0,
    adaptive_high_cap=0
)
```

## Validation

```text
Validation target: /Users/abhinavgupta/Desktop/IMC/outputs/submissions/round_1/limit_80/trader_round1_pepper_guard005.py
Size: 75499 bytes (soft 73728, hard 98304, 102% of soft / 77% of hard)
Issues: 0 error(s), 1 warning(s)
  [WARN] size_approaching_limit (-): bundled file is 75499 bytes, above soft budget of 73728 bytes (hard budget 98304 bytes); trim the live path before the hard ceiling is hit
Result: OK
```
