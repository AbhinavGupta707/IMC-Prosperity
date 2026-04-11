"""Graph / path arbitrage solver.

Used in P2-R2 and P3-R1. Expected shape: an ``N x N`` rate matrix over a
small set of currencies, a bounded number of trades (often 5), and a
fixed start/end node. The answer is the sequence of hops that maximises
the multiplicative product of edge weights.

For the typical ``N=4, k=5`` problem the full enumeration is ``N^(k-1)
= 64`` paths, so brute force is both simpler and more auditable than
Bellman-Ford. This module enumerates paths directly, reports the top
results, and leaves graph-theoretic elegance at the door.

If future rounds scale to larger matrices, swap ``best_path`` for a
dynamic-programming variant (state = current node + hop index, memoised
on best accumulated product). The brute-force entry point is still
useful as a check against subtler implementations.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class RateMatrix:
    """Directed rate matrix over named currencies."""

    currencies: tuple[str, ...]
    rates: tuple[tuple[float, ...], ...]

    def __post_init__(self) -> None:
        n = len(self.currencies)
        if n == 0:
            raise ValueError("currencies must be non-empty")
        if len(set(self.currencies)) != n:
            raise ValueError("currencies must be unique")
        if len(self.rates) != n:
            raise ValueError("rates rows must match currency count")
        for row in self.rates:
            if len(row) != n:
                raise ValueError("rates must be square")
            if any(v < 0 for v in row):
                raise ValueError("rates must be non-negative")

    def index(self, currency: str) -> int:
        return self.currencies.index(currency)

    def rate(self, frm: str, to: str) -> float:
        return self.rates[self.index(frm)][self.index(to)]

    @classmethod
    def from_dict(
        cls,
        currencies: Sequence[str],
        rates: Mapping[tuple[str, str], float],
    ) -> RateMatrix:
        names = tuple(currencies)
        n = len(names)
        table = [[0.0] * n for _ in range(n)]
        for (frm, to), value in rates.items():
            if frm not in names or to not in names:
                raise ValueError(f"unknown currency in rate {frm}->{to}")
            i, j = names.index(frm), names.index(to)
            table[i][j] = value
        return cls(currencies=names, rates=tuple(tuple(row) for row in table))


@dataclass(frozen=True)
class Path:
    hops: tuple[str, ...]
    product: float

    def __post_init__(self) -> None:
        if len(self.hops) < 2:
            raise ValueError("path must have >= 2 nodes")


def _enumerate_paths(
    matrix: RateMatrix,
    start: str,
    end: str,
    max_hops: int,
    exclude_start: bool,
) -> list[Path]:
    """Enumerate every path from ``start`` to ``end`` with at most
    ``max_hops`` edges.

    ``exclude_start`` drops the trivial 0-hop path (just the start node).
    """
    if max_hops < 1:
        raise ValueError("max_hops must be >= 1")
    matrix.index(start)  # validates
    matrix.index(end)

    results: list[Path] = []

    def walk(node: str, product: float, chain: tuple[str, ...]) -> None:
        # Record any in-flight state that ends at ``end`` and has at
        # least 1 hop.
        if (
            node == end
            and len(chain) > 1
            and not (exclude_start and chain == (start, end))
        ):
            results.append(Path(hops=chain, product=product))
        if len(chain) - 1 == max_hops:
            return
        for nxt in matrix.currencies:
            edge = matrix.rate(node, nxt)
            if edge <= 0:
                continue
            walk(nxt, product * edge, (*chain, nxt))

    walk(start, 1.0, (start,))
    return results


def best_path(
    matrix: RateMatrix,
    start: str,
    end: str,
    max_hops: int = 5,
    top_k: int = 5,
) -> tuple[Path, tuple[Path, ...]]:
    """Return the best path and the top-``top_k`` alternatives.

    ``max_hops`` is the trade budget (P2-R2 and P3-R1 both used 5). The
    start and end nodes are usually the same (SeaShells). Paths are
    ranked by their multiplicative product.
    """
    paths = _enumerate_paths(matrix, start, end, max_hops, exclude_start=False)
    if not paths:
        raise ValueError(f"no path from {start!r} to {end!r} within {max_hops} hops")
    paths.sort(key=lambda p: p.product, reverse=True)
    return paths[0], tuple(paths[:top_k])


def all_paths(
    matrix: RateMatrix,
    start: str,
    end: str,
    max_hops: int = 5,
) -> tuple[Path, ...]:
    """Return every feasible path, sorted highest product first."""
    paths = _enumerate_paths(matrix, start, end, max_hops, exclude_start=False)
    paths.sort(key=lambda p: p.product, reverse=True)
    return tuple(paths)
