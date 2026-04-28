# VELVET Probe Ladder Upload Selection

Date: 2026-04-27

These files are valid generated submissions, but they are not all equal-value
uploads. The first official batch should be small and mechanism-focused.

## Upload Now

1. `01_max_alpha_velvet_one_shot.py`
   - Tests whether the official `probe_stack` gain survives without the
     fragile `VEV_5000/5100/5200` recycler.
   - Highest official proxy, but worse public sliding-window tail.

2. `02_cover_only_negative_control.py`
   - Required control.
   - If this scores close to #1, most of the VELVET gain is terminal
     short-cover exposure, not robust recycle/re-short alpha.

3. `06_delayed_gate50_full_recycle.py`
   - Best final-leaning candidate before official results.
   - Lower official proxy than #1, but much better public sliding-window
     left tail.

## Upload Only If The First Batch Is Ambiguous

4. `03_long_cap_plus80.py`
   - Upload if #1 wins and #2 is also strong, or if we need to reduce final
     terminal long risk while keeping most of the official upside.

5. `04_cover_to_flat.py`
   - Short-cover isolation. Useful only if #2 and #3 leave the mechanism
     unclear.

6. `05_cover_to_short100.py`
   - Reduce-only control. Lower priority than #4.

7. `07_delayed_cover_to_flat.py`
   - Looks conservative, but local tests did not make it cleaner than the
     delayed full gate.

8. `08_rolling_confirm_diagnostic.py`
   - Diagnostic only. Do not treat as a final candidate unless official
     results force a deeper rolling-regime investigation.

## Current Recommendation

Upload exactly #1, #2, and #3 first. Add #4 only if we want one extra
terminal-risk calibration upload in the same batch.
