# Round 3 Local Artifact Inventory

Date: 2026-04-26

This repo intentionally keeps large generated Round 3 research outputs on disk
but out of git history. The artifacts are ignored by `.gitignore` under
`outputs/round_3/**` and are preserved locally in:

- Main workspace: `/Users/abhinavgupta/Desktop/IMC/outputs/round_3/`
- Velvet worktree backup: `/Users/abhinavgupta/Desktop/IMC-r3-velvet-options/`

The Velvet worktree was not deleted. At the time of this inventory it remains
registered as a git worktree on branch `codex/r3-velvet-options`.

## Committed Artifacts

These are small or strategically important enough to keep in git:

- `ROUND_3/` — raw Round 3 price/trade CSVs and the round image.
- `docs/round_3/` — research notes, postmortems, memory docs, and transcripts.
- `src/scripts/round_3/` — Hydrogel and Velvet research runners.
- `src/engines/r3_velvet_options_engine.py`
- `src/engines/r3_velvet_options_factory.py`
- `src/strategies/round_3/velvet_options_rolling_iv.py`
- `outputs/submissions/submission_r3*.py` — upload candidates and final bundles.

## Local-Only Generated Outputs

The following directories are preserved locally but ignored by git:

| Path | Approx size | Purpose |
| --- | ---: | --- |
| `outputs/round_3/99553_analysis/` | local | Hydrogel official/run analysis |
| `outputs/round_3/9955v2_analysis/` | local | Hydrogel variant analysis |
| `outputs/round_3/Results/` | local | Official result zips/extractions |
| `outputs/round_3/discovery/` | local | Initial R3 cross-product discovery |
| `outputs/round_3/fallback_analysis/` | local | Hydrogel fallback analysis |
| `outputs/round_3/hydrogel_actual_strategy_sweep/` | local | Hydrogel official-like strategy sweep |
| `outputs/round_3/hydrogel_cycle_state_sweep/` | local | Hydrogel cycle/rebound research |
| `outputs/round_3/hydrogel_deep_dive/` | local | Hydrogel oracle/deep-dive outputs |
| `outputs/round_3/hydrogel_drawdown_sweep/` | local | Hydrogel drawdown controls |
| `outputs/round_3/hydrogel_family_sweep/` | local | Hydrogel family comparison |
| `outputs/round_3/hydrogel_full_round_sweep/` | local | Hydrogel full-1M proxy sweep |
| `outputs/round_3/hydrogel_regime_research/` | local | Hydrogel regime work |
| `outputs/round_3/hydrogel_runner_variant_sweep/` | local | Hydrogel runner variants |
| `outputs/round_3/hydrogel_terminal_cycle_sweep/` | local | Hydrogel terminal/cycle research |
| `outputs/round_3/latest_analysis/` | local | Latest official comparison outputs |
| `outputs/round_3/turn_regime_research/` | local | Hydrogel turn-regime work |
| `outputs/round_3/validation/20260424_200223/` | local | R3 validation run |
| `outputs/round_3/validation/20260424_201917/` | local | R3 validation run |
| `outputs/round_3/velvet_anchor_curve_research/` | ~1.8 MB | Velvet anchor/fair-curve research |
| `outputs/round_3/velvet_call_spread_arb_research/` | ~0.6 MB | Call-spread no-arb experiments |
| `outputs/round_3/velvet_cycle_core_research/` | ~5.3 MB | Stateful Velvet/options cycle prototypes |
| `outputs/round_3/velvet_final_pass_research/` | ~28 MB | Final-pass Velvet portfolio sweeps |
| `outputs/round_3/velvet_hybrid_profile_research/` | ~0.1 MB | Hybrid/fallback profile comparison |
| `outputs/round_3/velvet_new_family_research/` | ~1.6 MB | Additional Velvet family exploration |
| `outputs/round_3/velvet_official_testing_results/` | ~8.8 MB | Uploaded simulator result zips |
| `outputs/round_3/velvet_options_research/` | ~147 MB | First-principles option/IV/smile analysis |
| `outputs/round_3/velvet_options_sleeve_risk_sweep/` | ~24 MB | Option-sleeve risk sweeps |
| `outputs/round_3/velvet_options_sleeve_sweep/` | ~12 MB | Rolling-IV/cross-smile/package sweeps |
| `outputs/round_3/velvet_oracle_path_review/` | ~0.1 MB | Oracle/path review |
| `outputs/round_3/velvet_passive_maker_research/` | ~0.1 MB | Passive maker proxy |
| `outputs/round_3/velvet_smile_cached_research/` | ~0.03 MB | Cached smile residual attempts |
| `outputs/round_3/velvet_static_threshold_robustness/` | ~5.4 MB | Static threshold robustness research |
| `outputs/round_3/velvet_trade_event_research/` | ~14 MB | Trade-event/markout analysis |

## Cleanup Rule

Do not delete local-only outputs until either:

1. the important summaries have been promoted into `docs/round_3/`, or
2. a compressed external archive has been created and verified.

The current cleanup keeps them in place and only removes them from git status.
