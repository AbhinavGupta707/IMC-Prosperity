# pepper_guard01 submission bundle — metadata

Companion record for `outputs/submissions/round_1/limit_80/trader_round1_pepper_guard01.py`.

## Summary

- Label: Round-1 PEPPER guarded carry (balanced)
- Purpose: Current best balanced PEPPER candidate for unseen data. Keeps the near-buy-and-hold carry core, uses level-1-only opening acquisition, and caps the target at flat when 32-step drift slope falls below 0.01.
- Expectation: Expect near-V3 real-day PEPPER carry with much better behavior on reversals and weaker negative-drift regimes.
- Source commit: `9ea0d43`
- SHA256: `75b6264e83a395007f6ee07d159b1c62aa01799bc630d987306163830cd077cb`
- Size: `75492` bytes
- Exporter: `src.scripts.round_1.export_round1_pepper_guard01`

## PEPPER CoreLongParams

```python
_PEPPER_GUARD01_CORE_LONG_PARAMS = CoreLongParams(
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
Validation target: /Users/abhinavgupta/Desktop/IMC/outputs/submissions/round_1/limit_80/trader_round1_pepper_guard01.py
Size: 75492 bytes (soft 73728, hard 98304, 102% of soft / 77% of hard)
Issues: 0 error(s), 1 warning(s)
  [WARN] size_approaching_limit (-): bundled file is 75492 bytes, above soft budget of 73728 bytes (hard budget 98304 bytes); trim the live path before the hard ceiling is hit
Result: OK
```
