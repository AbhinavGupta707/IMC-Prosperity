"""Manual-round toolkit.

A parallel workstream to the algorithmic trader: reusable solvers and
priors for the five problem families that recur every Prosperity season.

Families:

1. Graph / path arbitrage           -> :mod:`graph_arbitrage`
2. Bid optimization (single agent)  -> :mod:`bid_optimizer`
3. Game-theoretic crowding          -> :mod:`nash_crowd`
4. Hybrid bid + average-bid penalty -> :mod:`hybrid_bid`
5. News-driven integer portfolio    -> :mod:`news_portfolio`

Priors for opponent / crowd modelling live in :mod:`priors`.
Submission-note generator lives in :mod:`submission_note`.

See ``src/manual_rounds/README.md`` for worked examples from P1, P2, P3.
"""

from __future__ import annotations
