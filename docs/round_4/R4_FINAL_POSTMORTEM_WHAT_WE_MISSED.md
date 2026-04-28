# Round 4 Final Postmortem: What We Missed

Final submitted candidate:
`submission_r4_final_probe_stack_hyd_abortgate18_long80_60.py`

Official final result: `143,528`.

## Final Attribution

| Sleeve | Final PnL |
|---|---:|
| HYDROGEL_PACK | 56,870 |
| VELVETFRUIT_EXTRACT | 9,699 |
| VEV_4000-5200 | 80,981 |
| VEV_5300+ wings | -4,022 |

All final positions were flat. The terminal-risk control worked.

## The Main Miss

The final path did not reward Mark38 or the HYD target-120 bet. On a replay
of the final official path, `hyd120_nomark` behaved the same as the clean
abortgate80 candidate, while Mark38 variants were slightly worse under Kevin
matching. The real missed upside was a VELVET/options regime controller.

The final PnL path had four large negative 100k buckets:

| Bucket | Delta |
|---:|---:|
| 400k-500k | -41,697 |
| 500k-600k | -14,022 |
| 700k-800k | -40,814 |
| 900k-1000k | -19,777 |

Negative buckets summed to about `-116k`. Avoiding only the two worst
drawdowns would have put the same broad strategy near `226k`, before adding
any new edge.

## Hindsight Opportunity

Execution-aware independent-product oracle on the final book path:

| Product | Our PnL | Taker Oracle | Capture |
|---|---:|---:|---:|
| HYDROGEL_PACK | 56,870 | 267,240 | 21% |
| VEV_5100 | 23,435 | 240,637 | 10% |
| VEV_5000 | 19,428 | 226,856 | 9% |
| VELVETFRUIT_EXTRACT | 9,699 | 210,863 | 5% |
| VEV_5200 | 6,941 | 183,464 | 4% |

This is not an attainable target, but it shows where the missing 60k+ lived:
dynamic HYD cycling and near-ATM VELVET/options timing, not deep wings or Mark
IDs.

## Research Mistake

We identified the right next step in
`VELVET_ALPHA_FRONTIER_AND_ACTION_PLAN.md`: rolling intraday regime state,
capacity reservation, Greek/target-inventory controllers, and kill logic.
We did not finish that line of research. Instead we spent marginal time on
Mark38/Mark55/Mark22 integrations after the official evidence was already
showing that direct Mark alpha was small or fill-model-dependent.

## What Would Have Helped

1. A rolling VELVET/options state machine:
   - exit/reduce long delta after underlying drawdown from recent peak;
   - re-enter only after rebound/hysteresis;
   - reserve capacity instead of pinning all core vouchers at max position.

2. Portfolio-level delta/gamma control:
   - treat VELVET + VEV_4000-5200 as one convex portfolio;
   - cap net positive delta during downtrends;
   - use VELVET underlying as a hedge, not just another directional leg.

3. Full-day regime stress:
   - official 100k was not representative of final 1M;
   - public full-day bucket drawdowns should have been used as first-class
     acceptance criteria;
   - candidates should have been scored on drawdown avoidance, not just final
     PnL.

4. Better HYD cycle extraction:
   - HYD produced 56.9k, but the oracle showed a much larger repeat-cycle
     opportunity;
   - the high-regime debate was less important than robust mean-reversion
     cycling across the whole day.

## Bottom Line

The final candidate was a good robust choice among the candidates we had. The
reason it did not reach 200k+ is that we validated a broad static/regime stack
but did not turn it into a dynamic intraday portfolio controller. The missing
edge was mostly avoiding bad exposure during VELVET/options drawdowns and
recycling HYD more efficiently, not discovering one more Mark rule.
