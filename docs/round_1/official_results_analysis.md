# Round 1 — Official Results Analysis (Phase 7/8)

This memo interprets the three official IMC results against the
Phase-5 / Phase-6 local expectations, says what we learned, and
flags config-change recommendations for review (no automatic
promotions).

## What was uploaded

Files under `outputs/round_1/official_results/<variant>/`, one folder
per upload, each with the IMC submission `.py` (the file that ran
server-side), its `.json` results and `.log` trade history.

| Variant | Submission file (uploaded) | Our exported bundle | Byte-equivalence |
|---------|----------------------------|---------------------|------------------|
| Baseline | `Baseline/115117.py` (88 081 B) | `outputs/submissions/round_1/trader_round1_baseline.py` (88 082 B) | identical modulo a stripped trailing `\n` |
| Promoted | `Promoted/115254.py` (88 146 B) | `trader_round1_promoted.py` (88 147 B) | identical modulo trailing `\n` |
| Alt | `Alt/115380.py` (88 141 B) | `trader_round1_alt.py` (88 142 B) | identical modulo trailing `\n` |

Each uploaded file carries the "ROUND-1 UPLOAD VARIANT" banner with
factory name, build timestamp, and source commit (`b1fc5bf`). All
three banners match what was documented in
`docs/round_1/upload_plan.md`. Primary evidence below is taken from
the `.json` results; the `.py` files confirm what config actually
ran.

## What the official site reported

| Variant | Official total PnL | Final position (ASH) | Final position (PEPPER) | Trade count (ours) |
|---------|-------------------:|---------------------:|------------------------:|-------------------:|
| Baseline | **+2 276.15** | −8 | +1 | 137 |
| Promoted | **+2 518.11** | −21 | −2 | 121 |
| Alt | **+3 040.22** | −10 | +6 | 134 |

Per-product attribution (from `activitiesLog` cumulative
`profit_and_loss` on the last snapshot; sums to total exactly):

| Variant | ASH PnL | PEPPER PnL | ASH trades | PEPPER trades | Avg spread captured · ASH | Avg spread captured · PEPPER |
|---------|--------:|-----------:|-----------:|--------------:|--------------------------:|------------------------------:|
| Baseline | **+832** | **+1 444** | 89 | 48 | +3.73 | +12.55 |
| Promoted | +721 | +1 797 | 80 | 41 | +3.96 | **+19.61** |
| Alt | **+983** | **+2 057** | 89 | 45 | **+4.39** | +17.15 |

(Trade-count and avg-spread from `tradeHistory`; "avg spread captured"
= mean sell price − mean buy price.)

## Local vs official — the scale gap

The official Round-1 run covered **1 day × 1 000 snapshots**
(timestamps 0–99 900 at step 100). The local replay covered **3 days
× 10 000 snapshots each = 30 000 snapshots** — an order of magnitude
more trading opportunities.

Mechanically this means we should expect official PnL ≈ local PnL /
30 if strategies scaled linearly with snapshot count:

| Variant | Local total | Local / 30 | Official | Official / (local / 30) |
|---------|------------:|-----------:|---------:|-------------------------:|
| Baseline | +23 719 | ≈ 790 | +2 276 | **2.88×** |
| Promoted | +60 462 | ≈ 2 015 | +2 518 | **1.25×** |
| Alt | +86 591 | ≈ 2 886 | +3 040 | **1.05×** |

The simpler configs punch above their scaled expectations; the more
aggressive configs come in closer to 1:1. The absolute gap between
Promoted and Baseline **shrinks dramatically** on the official run
(+1.11× vs local +2.55×).

## Ranking: local prediction vs official outcome

| Product | Local ranking | Official ranking | Match? |
|---------|---------------|------------------|--------|
| **Overall** | Alt > Promoted > Baseline | **Alt > Promoted > Baseline** | ✅ Order held |
| ASH | Alt (+7 747) > Baseline (+7 301) > Promoted (+6 447) | **Alt (+983) > Baseline (+832) > Promoted (+721)** | ✅ Order held |
| PEPPER | Alt (+78 844) > Promoted (+54 015) > Baseline (+16 418) | **Alt (+2 057) > Promoted (+1 797) > Baseline (+1 444)** | ✅ Order held |

**The qualitative ranking held on every axis.** This is the single
most important finding: the Phase-5 / Phase-6 selection logic
*correctly* identified the best-performing variant in aggregate AND
per product. The absolute gaps, however, are materially different.

## Where local expectations held

1. **Fair-value family for PEPPER is validated.** The official Day-0
   PEPPER mid ran from ≈11 999 at t=0 to ≈12 100 at t=99 900 —
   slope ≈ **+0.101 per timestamp** by OLS. That is exactly the
   +0.1-per-step intraday drift identified in Phase 1. `linear_drift`
   as the primary was the right call; so was the decision not to
   ship lagging estimators.
2. **Alt's PEPPER inventory leverage beats Promoted's on this day.**
   Alt captures +2 057 on PEPPER vs Promoted's +1 797 — the +14 %
   uplift predicted locally (+40 % locally compressed to +15 %
   officially) is directionally consistent.
3. **Baseline is the weakest.** As designed — baseline is a
   reference, not a contender. It's worst on both products with both
   ASH and PEPPER carrying the Phase-3 parameters verbatim.
4. **Fill direction is sensible.** All variants ended with small
   signed positions (ASH −8 to −21, PEPPER −2 to +6) rather than
   being pinned at the limit. The Phase-4 near-limit hand-wringing
   did not materialise over a single official day.
5. **PEPPER avg-spread-captured is rank-consistent.** Baseline
   (+12.55 per round-trip) < Alt (+17.15) < Promoted (+19.61). The
   wider-taker-edge variants trade less but capture a cleaner edge,
   exactly as Phase-4 Stage-B predicted.

## Where local expectations failed

1. **Promoted ASH underperforms Baseline ASH on the official run.**
   Promoted ASH (`ewma_mid`, `taker_edge=0.25`) = +721.
   Baseline ASH (`wall_mid`, `taker_edge=1.0`) = +832.
   Alt ASH (`wall_mid`, `taker_edge=0.5`) = +983. The "robust
   default" we promoted on Phase-5 review-pack diagnostics (cross-
   day variance, markout quality, zero near-limit) is the worst of
   the three on the official site.
   - **Trade count difference is the key:** Promoted ASH executes 80
     trades, Baseline 89, Alt 89. With `taker_edge=0.25` sitting
     inside the spread's imbalance band, the official fill model
     triggers ewma_mid-based takes less often than wall_mid-based
     ones. The higher per-trade spread-captured (+3.96 vs +3.73)
     cannot compensate for trading ~10 % less often.
   - Locally, `ewma_mid`'s tight quoting won on markout quality; in
     the official simulator the extra markout quality doesn't beat
     the extra fill count that `wall_mid` + `t=0.5-1.0` gets.
2. **Absolute PnL gap between variants is 3-5× smaller than local**
   replay predicted. Our local replay fill model is materially more
   generous than the official one, especially for aggressive taker
   trades — Alt's +40 % local uplift over Promoted shrinks to +20 %.
3. **Q1-Q2 PnL is flat for all variants** (cumulative PnL stays near
   zero for the first ~50 % of the official run). The PEPPER drift
   needs 30-50 steps of warm-up before `linear_drift` locks on; on
   a 1000-step run that warm-up is a much bigger fraction of the
   day than on a local 10 000-step run. Smaller `history_length`
   (16 rather than 32) might compress the warm-up, but this is a
   Phase-4.5 follow-up, not a Phase-8 mandate.

## What this says about the five subsystems

### Fair value

- `linear_drift` for PEPPER is **validated**. Slope and sign match
  the Phase-1 finding exactly. Keep it.
- `ewma_mid` for ASH underperforms `wall_mid` on the official site.
  Phase-5 review-pack reasons (variance, markouts, inventory
  hygiene) turned out to be less predictive of official PnL than
  raw trade count in this simulator.

### Fill behaviour

- The official fill model is clearly **less permissive of tight
  taker edges than our local replay**. ASH at `taker_edge=0.25`
  drops ~10 % of fills vs `taker_edge≥0.5`; locally that 10 % was
  roughly neutral. The official simulator penalises under-edged
  takers more than our Phase-3 fill model does.
- The spread-captured-per-trade numbers (+3.73 to +4.39 on ASH,
  +12.55 to +19.61 on PEPPER) are all **below** the local entry-
  edge numbers (+2.08 on ASH, +2.95 on PEPPER). Fully consistent
  with a less generous simulator; our local "entry edge" was
  optimistic by roughly a factor of 2.

### Inventory pressure

- Final positions are modest on every variant. None pinned to the
  limit. The Phase-4 / Phase-5 inventory-risk discussion (C-PEP-B
  spending 24 % of steps near the limit) **did not show up** on the
  official day, almost certainly because the run is 30× shorter
  than local and inventory never had time to accumulate. This is
  *evidence that the worry was overstated for a single-day run* —
  but it also *does not clear* Alt's config for multi-day
  deployment.

### Simulator mismatch

- Runtime scale: **official = 1 day × 1 000 snapshots; local = 3
  days × 10 000 snapshots**. Everything local was 30× larger. Any
  future local-vs-official PnL comparison must normalise for this
  first.
- Fill-model strictness is the second mismatch: the official site
  does not reward tight taker edges the way our Phase-3 fill model
  does.

### Whether the promoted candidate should remain promoted

- **Overall ranking:** Promoted > Baseline on official PnL — yes, it
  is doing its job as the robust middle option.
- **ASH level:** Promoted ASH actually **lost** to Baseline ASH on
  the official run. The ewma_mid + taker_edge=0.25 pairing is the
  concrete failure point.
- **PEPPER level:** Promoted PEPPER beats Baseline PEPPER by +353 on
  the official run; its parameter choices (linear_drift,
  taker_edge=2.0, flatten=0.7, history=32) are validated.
- **Bottom line:** the promoted *package* beat baseline, but one of
  its two legs (ASH) underperformed. Keep Promoted promoted for now
  — **but flag ASH for a config-level review** (see next section).

## Config-change recommendations — flagged, not applied

Per the workflow constraint ("do not change production config
automatically; flag for review"), the engine configs
(`round1_baseline_engine_config`, `round1_promoted_engine_config`,
`round1_alt_engine_config`) are **unchanged** by this memo. The
following are candidate changes for a *future* explicit promotion
decision:

1. **[Promoted ASH candidate swap — FLAGGED]**
   Change `round1_promoted_engine_config` ASH leg from
   `(ewma_mid, taker_edge=0.25, maker_edge=1.0)` to
   `(wall_mid, taker_edge=0.5, maker_edge=1.5)` (i.e., adopt Alt's
   ASH leg into Promoted). Evidence: Alt's ASH beats Promoted's ASH
   by +262 (+36 %) and Baseline's ASH by +151 (+18 %) on the single
   official day. It is the only config that is top-ranked on every
   comparison.
   **Risk of adopting:** one official data point; we would be
   throwing away cross-day variance robustness (28 vs 455 locally).
   **Counter-evidence needed before acting:** rerun Phase-5 review
   diagnostics with wall_mid as the PROMOTED ASH primary and
   confirm the cross-day variance penalty isn't disqualifying.
2. **[Promoted PEPPER — KEEP]** C1b's `(linear_drift h=32, t=2.0,
   flatten=0.7, skew=2.0)` beat baseline and lost to alt by only
   +15 %. Given one data point and C1b's much better inventory
   posture, do not promote Alt's PEPPER. Hold.
3. **[PEPPER history_length — FLAGGED for Phase-4.5]** Q1-Q2 flat
   PnL on the official 1000-step run suggests `history_length=32`
   may be too slow to warm up on short runs. Investigate `h=16` on
   an official-scale (1000-step) simulated replay before any
   change.
4. **[ASH strategy-level review — FLAGGED]** Phase-5 promoted
   `ewma_mid` over `wall_mid` based on local diagnostics that
   turned out to not predict official performance. Document this
   as a known meta-learning and apply it to Round 2: don't ship a
   primary that trades materially less frequently than the best
   taker-heavier baseline purely on markout quality — the official
   fill model may not reward that trade-off.

None of the above should be applied without another review pass.

## What the next optimisation pass should focus on

1. **Calibrate the local fill model to the official one.** The
   local replay was ~2× too generous on per-fill edge and produced
   ~40 % more PnL gap between aggressive and conservative configs
   than the official site. Start with the simplest calibration:
   derive the official day's trade prices vs mid from
   `tradeHistory` and compare to the local fill model's assumed
   prices.
2. **Run a 1-day (1 000-snapshot) local replay.** All local tooling
   currently runs the 3-day × 10k-snapshot sample. A shorter replay
   mirrors the official scale and would have exposed the ewma_mid
   warm-up vs trade-count trade-off earlier.
3. **Revisit ASH primary.** Given the ewma_mid underperformance, a
   Phase-4.5 sweep over wall_mid / ewma_mid / depth_mid at
   `taker_edge ∈ {0.5, 0.75, 1.0}` on the 1-day scale is the
   cheapest informative experiment.
4. **Do NOT start a new broad tuning pass yet.** The findings
   above are all from a single official data point. Scope any
   follow-up as a targeted calibration + one directed sweep; broad
   retuning on one sample is the anti-pattern the plan explicitly
   warns against.

## Whether Promoted stays promoted

**Yes — Promoted stays promoted, but conditionally.** The promoted
variant beat baseline on total PnL and on PEPPER specifically. The
ASH leg's underperformance is a flagged concern, not grounds for an
automatic swap.

If forced to pick today without any new data: keep Promoted as the
default. If one more official data point becomes available and the
ASH leg underperforms again, adopt Alt's ASH leg into Promoted (see
flagged change #1 above).

## Acceptance

| Criterion | Status |
|-----------|--------|
| Located the three official result files | ✅ (`outputs/round_1/official_results/{Baseline,Promoted,Alt}/*.json`, matching `.py` and `.log`) |
| Verified each uploaded `.py` matches the exported bundle | ✅ byte-identical modulo trailing newline |
| Parsed official PnL, per-product PnL, trades | ✅ |
| Compared rankings | ✅ order holds on every axis |
| Did NOT silently change production config | ✅ all config-change candidates flagged for review |
| Did NOT start a broad new tuning pass | ✅ next-step recommendations scoped as directed calibration only |
