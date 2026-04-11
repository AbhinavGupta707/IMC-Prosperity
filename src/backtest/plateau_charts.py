"""Phase 6 plateau visualisation.

Renders 2D pnl heatmaps from ``ParameterSweepReport`` objects. The
output is a nice-to-have diagnostic for the Phase 6 robustness note
— the core acceptance criteria (cross-slice plateau intersection,
promotion gate, per-slice incumbent baseline block) are driven by
``plateau.py`` and do not depend on heatmaps. If matplotlib is
missing or the axes are incompatible, ``render_plateau_heatmaps``
returns an empty list so the rest of Phase 6 still lands.

Follows the ``charts.py::_plt()`` lazy-import pattern so the live
trading path stays matplotlib-free.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.backtest.parameter_sweep import ParameterSweepReport, SweepValue

_DEFAULT_BAND_FRACTION = 0.10


def render_plateau_heatmaps(
    report: ParameterSweepReport,
    *,
    x_axis: str,
    y_axis: str,
    slice_name: str,
    out_dir: Path | str,
    band_fraction: float = _DEFAULT_BAND_FRACTION,
) -> list[Path]:
    """Render a 2D pnl heatmap for a single slice's sweep report.

    Rows are grouped by ``(x_axis, y_axis)`` and pnl is averaged
    across every other grid axis. Cells within the plateau band
    (within ``band_fraction`` of the post-filter peak on the
    averaged grid) are outlined in white. The baseline cell is
    highlighted with a red marker when both its axes fall on the
    grid.

    Non-blocking by design. Returns ``[]`` on matplotlib import
    failure, missing axes, or empty grids.
    """
    try:
        plt = _lazy_plt()
    except ImportError:
        return []

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    try:
        x_values, y_values, pnl_grid = _bucketed_pnl_grid(report, x_axis=x_axis, y_axis=y_axis)
    except ValueError:
        return []

    if not x_values or not y_values:
        return []

    # Matplotlib imshow accepts nested lists; masked cells are drawn as
    # the colormap's "bad" colour via NaN.
    display_grid = [
        [value if value is not None else float("nan") for value in row] for row in pnl_grid
    ]

    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    im = ax.imshow(
        display_grid,
        aspect="auto",
        origin="lower",
        cmap="viridis",
    )
    fig.colorbar(im, ax=ax, label="mean pnl (averaged over other axes)")

    ax.set_xticks(range(len(x_values)))
    ax.set_yticks(range(len(y_values)))
    ax.set_xticklabels([_format_axis_label(v) for v in x_values])
    ax.set_yticklabels([_format_axis_label(v) for v in y_values])
    ax.set_xlabel(x_axis)
    ax.set_ylabel(y_axis)
    ax.set_title(
        f"Phase 6 plateau heatmap: {report.product} / {slice_name}\n"
        f"fair_value_method={report.fair_value_method}"
    )

    averaged_values = [value for row in pnl_grid for value in row if value is not None]
    if averaged_values:
        peak_averaged = max(averaged_values)
        threshold = peak_averaged * (1.0 - band_fraction)
        for yi, _ in enumerate(y_values):
            for xi, _ in enumerate(x_values):
                value = pnl_grid[yi][xi]
                if value is None or value < threshold:
                    continue
                ax.add_patch(
                    plt.Rectangle(
                        (xi - 0.48, yi - 0.48),
                        0.96,
                        0.96,
                        fill=False,
                        edgecolor="white",
                        linewidth=1.2,
                    )
                )

    baseline_x = report.baseline.params.get(x_axis)
    baseline_y = report.baseline.params.get(y_axis)
    if baseline_x in x_values and baseline_y in y_values:
        ax.scatter(
            x_values.index(baseline_x),
            y_values.index(baseline_y),
            color="red",
            marker="o",
            s=80,
            label="baseline",
            edgecolors="black",
            linewidths=0.8,
        )
        ax.legend(loc="upper right", framealpha=0.8)

    target = out_path / f"{slice_name}_{x_axis}_x_{y_axis}.png"
    fig.tight_layout()
    fig.savefig(target, dpi=150)
    plt.close(fig)
    return [target]


def _lazy_plt() -> Any:
    """Lazy matplotlib import pinned to the Agg backend.

    Mirrors ``src/backtest/charts.py::_plt`` so Phase 6 heatmaps keep
    the live trading path matplotlib-free.
    """
    import matplotlib

    matplotlib.use("Agg", force=False)
    import matplotlib.pyplot as plt

    return plt


def _format_axis_label(value: object) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _bucketed_pnl_grid(
    report: ParameterSweepReport,
    *,
    x_axis: str,
    y_axis: str,
) -> tuple[list[SweepValue], list[SweepValue], list[list[float | None]]]:
    """Build a 2D mean-pnl grid keyed by ``(x_axis, y_axis)``.

    Raises ``ValueError`` if either axis is missing from every row.
    """
    if not any(x_axis in row.params for row in report.rows):
        raise ValueError(f"axis {x_axis!r} missing from sweep report")
    if not any(y_axis in row.params for row in report.rows):
        raise ValueError(f"axis {y_axis!r} missing from sweep report")

    x_values = sorted(
        {row.params[x_axis] for row in report.rows if x_axis in row.params},
        key=_axis_sort_key,
    )
    y_values = sorted(
        {row.params[y_axis] for row in report.rows if y_axis in row.params},
        key=_axis_sort_key,
    )

    buckets: dict[tuple[SweepValue | None, SweepValue | None], list[float]] = {}
    for row in report.rows:
        key = (row.params.get(x_axis), row.params.get(y_axis))
        buckets.setdefault(key, []).append(row.pnl)

    grid: list[list[float | None]] = []
    for y_value in y_values:
        row_values: list[float | None] = []
        for x_value in x_values:
            samples = buckets.get((x_value, y_value))
            row_values.append(sum(samples) / len(samples) if samples else None)
        grid.append(row_values)
    return x_values, y_values, grid


def _axis_sort_key(value: object) -> tuple[int, object]:
    # Numeric axes sort numerically; categorical axes fall back to repr
    # so heatmap axes remain deterministic across runs.
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return (0, float(value))
    return (1, repr(value))
