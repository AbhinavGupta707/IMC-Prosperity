# pepper_v5_micro submission bundle — metadata

Companion record for `outputs/submissions/round_1/limit_80/trader_round1_pepper_v5_micro.py`.

## Summary

- Label: Round-1 PEPPER guarded carry + micro timing overlay
- Purpose: Research PEPPER bundle built on the balanced 0.01 guarded-carry core with a tiny residual+imbalance timing overlay. This is the current best candidate for any incremental PEPPER alpha beyond the carry core.
- Expectation: Expect slightly less real-day PEPPER carry than the balanced guarded bundle, but somewhat better behavior on flat / high-vol / late-reversal synthetic regimes.
- Source commit: `9ea0d43`
- SHA256: `0bccaf6eaab9cdd01343b45064e745f1b10da696772f31258717b3e5a25a3cd4`
- Size: `75498` bytes
- Exporter: `src.scripts.round_1.export_round1_pepper_v5_micro`

## PEPPER CoreLongParams

```python
_PEPPER_V5_MICRO_CORE_LONG_PARAMS = CoreLongParams(
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
    guard_negative_slope=0.01,
    guard_r2_min=0.0,
    guard_target=0,
    micro_residual_threshold=3.0,
    micro_imbalance_threshold=0.3,
    micro_add_size=2,
    micro_trim_size=2,
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
Validation target: /Users/abhinavgupta/Desktop/IMC/outputs/submissions/round_1/limit_80/trader_round1_pepper_v5_micro.py
Size: 75498 bytes (soft 73728, hard 98304, 102% of soft / 77% of hard)
Issues: 0 error(s), 1 warning(s)
  [WARN] size_approaching_limit (-): bundled file is 75498 bytes, above soft budget of 73728 bytes (hard budget 98304 bytes); trim the live path before the hard ceiling is hit
Result: OK
```
