# Handoff - R4 HYDROGEL Isolation

We are working on IMC Prosperity Round 4. Ignore manual challenge.

Main repo:
`/Users/abhinavgupta/Desktop/IMC`

Readable R4 official simulator logs:
`/Users/abhinavgupta/Desktop/IMC/r4 Sim Results/`

R4 historical data, if not copied into main repo, is readable in scratch:
`/tmp/imc-r4-counterparty-audit/data/raw/round_4/`

Current Phase 1 report:
`/Users/abhinavgupta/Desktop/IMC/docs/round_4/PHASE_1_CURRENT_STRATEGY_ANATOMY.md`

Current R4 candidates:
`/Users/abhinavgupta/Desktop/IMC/outputs/submissions/r4/`

Task: maximize HYDROGEL in isolation from first principles.

Research goals:

- Explain current HYDROGEL alpha: static mean-reversion around 9988/9995,
  terminal flatten at 995k, official 100k outlier regime.
- Evaluate PnL, max drawdown, inventory path, final position, and hidden-FV
  sensitivity.
- Test robust families, not random tweaks: static fair/width, EWMA fair,
  regime-aware trend/fade, volatility bands, terminal flatten/cap timing.
- Use 3 historical 1M R4 days plus official 100k logs as calibration, not as
  overfit targets.
- Compare against current `safer_hydflat995`.

Important evidence so far:

- `flat995` costs about 3,589 local PnL versus unguarded control but reduces
  terminal HYDROGEL residual from about +128 to +12.
- Official 100k HYDROGEL is an outlier high-mean window; do not re-anchor to it
  blindly.
- Official hindsight oracle shows HYDROGEL has a large dynamic gap, but that is
  not directly tradable.

Deliverable:

- A concise HYDROGEL research report with one recommended safe candidate and
  one or two official-calibration probes, if justified.

