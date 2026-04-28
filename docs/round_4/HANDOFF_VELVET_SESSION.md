# Handoff - R4 VELVET / Voucher Complex Isolation

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

Task: maximize the VELVET underlying + voucher chain as one coupled options
book.

Research goals:

- Treat VELVET and `VEV_*` vouchers as one Greek-aware portfolio, not separate
  products.
- Audit static schedule thresholds by strike and day.
- Study blocked signals after position limits: which are true missed alpha and
  which are stale threshold traps?
- Build conservative recycling / take-profit rules that free capacity only
  when cross-day evidence supports it.
- Evaluate delta, gamma, vega, theta, drawdown, terminal exposure, and realized
  PnL.
- Continue `VEV_5500` work: `sellonly` with threshold 8 did not fill
  officially; `sell7` improves local replay and is the current best probe.

Important evidence so far:

- Official 100k: `disabled` and `sellonly` both beat `flat995` by +1,034.46
  entirely by avoiding bad `VEV_5500` buys.
- `sellonly` threshold 8 did not fill; `sell7` would have sold 300 at bid 7 in
  the official 100k window and local replay improves to about 886,964.
- Real validated `sell7` upload scored `68,655.81` full official JSON profit.
  Isolated VELVET/voucher PnL moved to `66,975.81`, with `VEV_5500` itself
  contributing `+1,034.45`.
- Plateau root cause: strategy reaches 99% final PnL by tick 41,900 and last
  fills at tick 51,600, then sits at limits.
- Official hindsight L1 oracle: actual about 67.6k, oracle about 138.7k. Largest
  gaps are VELVET, VEV_5100, VEV_5200, VEV_5300, VEV_5000.
- Naive symmetric recycler and naive gamma/smile probes failed; leave disabled.
- Ungated VELVET recycle and ungated long-only core-voucher recycling improve
  the day-3/official path but hurt historical days 1 and 2.
- Best next mechanism is a one-time early-selloff gate: activate only if
  VELVET is down at least 20 ticks from open by timestamp 30,000. This leaves
  historical days 1 and 2 unchanged and activates on day 3 / official 100k.
- Strongest official-proxy stack:
  `stack_officialmax_v5248_5264_core3_tp8`
  (`VELVET buy<=5248/sell>=5264` plus gated long-only `VEV_5000/5100/5200`
  recycler with take-profit 8, active_abs 280, floor_abs 240, max_order 20).
  Isolated official proxy: `70,108.5`, `+3,239.5` over `sell7_base`.
- Upload-probe bundle built and validator-clean:
  `/Users/abhinavgupta/Desktop/IMC/outputs/submissions/r4/submission_r4_exp_flat995_vev5500_sell7_stack_officialmax_probe.py`.
  Full bundled local replay smoke: `890,334` vs `886,964` for plain
  `sell7_validated`.
- Actual official `probe_stack` upload scored `71,997.24`, `+3,341.44` over
  validated `sell7`. Product attribution is `+2,806.44` VELVET underlying and
  `+535.00` from `VEV_5000/5100/5200`; HYDROGEL and `VEV_5500` were unchanged.
- This is a calibration win, not a final-1M proof. Public sliding 100k windows
  show the current VELVET gate fires in only `25 / 270` windows; when active,
  hit rate is `36%`, median delta is `0`, p10 is `-1,662.8`, and worst active
  window is `-4,262`.
- Current official top line `hardlong4060k` scored `72,057.90`, but this is a
  HYDROGEL timing win (`+5,471` HYD) while losing the validated `VEV_5500`
  `sell7` edge (`-2,068.90`). Next upload should test additivity:
  `hardlong4060k + sell7 VEV_5500`, then `hardlong4060k + probe_stack`.
- New VELVET-only upload ladder is built and validation-clean. The first four
  high-signal uploads are: one-shot VELVET max-alpha, matched cover-only
  negative control, `+80` long-cap terminal-risk dial, and delayed-gate robust
  candidate. The full eight-probe ladder also includes cover-to-flat,
  cover-to-`-100`, delayed cover-to-flat, and rolling-confirm diagnostics.
- Inventory-cap research did **not** make cap-to-flat the obvious final. The
  delayed full gate still has the best local sliding-window left tail (`worst
  active -536`) while keeping a positive official proxy (`+1,528.5`). Cap
  variants are useful controls for terminal exposure, not first-choice final
  candidates before official results.

Fresh reports:

- `/Users/abhinavgupta/Desktop/IMC/docs/round_4/VELVET_REGIME_GATE_PROBES.md`
- `/Users/abhinavgupta/Desktop/IMC/docs/round_4/LONG_ONLY_RECYCLER_PROBES.md`
- `/Users/abhinavgupta/Desktop/IMC/docs/round_4/STACKED_ALPHA_PROBES.md`
- `/Users/abhinavgupta/Desktop/IMC/docs/round_4/UPLOAD_PROBE_ROBUSTNESS.md`
- `/Users/abhinavgupta/Desktop/IMC/docs/round_4/VELVET_ROLLING_REGIME_SELECTED25K.md`
- `/Users/abhinavgupta/Desktop/IMC/docs/round_4/VELVET_INVENTORY_CAP_PROBES.md`
- `/Users/abhinavgupta/Desktop/IMC/docs/round_4/VELVET_UPLOAD_PROBE_LADDER.md`

Deliverable:

- A VELVET complex report with a strike-by-strike recommendation, one safe
  integrated candidate, and explicit reasons not to overfit to the 100k probe.
