"""Sample synthetic order books from empirical historical distributions.

Approach: **historical book reanchoring.** At each tick, sample a
complete historical fact row from the same fractional-FV bucket as
the current synthetic FV, then translate its offsets to the new FV.

Why this beats per-rank parametric sampling:

  1. Preserves cross-rank correlation by construction (level1 above
     level2 above level3, never inverted).
  2. Preserves bid-ask spread distribution (sampling whole books
     keeps the bid-ask coupling).
  3. Captures asymmetric rounding (Bot 2's floor(fv+0.75) vs ceil(fv+0.25))
     because we condition on frac(fv).
  4. Captures multi-bot patterns (bimodal sub-bands) because they
     appear naturally in the historical sample.
  5. No model risk from formula incompleteness — the brute-force
     fitted bot rules are diagnostics, not generators.

Mathematical basis for reanchoring: for any bot rule of the form
``f(fv) + offset`` where f is integer-rounding-invariant in
``frac(fv)`` (true of round, floor, ceil), the price-minus-fv offset
is a function of ``frac(fv)`` only. So two FV values with the same
frac produce books with identical relative offsets. We sample within
a frac bucket and translate; the translation is exact at the bucket's
resolution.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from src.analysis.calibration.types import BookLevel, FactRow


@dataclass(frozen=True)
class BookSamplerStats:
    """Summary of a fitted sampler's bucket population."""

    n_buckets: int
    n_facts_total: int
    bucket_populations: tuple[int, ...]  # one per bucket
    empty_bucket_indices: tuple[int, ...]


class BookSampler:
    """Empirical-distribution sampler for per-tick order books.

    Initialize with the historical FactRows for one product, then call
    ``sample_book(fv=..., rng=...)`` per tick to draw a synthetic book.
    """

    def __init__(
        self,
        facts: Sequence[FactRow],
        *,
        n_frac_buckets: int = 10,
    ) -> None:
        if n_frac_buckets <= 0:
            raise ValueError(
                f"n_frac_buckets must be positive, got {n_frac_buckets}"
            )
        self._n_buckets = n_frac_buckets
        self._buckets: dict[int, list[FactRow]] = {}
        for fact in facts:
            bucket = _bucket_for(fact.server_fv, n_frac_buckets)
            self._buckets.setdefault(bucket, []).append(fact)
        self._all_facts = list(facts)
        if not self._all_facts:
            raise ValueError("BookSampler requires at least one FactRow")

    @property
    def stats(self) -> BookSamplerStats:
        populations = tuple(
            len(self._buckets.get(b, []))
            for b in range(self._n_buckets)
        )
        empty = tuple(
            b for b in range(self._n_buckets)
            if len(self._buckets.get(b, [])) == 0
        )
        return BookSamplerStats(
            n_buckets=self._n_buckets,
            n_facts_total=len(self._all_facts),
            bucket_populations=populations,
            empty_bucket_indices=empty,
        )

    def sample_book(
        self,
        *,
        fv: float,
        rng: np.random.Generator,
    ) -> tuple[tuple[BookLevel, ...], tuple[BookLevel, ...]]:
        """Sample a complete book (bids, asks) for the given FV.

        Picks a historical fact from the same frac(fv) bucket and
        re-anchors its level prices to the new FV. If the target
        bucket is empty, falls back to the nearest populated bucket
        (cyclically; abs-distance in bucket space).
        """
        bucket = _bucket_for(fv, self._n_buckets)
        candidates = self._buckets.get(bucket)
        if not candidates:
            candidates = self._nearest_populated_bucket(bucket)
        idx = int(rng.integers(0, len(candidates)))
        chosen = candidates[idx]
        return _reanchor(chosen, new_fv=fv)

    def _nearest_populated_bucket(self, target: int) -> list[FactRow]:
        """Find the populated bucket nearest to ``target`` in bucket-index space.

        Searches outward from ``target``: target+1, target-1, target+2, ...
        Wraps around the bucket index space cyclically (frac is
        circular: bucket 9 is adjacent to bucket 0 for n_buckets=10).
        """
        for distance in range(1, self._n_buckets + 1):
            for direction in (1, -1):
                candidate_bucket = (target + distance * direction) % self._n_buckets
                if candidate_bucket in self._buckets:
                    return self._buckets[candidate_bucket]
        # Should never reach here because constructor rejects empty input.
        raise RuntimeError("All buckets empty — sampler has no facts to draw from")


def _bucket_for(fv: float, n_buckets: int) -> int:
    """Map an FV to its fractional-part bucket index.

    Returns an int in [0, n_buckets). Uses positive-modulo so negative
    fractional parts (rare; happens only with negative FVs) bucket
    correctly.
    """
    f = fv - math.floor(fv)
    return min(int(f * n_buckets), n_buckets - 1)


def _reanchor(
    fact: FactRow, *, new_fv: float
) -> tuple[tuple[BookLevel, ...], tuple[BookLevel, ...]]:
    """Re-express a historical fact's levels at a new FV value.

    Each level's price-minus-FV offset is preserved. The new integer
    price is ``round(historical_price - historical_fv + new_fv)``. The
    rounding handles fractional-FV translation cleanly.
    """
    delta = new_fv - fact.server_fv
    new_bids = tuple(
        BookLevel(
            price=int(round(level.price + delta)),
            volume=level.volume,
        )
        for level in fact.bids
    )
    new_asks = tuple(
        BookLevel(
            price=int(round(level.price + delta)),
            volume=level.volume,
        )
        for level in fact.asks
    )
    return new_bids, new_asks
