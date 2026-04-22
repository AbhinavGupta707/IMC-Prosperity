# D1 — OBI / Flow IC Test

Tests whether top-of-book imbalance (OBI) and signed trade flow predict next-N-tick mid returns. |IC| > 0.03 indicates alpha the current reactive FairValueEngine cannot capture.

| Round | Product | Horizon | N | IC(OBI, Pearson) | IC(OBI, Spearman) | IC(Flow, Pearson) | IC(Flow, Spearman) |
|---|---|---|---|---|---|---|---|
| round_1 | ASH_COATED_OSMIUM | 10 | 27614 | +0.5205 | +0.5108 | — | — |
| round_1 | ASH_COATED_OSMIUM | 50 | 27494 | +0.3845 | +0.3630 | — | — |
| round_1 | ASH_COATED_OSMIUM | 100 | 27344 | +0.3173 | +0.3025 | — | — |
| round_1 | ASH_COATED_OSMIUM | 200 | 27044 | +0.2511 | +0.2402 | — | — |
| round_1 | ASH_COATED_OSMIUM | 500 | 26144 | +0.1937 | +0.1858 | — | — |
| round_1 | INTARIAN_PEPPER_ROOT | 10 | 27658 | +0.5662 | +0.6090 | — | — |
| round_1 | INTARIAN_PEPPER_ROOT | 50 | 27538 | +0.5453 | +0.5864 | — | — |
| round_1 | INTARIAN_PEPPER_ROOT | 100 | 27388 | +0.5071 | +0.5207 | — | — |
| round_1 | INTARIAN_PEPPER_ROOT | 200 | 27088 | +0.4011 | +0.3883 | — | — |
| round_1 | INTARIAN_PEPPER_ROOT | 500 | 26188 | +0.2166 | +0.2073 | — | — |
| round_2 | ASH_COATED_OSMIUM | 10 | 27678 | +0.5189 | +0.5083 | — | — |
| round_2 | ASH_COATED_OSMIUM | 50 | 27558 | +0.3824 | +0.3599 | — | — |
| round_2 | ASH_COATED_OSMIUM | 100 | 27408 | +0.3176 | +0.2985 | — | — |
| round_2 | ASH_COATED_OSMIUM | 200 | 27108 | +0.2431 | +0.2265 | — | — |
| round_2 | ASH_COATED_OSMIUM | 500 | 26208 | +0.1847 | +0.1727 | — | — |
| round_2 | INTARIAN_PEPPER_ROOT | 10 | 27694 | +0.5713 | +0.6097 | — | — |
| round_2 | INTARIAN_PEPPER_ROOT | 50 | 27574 | +0.5471 | +0.5917 | — | — |
| round_2 | INTARIAN_PEPPER_ROOT | 100 | 27424 | +0.5216 | +0.5436 | — | — |
| round_2 | INTARIAN_PEPPER_ROOT | 200 | 27124 | +0.4349 | +0.4208 | — | — |
| round_2 | INTARIAN_PEPPER_ROOT | 500 | 26224 | +0.2469 | +0.2353 | — | — |

## Interpretation

- **IC > 0.03:** signal has predictive power. Worth wiring into FairValueEngine as a predictive estimator component.
- **IC > 0.08:** strong signal — comparable to what top quant funds deploy on real markets. Priority build.
- **IC ~ 0:** signal has no edge in this regime; current reactive estimators are fine.
- **Spearman >> Pearson:** signal is monotonic but non-linear; use quantile-based feature rather than raw value.

## Implications for F1 / F5

F1 (observational-only FlowAnalyzer): confirmed a leak if |IC(Flow)| > 0.03.
F5 (all estimators reactive): confirmed a leak if |IC(OBI)| > 0.03.
