# Round 4 Mark Thread - Initial Findings

Date: 2026-04-27

## Question

Can buyer/seller IDs become a primary alpha source, or should they be used only
as modifiers on the existing schedule/inventory logic?

Current answer: Mark IDs are real, but the evidence still favors modifier use,
not standalone trading.

## Evidence Standards

We need to keep three claims separate:

1. A Mark is directionally informed in raw markouts.
2. We can observe the Mark, react after delay, cross the spread, and still win.
3. The Mark identity should alter an already-good schedule fill or inventory
   decision.

Historical raw markouts support claim 1 for some cells. Prior actionable tests
mostly reject claim 2. Claim 3 is still open and is the right next research
path.

## Historical Actionable Audit

Prior script:

`/tmp/imc-r4-counterparty-audit/src/research/round_4/audit_mark_actionable.py`

Model:

- observe Mark event at timestamp `T`;
- earliest reaction is `T + 100`;
- cross the target product touch;
- exit after fixed horizon;
- choose direction on training days and evaluate held-out day.

Result:

- No high-confidence Mark cell passed the desired 3/3 holdout standard after
  delay and spread.
- The top rows had only 2 positive holdouts and/or weak minimum test edge.
- This rejects standalone aggressive-cross Mark wrappers under tested rules.

## Historical Raw Signals That Look Real

The residual table still shows some stable raw patterns:

- `Mark 67` buying `VELVETFRUIT_EXTRACT`: positive short-horizon residual across
  all 3 historical days.
- `Mark 49` selling `VELVETFRUIT_EXTRACT`: similar short-horizon positive
  residual.
- `Mark 22` selling `VEV_5200/5300`: some longer-horizon positive residual.
- `Mark 14` / `Mark 38` patterns in HYDROGEL and `VEV_4000` are large, but
  heavily role-structured and can invert depending on whether we look from
  aggressor, passive, or target-product perspective.

These are useful as state variables. They are not yet standalone strategies.

## Official 100k Live Check

Using `r4 Sim Results/sellonly/497595.log`, non-submission Mark aggressor
markouts show:

- `Mark 67` buying VELVET is positive at 100, 500, 1k, and 5k horizons, but
  sample is tiny and flips negative by 10k/30k.
- `Mark 55` VELVET flow is mostly adverse at short horizons. Its sell prints
  become positive at longer horizons, which looks more like regime drift than
  clean ID alpha.
- `Mark 38` HYDROGEL aggressor flow is strongly negative in the official slice.
- `Mark 22` OTM voucher sells are weakly negative in `VEV_5400/5500/6000/6500`
  but small-positive in `VEV_5300` at 5k/10k.

This is not enough to justify a standalone Mark overlay.

## Our Official Fills By Counterparty

Our fills are mostly with `Mark 01`, `Mark 14`, and some `Mark 38`.

At 1k/5k horizons, our fill markouts by counterparty are generally negative
because we cross the spread and often enter during adverse short-horizon
movement. At 30k/50k horizons, many sell-side fills become strongly positive,
but this is the schedule/regime working, not clear counterparty selection.

Conclusion: counterparty ID does not explain the bulk of our official PnL.
The fixed schedule and inventory state do.

## Best Mark Research Path

Do not build a Mark-only trader yet.

Instead test Mark as conditional state input:

1. VELVET velocity modifier:
   - `Mark 67` buy / `Mark 49` sell / selected `Mark 55` flow as short-horizon
     regime evidence.
   - Candidate use: adjust VELVET hedge urgency or defer adverse schedule fills.

2. OTM voucher modifier:
   - `Mark 22` OTM sell flow may identify when low-strike/OTM voucher schedule
     should be more conservative.
   - Candidate use: reduce `VEV_5300/5400/5500` stale buy/rebuy behavior.

3. HYDROGEL modifier:
   - Mark HYDROGEL patterns are large but role-confounded.
   - Candidate use only after HYDROGEL isolation finds a base regime model.

## Next Test

Build a Mark-conditioned schedule audit:

- Start from existing schedule fill/blocked-signal events.
- Attach recent Mark event features over trailing windows:
  - product,
  - side,
  - mark,
  - signed qty,
  - time since event.
- Ask whether Mark features predict which schedule fills or blocked signals have
  positive markout after spread.
- Evaluate by leave-one-day-out on historical days, then compare to official
  100k as calibration only.

Status: completed in
`/Users/abhinavgupta/Desktop/IMC/docs/round_4/MARK_CONDITIONED_SCHEDULE_AUDIT.md`.

Core result: the strongest Mark evidence is conditional and short-horizon. The
best historical gate is `Mark 22` selling VELVET as an active conditioner for
VELVET/VEV_5000/VEV_5100 sell-side schedule quality. Official 100k calibration
is mixed and strike/horizon dependent, so this should become a small recycler or
micro-probe, not a broad Mark overlay.

Additional groundwork from the IMC counterparty hint is in
`/Users/abhinavgupta/Desktop/IMC/docs/round_4/MARK_BEHAVIOR_CLASSIFICATION.md`.
The major update is role classification: `Mark 14`/`Mark 01` are robust
maker-like/passive participants, `Mark 55`/`Mark 38` are taker-like, and
`Mark 22` is a broad OTM voucher basket seller. Role is more stable than raw
directional markout.
