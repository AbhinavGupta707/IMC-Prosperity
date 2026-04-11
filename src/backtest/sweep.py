from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from itertools import product

type GridValue = int | float | str | bool


def parameter_grid(grid: Mapping[str, Sequence[GridValue]]) -> Iterator[dict[str, GridValue]]:
    keys = list(grid)
    for values in product(*(grid[key] for key in keys)):
        yield dict(zip(keys, values, strict=True))
