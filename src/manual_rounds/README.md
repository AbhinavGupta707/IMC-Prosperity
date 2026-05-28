# manual_rounds/

Reusable solvers for the five recurring manual-round families in IMC
Prosperity. Each solver is small, dependency-free (stdlib only), and
heavily unit-tested against known answers from public Prosperity 2 and
3 writeups.

## Families

| # | Module | Family | Historical rounds |
|---|---|---|---|
| 1 | `graph_arbitrage` | Graph / path arbitrage | P2-R2, P3-R1 |
| 2 | `bid_optimizer` | Single-agent sealed bid | P2-R1 |
| 3 | `nash_crowd` | Game-theoretic crowding | P2-R3, P3-R2, P3-R4 |
| 4 | `hybrid_bid` | Bid with average-bid coupling | P2-R4, P3-R3 |
| 5 | `news_portfolio` | Integer QP with quadratic fee | P1-R4, P2-R5, P3-R5 |

Supporting modules:

- `priors` — crowd behaviour priors (uniform, Nash, concentrated,
  inverse, nice-number overlay, mixtures).
- `submission_note` — structured markdown renderer for the pre-submit
  review checklist.

## Workflow during a live round

1. **Classify** the round family in under 10 minutes. Pattern match
   against the table above. If it looks hybrid, pick the dominant
   family first.
2. **Pick the solver module.** Copy the worked example from this README
   into a notebook and edit the inputs.
3. **Solve the naive no-opponent version first.** For crowding, use
   `shares_override=uniform_prior(cells)`. For bidding, use the
   single-agent `optimize_two_bids`.
4. **Add the crowd / opponent model.** Run the Nash equilibrium or use
   `mix_priors` to model the population as a mixture.
5. **Sensitivity sweep.** Call `sensitivity_sweep` (crowding) or
   `optimize_hybrid` with multiple `mu` scenarios (bidding).
6. **Build a `SubmissionNote`.** Fill in the chosen answer, naive
   baseline, crowd-adjusted answer, failure mode, backup.
7. **Submit.**

## Worked examples

### Family 1 — P3-R1 FX arbitrage

```python
from src.manual_rounds.graph_arbitrage import RateMatrix, best_path

matrix = RateMatrix(
    currencies=("Snow", "Pizza", "SiNug", "Shell"),
    rates=(
        (1.00, 1.45, 0.52, 0.72),
        (0.70, 1.00, 0.31, 0.48),
        (1.95, 3.10, 1.00, 1.49),
        (1.34, 1.98, 0.64, 1.00),
    ),
)
best, top5 = best_path(matrix, start="Shell", end="Shell", max_hops=5)
# best.hops = ("Shell", "Snow", "SiNug", "Pizza", "Snow", "Shell")
# best.product ~= 1.089  # ~8.9% return
```

### Family 2 — P2-R1 goldfish

```python
from src.manual_rounds.bid_optimizer import LinearRampReserve, optimize_two_bids

dist = LinearRampReserve(low=900, high=1000)
best, top10 = optimize_two_bids(dist, resale_value=1000, bid_grid=list(range(900, 1001)))
# best.low_bid, best.high_bid == (952, 978)
```

Known trap: the EV-optimal answer is only ex-post optimal ~9% of the
time for a 5000-fish sample. Treat `top10` as alternatives worth
considering if your round scores on realised, not expected, PnL.

### Family 3 — P3-R2 containers

```python
from src.manual_rounds.nash_crowd import CrowdCell, CrowdPayoff, solve

cells = [
    CrowdCell("C1", 10, 1),  CrowdCell("C2", 80, 6),  CrowdCell("C3", 37, 3),
    CrowdCell("C4", 17, 1),  CrowdCell("C5", 31, 2),  CrowdCell("C6", 50, 4),
    CrowdCell("C7", 89, 8),  CrowdCell("C8", 73, 4),  CrowdCell("C9", 20, 2),
    CrowdCell("C10", 90, 10),
]
payoff = CrowdPayoff(base_treasure=10_000, coupling=100)
sol = solve(cells, payoff, pick_fees=(0, 50_000), max_picks=2)

# sol.best_by_size[1]  -- best free single pick under logit equilibrium
# sol.best_by_size[2]  -- best two-pick bundle (may not clear the 50k fee)
# sol.top_bundles       -- top-10 alternatives
```

### Family 3 with prior overlays

```python
from src.manual_rounds.priors import (
    mix_priors,
    proportional_to_ratio,
    uniform_prior,
    nice_number_overlay,
)

nash = sol.shares  # from the previous example
greedy = proportional_to_ratio(cells, exponent=2.0)  # "crowd chases best ratio"
mixed = mix_priors([(0.5, nash), (0.3, greedy), (0.2, uniform_prior(cells))])
overlaid = nice_number_overlay(cells, mixed, nice_cell_names=["C3"], boost=0.05)

from src.manual_rounds.nash_crowd import solve as resolve
biased = resolve(cells, payoff, pick_fees=(0, 50_000), max_picks=2,
                 shares_override=overlaid)
```

### Family 4 — P3-R3 bimodal flipper bids

```python
from src.manual_rounds.bid_optimizer import BimodalUniformReserve
from src.manual_rounds.hybrid_bid import HybridScenario, optimize_hybrid

dist = BimodalUniformReserve(low_a=160, high_a=200, low_b=250, high_b=320)
scenarios = [
    HybridScenario("mu=280", 280),
    HybridScenario("mu=287", 287),
    HybridScenario("mu=293", 293),
]
best, alts = optimize_hybrid(
    distribution=dist,
    resale_value=320,
    bid_grid=list(range(160, 321)),
    scenarios=scenarios,
    alpha=3.0,  # cubic penalty for P3-R3; P2-R4 used alpha=1.0
)
# best.low_bid near 200; best.high_bid in 285-305
```

### Family 5 — P3-R5 news portfolio

```python
from src.manual_rounds.news_portfolio import NewsPayoff, Product, solve

payoff = NewsPayoff(capital_per_unit=10_000, fee_coefficient=120, budget=100)
products = [
    Product("Haystacks",    -0.005, rationale="neutral news"),
    Product("Ranch Sauce",  -0.007, rationale="weak bearish"),
    Product("Cacti Needle",  0.020, rationale="mild bullish"),
    Product("Solar Panels",  0.015, rationale="positive industry note"),
    Product("Red Flags",     0.050, rationale="headline looks bearish but numbers bullish"),
    Product("VR Monocle",    0.010),
    Product("Quantum Coffee", 0.000),
    Product("Moonshine",     0.030),
    Product("Striped shirts", -0.010),
]
sol = solve(products, payoff)
# sol.positions[product_name]: integer % allocations
# sol.total_pnl: expected PnL under the sentiment estimates
# sol.binding: True if L1 budget is the binding constraint
```

### Submission note

```python
from src.manual_rounds.submission_note import SubmissionNote

note = SubmissionNote(
    round_name="P4-R2",
    family="crowding",
    chosen_answer="C6 (multiplier 50, inhabitants 4) — free single pick",
    payoff_explanation="10000 * M / (I + 100 * p), fee 50k for a 2nd pick",
    core_assumptions=[
        "Nash logit response at T=5000 describes ~60% of players",
        "Top-multiplier cells over-picked by ~20% above Nash",
    ],
    naive_baseline="C10 under uniform crowd = ~41k",
    crowd_adjusted="C6 at Nash EV ~40k",
    robustness_range="C6 stays best under mixtures of Nash+greedy+uniform",
    backup_answer="C5 (31x2) if C6 also over-picked",
    failure_mode="if 2nd pick fee drops, greedy C6+C5 bundle becomes better",
)
print(note.render())
```

## Testing

All modules come with regression tests. Some tests hard-code public
answers from past rounds (P2-R1 = `(952, 978)`, P3-R1 = `~1.089`) so
any silent breakage is loud.

```
pytest tests/test_manual_*.py
```

## Non-goals

- No web scraping of the IMC portal — manual rounds are solved offline.
- No Monte Carlo Nash for more than `k=1` picks per player. If a future
  round demands multi-pick Nash, extend `nash_crowd.logit_quantal_equilibrium`
  rather than reaching for SciPy.
- No reading of news PDFs. Sentiment -> `expected_return` is a human
  judgment; the solver only handles the optimisation once `r_i` is set.
