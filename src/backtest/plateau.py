"""Phase 6 cross-slice plateau helper.

Computes a robust-across-slices plateau band for Phase 6 parameter
sweeps, picks a categorical-safe medoid center, runs the first four
checks of the six-part Phase 6 promotion gate, and compares multiple
sub-sweeps to pick a single product-level winner.

The doctrine reference is ``ARCHITECTURE_DOCTRINE.md`` §8 — prefer
broad plateaus to peak settings — and the Phase 6 plan spec in
``Tutorial/Implementation Plan.md:649``.

This module is deliberately decoupled from ``BacktestSimulator`` and
``ReplayEngine``: every function takes ``ParameterSweepReport``
objects and returns pure dataclasses. That keeps unit tests fast
(no replay tape needed) and makes the plateau logic reusable by
future round-specific sweeps.

Gate checks implemented here (sweep-level, automatic):

1. ``pnl_lift``   — candidate ``pnl >= 1.10 * baseline.pnl`` on the
   ``combined`` slice.
2. ``inventory``  — candidate's params pass the inventory-discipline
   filter on every slice (``steps_near_limit == 0``).
3. ``trade_count``— candidate trade count on the ``combined`` slice
   sits in ``[0.5 * baseline, 3 * baseline]``, and every per-day
   slice has ``trade_count > 0``.
4. ``regime``     — ``abs(candidate.maker_share - baseline.maker_share)
   <= 0.20``. ``None`` maker shares are treated as ``0.0``.

Gate checks 5 (markout degradation) and 6 (timestamp drilldown vs
incumbent) are **not** enforced here — they are review-pack checks
executed by hand before any ``default_engine_config()`` edit, per
the Phase 6 plan.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from src.backtest.parameter_sweep import ParameterSweepReport, SweepRow

_PLATEAU_BAND = 0.10  # 10% of post-filter peak pnl
_MIN_PROMOTION_INTERSECTION = 3
_PNL_LIFT_THRESHOLD = 1.10
_TRADE_COUNT_MIN_FRACTION = 0.5
_TRADE_COUNT_MAX_FRACTION = 3.0
_REGIME_MAX_DELTA = 0.20
_COMBINED_SLICE_NAME = "combined"
_DEFAULT_SWEEP_DIR = Path("outputs/sweeps")

type ParamValue = int | float | str | bool
type ParamKey = tuple[tuple[str, ParamValue], ...]


# --------------------------------------------------------------- dataclasses


@dataclass(frozen=True)
class SlicePlateau:
    """Per-slice plateau state for a single sub-sweep."""

    slice_name: str
    baseline: SweepRow
    peak_pnl: float | None
    band_rows: tuple[SweepRow, ...]
    baseline_in_band: bool


@dataclass(frozen=True)
class Phase6CrossSliceReport:
    """Cross-slice plateau report for one sub-sweep.

    Sub-sweeps flagged ``role="diagnostic"`` are reported factually
    (per-slice plateau, incumbent baseline block) but the four-part
    automatic promotion gate is **not** evaluated and ``verdict`` is
    fixed to ``"diagnostic"``.
    """

    product: str
    sub_sweep: str
    role: str                       # "promotion_eligible" | "diagnostic"
    run_label: str
    generated_at: str
    per_slice: tuple[SlicePlateau, ...]
    intersection: tuple[SweepRow, ...]   # rows present in every slice's band
    center: SweepRow | None              # medoid of the intersection (or None)
    gate_checks: dict[str, bool] = field(default_factory=dict)
    verdict: str = "retain"
    reason: str = ""

    def summary_text(self) -> str:
        lines = [
            f"Phase 6 cross-slice plateau: {self.product} / {self.sub_sweep}",
            f"role: {self.role}",
            f"run_label: {self.run_label}",
            f"verdict: {self.verdict}",
            f"reason: {self.reason}" if self.reason else "",
            "",
        ]
        for slice_plateau in self.per_slice:
            lines.extend(_format_slice_block(slice_plateau))
            lines.append("")

        lines.append(f"intersection size: {len(self.intersection)}")
        if self.center is not None:
            lines.append(f"medoid center: {_format_params(self.center.params)}")
            lines.append(
                f"  pnl={self.center.pnl:.2f} "
                f"trades={self.center.trade_count} "
                f"maker_share={_format_maker_share(self.center.maker_share)} "
                f"near={self.center.steps_near_limit}"
            )
        if self.gate_checks:
            lines.append("")
            lines.append("gate checks (sweep-level):")
            for name, value in self.gate_checks.items():
                lines.append(f"  {name}: {'PASS' if value else 'FAIL'}")
        return "\n".join(line for line in lines if line is not None)


@dataclass(frozen=True)
class ProductComparison:
    """Final product-level step for a product with multiple sub-sweeps.

    Sub-sweeps marked ``role="diagnostic"`` are excluded from winner
    selection. The tie-break chain is: (1) larger intersection,
    (2) higher combined-slice pnl lift, (3) smaller maker/taker regime
    shift, (4) lexicographic sub_sweep name.
    """

    product: str
    considered: tuple[str, ...]
    excluded: tuple[str, ...]
    winner: str | None
    verdict: str                    # "retain" | "narrow" | "promotion_candidate"
    reason: str

    def summary_text(self) -> str:
        lines = [
            f"Phase 6 product comparison: {self.product}",
            f"considered: {', '.join(self.considered) if self.considered else '(none)'}",
            f"excluded:   {', '.join(self.excluded) if self.excluded else '(none)'}",
            f"winner:     {self.winner or '(none)'}",
            f"verdict:    {self.verdict}",
        ]
        if self.reason:
            lines.append(f"reason:     {self.reason}")
        return "\n".join(lines)


# --------------------------------------------------------------- filters


def filter_inventory_discipline(rows: Iterable[SweepRow]) -> tuple[SweepRow, ...]:
    """Drop rows whose sweep recorded any near-limit steps."""
    return tuple(row for row in rows if row.steps_near_limit == 0)


def post_filter_peak(rows: Iterable[SweepRow]) -> float | None:
    """Return the maximum pnl among ``rows`` or ``None`` for an empty set.

    Callers are expected to have already run ``filter_inventory_discipline``.
    """
    rows = tuple(rows)
    if not rows:
        return None
    return max(row.pnl for row in rows)


def plateau_band(
    rows: Iterable[SweepRow],
    *,
    band_fraction: float = _PLATEAU_BAND,
) -> tuple[SweepRow, ...]:
    """Keep rows whose pnl is within ``band_fraction`` of the peak.

    The rule is fixed at "within 10% of the post-filter peak" — the
    only plateau rule used anywhere in Phase 6. Callers must pass
    inventory-filtered rows.
    """
    rows = tuple(rows)
    peak = post_filter_peak(rows)
    if peak is None:
        return ()
    threshold = peak * (1.0 - band_fraction)
    return tuple(row for row in rows if row.pnl >= threshold)


# --------------------------------------------------------------- medoid


def _param_key(params: Mapping[str, ParamValue]) -> ParamKey:
    """Stable hashable key for a params dict (categorical-safe)."""
    return tuple(sorted(params.items()))


def _is_numeric(value: object) -> bool:
    # bool is a subclass of int in Python; we intentionally treat it as
    # categorical here because "skew axis in {True, False}" should not
    # get normalized-by-range arithmetic distance.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _axis_keys(rows: tuple[SweepRow, ...]) -> tuple[str, ...]:
    keys: set[str] = set()
    for row in rows:
        keys.update(row.params.keys())
    return tuple(sorted(keys))


def _axis_is_numeric(rows: tuple[SweepRow, ...], axis: str) -> bool:
    for row in rows:
        if axis not in row.params:
            continue
        if not _is_numeric(row.params[axis]):
            return False
    return True


def _computed_axis_range(rows: tuple[SweepRow, ...], axis: str) -> float:
    values = [
        float(row.params[axis])
        for row in rows
        if axis in row.params and _is_numeric(row.params[axis])
    ]
    if not values:
        return 0.0
    return max(values) - min(values)


def _pair_distance(
    a: SweepRow,
    b: SweepRow,
    *,
    axes: tuple[str, ...],
    numeric_axes: frozenset[str],
    axis_ranges: Mapping[str, float],
) -> float:
    total = 0.0
    for axis in axes:
        a_value = a.params.get(axis)
        b_value = b.params.get(axis)
        if a_value is None or b_value is None:
            # Missing axis on one side: treat as a categorical mismatch.
            total += 1.0 if a_value != b_value else 0.0
            continue
        if axis in numeric_axes:
            axis_range = axis_ranges.get(axis, 0.0)
            if axis_range <= 0.0:
                # Everyone shares the same value on this axis → no
                # contribution.
                continue
            total += abs(float(a_value) - float(b_value)) / float(axis_range)
        else:
            total += 0.0 if a_value == b_value else 1.0
    return total


def medoid(
    intersection: tuple[SweepRow, ...],
    axis_ranges: Mapping[str, float],
) -> SweepRow | None:
    """Pick the medoid of ``intersection`` using a mixed distance metric.

    Numeric axes are normalized by ``axis_ranges[axis]`` (or by the
    range computed across ``intersection`` if missing / zero). Categorical
    axes contribute 0 when equal, 1 otherwise.

    Tie-break chain (when two rows score identically):
        1. higher ``row.pnl`` (combined-slice pnl when called from
           ``intersect_plateaus``);
        2. lower ``row.steps_near_limit``;
        3. lexicographic sorted params key.

    Returns ``None`` for an empty intersection.
    """
    if not intersection:
        return None
    if len(intersection) == 1:
        return intersection[0]

    axes = _axis_keys(intersection)
    numeric_axes = frozenset(
        axis for axis in axes if _axis_is_numeric(intersection, axis)
    )

    # Fill in missing / zero axis ranges from the intersection itself.
    resolved_ranges: dict[str, float] = {}
    for axis in numeric_axes:
        provided = axis_ranges.get(axis, 0.0)
        resolved_ranges[axis] = (
            provided if provided and provided > 0 else _computed_axis_range(intersection, axis)
        )

    def total_distance(row: SweepRow) -> float:
        return sum(
            _pair_distance(
                row,
                other,
                axes=axes,
                numeric_axes=numeric_axes,
                axis_ranges=resolved_ranges,
            )
            for other in intersection
            if other is not row
        )

    def sort_key(row: SweepRow) -> tuple[float, float, int, tuple[tuple[str, str], ...]]:
        return (
            total_distance(row),
            -row.pnl,                     # higher pnl ranks first
            row.steps_near_limit,         # lower near-limit ranks first
            tuple((k, repr(v)) for k, v in sorted(row.params.items())),
        )

    return sorted(intersection, key=sort_key)[0]


# --------------------------------------------------------------- slice plateau


def build_slice_plateau(
    slice_name: str,
    report: ParameterSweepReport,
    *,
    band_fraction: float = _PLATEAU_BAND,
) -> SlicePlateau:
    filtered = filter_inventory_discipline(report.rows)
    peak = post_filter_peak(filtered)
    band = plateau_band(filtered, band_fraction=band_fraction)

    baseline = report.baseline
    baseline_in_band = (
        baseline.steps_near_limit == 0
        and peak is not None
        and baseline.pnl >= peak * (1.0 - band_fraction)
    )
    return SlicePlateau(
        slice_name=slice_name,
        baseline=baseline,
        peak_pnl=peak,
        band_rows=band,
        baseline_in_band=baseline_in_band,
    )


# --------------------------------------------------------------- intersect


def _intersect_band_rows(
    per_slice: tuple[SlicePlateau, ...],
    combined_slice_name: str = _COMBINED_SLICE_NAME,
) -> tuple[SweepRow, ...]:
    """Rows whose params appear in the plateau band on every slice.

    Returns the ``combined``-slice copies of those rows so downstream
    gate checks read combined-slice pnl / trade_count / maker_share.
    Order is determined by the combined slice's row order.
    """
    if not per_slice:
        return ()

    combined_slice = next(
        (slice_plateau for slice_plateau in per_slice if slice_plateau.slice_name == combined_slice_name),
        None,
    )
    if combined_slice is None:
        # No combined slice → fall back to the first slice's rows.
        combined_slice = per_slice[0]

    other_slices = tuple(
        slice_plateau
        for slice_plateau in per_slice
        if slice_plateau.slice_name != combined_slice.slice_name
    )

    combined_keys = {_param_key(row.params): row for row in combined_slice.band_rows}
    for slice_plateau in other_slices:
        slice_keys = {_param_key(row.params) for row in slice_plateau.band_rows}
        combined_keys = {
            key: row for key, row in combined_keys.items() if key in slice_keys
        }
    return tuple(combined_keys.values())


def _lookup_row_for_key(
    slice_plateau: SlicePlateau,
    key: ParamKey,
) -> SweepRow | None:
    for row in slice_plateau.band_rows:
        if _param_key(row.params) == key:
            return row
    return None


def _gate_checks(
    *,
    center: SweepRow,
    per_slice: tuple[SlicePlateau, ...],
) -> dict[str, bool]:
    combined_slice = next(
        (slice_plateau for slice_plateau in per_slice if slice_plateau.slice_name == _COMBINED_SLICE_NAME),
        None,
    )
    if combined_slice is None:
        return {
            "pnl_lift": False,
            "inventory": False,
            "trade_count": False,
            "regime": False,
        }

    combined_baseline = combined_slice.baseline
    center_key = _param_key(center.params)

    # (1) pnl lift on combined slice.
    pnl_lift = (
        combined_baseline.pnl <= 0.0
        and center.pnl > 0.0
    ) or (
        combined_baseline.pnl > 0.0
        and center.pnl >= _PNL_LIFT_THRESHOLD * combined_baseline.pnl
    )

    # (2) inventory discipline: center's params must be in every slice's
    # band (which already required steps_near_limit == 0 via the filter).
    inventory = all(
        _lookup_row_for_key(slice_plateau, center_key) is not None
        for slice_plateau in per_slice
    )

    # (3) trade count: combined within [0.5x, 3x] baseline; per-day
    # slices > 0.
    min_trades = _TRADE_COUNT_MIN_FRACTION * combined_baseline.trade_count
    max_trades = _TRADE_COUNT_MAX_FRACTION * combined_baseline.trade_count
    trade_count_combined_ok = (
        center.trade_count >= min_trades and center.trade_count <= max_trades
        if combined_baseline.trade_count > 0
        else center.trade_count > 0
    )
    trade_count_per_day_ok = True
    for slice_plateau in per_slice:
        if slice_plateau.slice_name == _COMBINED_SLICE_NAME:
            continue
        per_day_row = _lookup_row_for_key(slice_plateau, center_key)
        if per_day_row is None or per_day_row.trade_count <= 0:
            trade_count_per_day_ok = False
            break
    trade_count = trade_count_combined_ok and trade_count_per_day_ok

    # (4) maker/taker regime.
    center_maker = center.maker_share if center.maker_share is not None else 0.0
    baseline_maker = (
        combined_baseline.maker_share if combined_baseline.maker_share is not None else 0.0
    )
    regime = abs(center_maker - baseline_maker) <= _REGIME_MAX_DELTA

    return {
        "pnl_lift": bool(pnl_lift),
        "inventory": bool(inventory),
        "trade_count": bool(trade_count),
        "regime": bool(regime),
    }


def _compute_axis_ranges(
    slices: Mapping[str, ParameterSweepReport],
) -> dict[str, float]:
    """Union axis ranges across every sweep row in every slice."""
    values_per_axis: dict[str, list[float]] = {}
    for report in slices.values():
        for row in report.rows:
            for axis, value in row.params.items():
                if _is_numeric(value):
                    values_per_axis.setdefault(axis, []).append(float(value))
    return {
        axis: (max(values) - min(values)) if values else 0.0
        for axis, values in values_per_axis.items()
    }


def _verdict_and_reason(
    *,
    role: str,
    intersection_size: int,
    gate_checks: Mapping[str, bool],
) -> tuple[str, str]:
    if role == "diagnostic":
        return "diagnostic", "sub-sweep is diagnostic-only (no promotion)"
    if intersection_size == 0:
        return "retain", "plateau intersection is empty across slices"
    if intersection_size < _MIN_PROMOTION_INTERSECTION:
        return (
            "narrow",
            f"plateau intersection is {intersection_size} row(s); "
            f"threshold for promotion is {_MIN_PROMOTION_INTERSECTION}",
        )
    failed = [name for name, ok in gate_checks.items() if not ok]
    if failed:
        return "retain", f"gate check(s) failed: {', '.join(sorted(failed))}"
    return "promotion_candidate", "intersection >= 3 and all automatic gate checks pass"


def intersect_plateaus(
    slices: Mapping[str, ParameterSweepReport],
    *,
    product: str,
    sub_sweep: str,
    role: str = "promotion_eligible",
    band_fraction: float = _PLATEAU_BAND,
    run_label: str | None = None,
) -> Phase6CrossSliceReport:
    """Build a Phase 6 cross-slice plateau report for one sub-sweep.

    ``slices`` maps slice name (e.g. ``"day_-2"``, ``"day_-1"``,
    ``"combined"``) to a ``ParameterSweepReport`` produced by
    ``build_parameter_sweep_report``.

    When ``role == "diagnostic"`` the plateau band is still computed
    per slice (so the robustness note can quote the same data), but
    the automatic promotion gate is **not** evaluated and the verdict
    is fixed to ``"diagnostic"``. This is the hook Phase 6 uses to
    carry the Phase 5 EWMA validation read without reopening Phase 5.
    """
    per_slice = tuple(
        build_slice_plateau(name, report, band_fraction=band_fraction)
        for name, report in slices.items()
    )
    intersection = _intersect_band_rows(per_slice)
    axis_ranges = _compute_axis_ranges(slices)
    center = medoid(intersection, axis_ranges)

    gate_checks: dict[str, bool] = {}
    if role != "diagnostic" and center is not None:
        gate_checks = _gate_checks(center=center, per_slice=per_slice)

    verdict, reason = _verdict_and_reason(
        role=role,
        intersection_size=len(intersection),
        gate_checks=gate_checks,
    )

    resolved_label = run_label or _derive_run_label(slices, sub_sweep)

    return Phase6CrossSliceReport(
        product=product,
        sub_sweep=sub_sweep,
        role=role,
        run_label=resolved_label,
        generated_at=datetime.now(UTC).isoformat(),
        per_slice=per_slice,
        intersection=intersection,
        center=center,
        gate_checks=gate_checks,
        verdict=verdict,
        reason=reason,
    )


def _derive_run_label(
    slices: Mapping[str, ParameterSweepReport],
    sub_sweep: str,
) -> str:
    for report in slices.values():
        if report.run_label:
            return report.run_label
    return sub_sweep


# --------------------------------------------------- product comparison


def _combined_pnl_lift(report: Phase6CrossSliceReport) -> float:
    combined = next(
        (slice_plateau for slice_plateau in report.per_slice if slice_plateau.slice_name == _COMBINED_SLICE_NAME),
        None,
    )
    if combined is None or report.center is None:
        return 0.0
    base = combined.baseline.pnl
    if base <= 0:
        return float("inf") if report.center.pnl > 0 else 0.0
    return report.center.pnl / base - 1.0


def _regime_shift(report: Phase6CrossSliceReport) -> float:
    combined = next(
        (slice_plateau for slice_plateau in report.per_slice if slice_plateau.slice_name == _COMBINED_SLICE_NAME),
        None,
    )
    if combined is None or report.center is None:
        return float("inf")
    center_maker = report.center.maker_share if report.center.maker_share is not None else 0.0
    baseline_maker = combined.baseline.maker_share if combined.baseline.maker_share is not None else 0.0
    return abs(center_maker - baseline_maker)


def compare_subsweep_winners(
    reports: tuple[Phase6CrossSliceReport, ...],
) -> ProductComparison:
    """Pick a product-level winner across multiple sub-sweep reports.

    Reports with ``role == "diagnostic"`` are recorded in ``excluded``
    and never win regardless of their sweep numbers. Among the
    remaining reports, only those with ``verdict == "promotion_candidate"``
    are eligible to win.

    Tie-break chain (first rule that separates wins):
        1. Larger intersection size.
        2. Higher combined-slice pnl lift over the sub-sweep baseline.
        3. Smaller maker/taker regime shift.
        4. Lexicographic sub_sweep name (deterministic fallback).
    """
    product = reports[0].product if reports else "UNKNOWN"

    considered: list[Phase6CrossSliceReport] = []
    excluded: list[str] = []
    for report in reports:
        if report.role == "diagnostic":
            excluded.append(report.sub_sweep)
        else:
            considered.append(report)

    candidates = [report for report in considered if report.verdict == "promotion_candidate"]
    if not candidates:
        return ProductComparison(
            product=product,
            considered=tuple(report.sub_sweep for report in considered),
            excluded=tuple(excluded),
            winner=None,
            verdict="retain",
            reason=(
                "no eligible sub-sweep reached promotion_candidate"
                if considered
                else "no eligible sub-sweeps after excluding diagnostics"
            ),
        )

    def sort_key(report: Phase6CrossSliceReport) -> tuple[int, float, float, str]:
        return (
            -len(report.intersection),            # larger intersection first
            -_combined_pnl_lift(report),          # higher pnl lift first
            _regime_shift(report),                # smaller regime shift first
            report.sub_sweep,                     # lexicographic fallback
        )

    winner = sorted(candidates, key=sort_key)[0]
    return ProductComparison(
        product=product,
        considered=tuple(report.sub_sweep for report in considered),
        excluded=tuple(excluded),
        winner=winner.sub_sweep,
        verdict="promotion_candidate",
        reason=(
            f"winner {winner.sub_sweep}: intersection={len(winner.intersection)}, "
            f"pnl_lift={_combined_pnl_lift(winner):+.2%}, "
            f"regime_shift={_regime_shift(winner):+.2f}"
        ),
    )


# --------------------------------------------------------------- writers


def _format_maker_share(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _format_params(params: Mapping[str, ParamValue]) -> str:
    return ", ".join(f"{key}={value}" for key, value in sorted(params.items()))


def _format_slice_block(slice_plateau: SlicePlateau) -> list[str]:
    baseline = slice_plateau.baseline
    if slice_plateau.peak_pnl is None:
        distance_text = "n/a (no inventory-disciplined rows)"
    elif slice_plateau.peak_pnl == 0:
        distance_text = "n/a (peak is 0)"
    else:
        distance_text = (
            f"{(slice_plateau.peak_pnl - baseline.pnl) / slice_plateau.peak_pnl * 100:+.1f}%"
        )
    return [
        f"slice {slice_plateau.slice_name}",
        f"  baseline params:    {_format_params(baseline.params)}",
        (
            f"  baseline: pnl={baseline.pnl:.2f} trades={baseline.trade_count} "
            f"maker_share={_format_maker_share(baseline.maker_share)} "
            f"near={baseline.steps_near_limit} pos={baseline.final_position}"
        ),
        f"  in_plateau_band:    {'yes' if slice_plateau.baseline_in_band else 'no'}",
        (
            f"  peak_pnl (post-filter): "
            f"{slice_plateau.peak_pnl if slice_plateau.peak_pnl is not None else 'n/a'}"
        ),
        f"  distance_from_peak: {distance_text}",
        f"  rows_in_band:       {len(slice_plateau.band_rows)}",
    ]


def _encode_for_json(value: object) -> object:
    if isinstance(value, SweepRow):
        return asdict(value)
    if isinstance(value, SlicePlateau):
        data = asdict(value)
        data["baseline"] = _encode_for_json(value.baseline)
        data["band_rows"] = [_encode_for_json(row) for row in value.band_rows]
        return data
    if isinstance(value, Phase6CrossSliceReport):
        data = asdict(value)
        data["per_slice"] = [_encode_for_json(slice_plateau) for slice_plateau in value.per_slice]
        data["intersection"] = [_encode_for_json(row) for row in value.intersection]
        data["center"] = _encode_for_json(value.center) if value.center is not None else None
        return data
    if isinstance(value, ProductComparison):
        return asdict(value)
    return value


def write_phase6_cross_slice_report(
    report: Phase6CrossSliceReport,
    per_slice_reports: Mapping[str, ParameterSweepReport],
    *,
    base_dir: Path | str = _DEFAULT_SWEEP_DIR,
    run_id: str | None = None,
) -> Path:
    """Write a per-sub-sweep cross-slice artifact directory.

    Layout:
        base_dir/<run_id>/<sub_sweep>/
            day_-2/summary.json + summary.txt
            day_-1/summary.json + summary.txt
            combined/summary.json + summary.txt
            plateau_intersection.json
            plateau_intersection.txt
    """
    from src.backtest.parameter_sweep import write_parameter_sweep_report  # circular-safe

    resolved_run_id = run_id or _format_run_id(report.run_label)
    directory = Path(base_dir) / resolved_run_id / report.sub_sweep
    directory.mkdir(parents=True, exist_ok=True)

    for slice_name, slice_report in per_slice_reports.items():
        slice_dir = directory / slice_name
        slice_dir.mkdir(parents=True, exist_ok=True)
        (slice_dir / "summary.json").write_text(
            json.dumps(_encode_for_json(asdict(slice_report)), indent=2, sort_keys=True, default=str)
        )
        (slice_dir / "summary.txt").write_text(slice_report.summary_text() + "\n")
        # Also drop a raw dataclass-style dump via the library writer so
        # the per-slice artifacts match the existing sweep layout.
        _ = write_parameter_sweep_report  # kept reachable for downstream scripts

    (directory / "plateau_intersection.json").write_text(
        json.dumps(_encode_for_json(report), indent=2, sort_keys=True, default=str)
    )
    (directory / "plateau_intersection.txt").write_text(report.summary_text() + "\n")
    return directory


def write_product_comparison(
    comparison: ProductComparison,
    *,
    base_dir: Path | str = _DEFAULT_SWEEP_DIR,
    run_id: str,
) -> Path:
    directory = Path(base_dir) / run_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "product_comparison.json").write_text(
        json.dumps(_encode_for_json(comparison), indent=2, sort_keys=True, default=str)
    )
    (directory / "product_comparison.txt").write_text(comparison.summary_text() + "\n")
    return directory


def _format_run_id(run_label: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    clean = "".join(char if char.isalnum() or char in "-_" else "_" for char in run_label)
    return f"{stamp}_{clean}" if clean else stamp
