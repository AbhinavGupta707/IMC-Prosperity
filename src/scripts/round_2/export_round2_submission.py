"""Export Round-2 submission bundle: v5_micro PEPPER + wide-w113 ASH.

Final Round-2 submission. Combines the unchanged v5_micro PEPPER leg
(deterministic +80k/day annuity validated in batch C) with the
batch-D1 sweep winner ASH ladder (wide edges 3/5/8 + outer-heavy
weights 1:1:3, +20% over the R1 L1 baseline on the R2 tape).

The MAF auction bid is embedded via ``with_bid_value`` when ``--bid``
is set; defaults to 0 (abstain). Recommended bid per batch D3:
2 300 XIRECs (floor-EV-maximising under hierarchical opponent prior).

Usage::

    PYTHONPATH=. .venv/bin/python -m src.scripts.round_2.export_round2_submission --bid 2300

Outputs ``outputs/submissions/round_2/trader_round2_promoted.py``.
"""

from __future__ import annotations

import argparse
import ast
import re
from dataclasses import asdict
from pathlib import Path

from src.core.config import round2_v5micro_wide113_engine_config
from src.scripts.round_1._pepper_deep_bundle import (
    PepperBundleSpec,
    PepperInline,
    build_bundle,
)
from src.strategies.pepper_core_long import V5_MICRO_PARAMS

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "submissions" / "round_2"

# PEPPER leg uses the canonical v5_micro CoreLongParams (defined in
# src/strategies/pepper_core_long.py). Kill switches NOT enabled —
# batch D2 confirmed they are redundant with the strategy's own
# guard machinery on this stack.

# Wide-w113 ASH ladder — batch-D1 sweep winner. Edges (3, 5, 8),
# outer-heavy weights (1, 1, 3), skew_coef=1.0, flatten=0.7.
# +20% over the R1 L1 baseline on the R2 tape.
_WIDE_W113_ASH_PARAMS: dict[str, object] = {
    "edges": (3.0, 5.0, 8.0),
    "size_mults": (1.0, 2.0, 3.0),
    "weights": (1, 1, 3),
    "skew_coef": 1.0,
    "flatten_threshold": 0.7,
}

_ASH_INLINE = PepperInline(
    strategy_module_path="src/strategies/ash_ladder.py",
    strategy_class_name="AshLadderStrategy",
    params_class_name="LadderParams",
    new_strategy_name="ash_ladder",
    params_dict=_WIDE_W113_ASH_PARAMS,
)

_PEPPER_INLINE = PepperInline(
    strategy_module_path="src/strategies/pepper_core_long.py",
    strategy_class_name="PepperCoreLongStrategy",
    params_class_name="CoreLongParams",
    new_strategy_name="pepper_core_long",
    params_dict=asdict(V5_MICRO_PARAMS),
)


def _spec(bid_value: int) -> PepperBundleSpec:
    """Build a bundle spec parameterised on the embedded MAF bid."""
    bid_phrase = (
        f"; MAF bid = {bid_value} XIRECs (Round-2 only)" if bid_value else ""
    )
    return PepperBundleSpec(
        variant="round2_promoted",
        factory_name="round2_v5micro_wide113_engine_config",
        factory=round2_v5micro_wide113_engine_config,
        label="Round-2 promoted: v5_micro PEPPER + wide-w113 ASH ladder",
        purpose=(
            "Final Round-2 submission. v5_micro PEPPER (R1 winner; +80k/day "
            "deterministic annuity validated on R2 in batch C) + wide-w113 "
            "ASH ladder (batch-D1 sweep winner, +20% over L1 baseline on R2)"
            f"{bid_phrase}."
        ),
        ash_inline=_ASH_INLINE,
        pepper_inline=_PEPPER_INLINE,
    )


def _wrap_factory_call_with_bid(source: str, factory_name: str, bid_value: int) -> str:
    """Post-process the bundle to wrap the factory call with `with_bid_value`.

    The shared `build_bundle` helper produces a bundle with the line
    ``self.config = config or {factory_name}()``. To embed a non-zero
    MAF bid, we wrap that call as
    ``with_bid_value({factory_name}(), {bid})``. ``with_bid_value`` is
    already exported from `src.core.config` and bundled into the file.
    """
    if bid_value == 0:
        return source
    if bid_value < 0:
        raise ValueError(f"bid_value must be >= 0 (got {bid_value})")
    pattern = (
        rf"self\.config = config or {re.escape(factory_name)}\(\)"
    )
    replacement = (
        f"self.config = config or with_bid_value({factory_name}(), {bid_value})"
    )
    new_source, n = re.subn(pattern, replacement, source, count=1)
    if n != 1:
        raise RuntimeError(
            f"Could not find the factory call line for {factory_name!r} in the "
            "bundle source — bundle layout has changed; update this script."
        )
    return new_source


def _ast_compress(source: str) -> str:
    """Strip module-level docstrings to keep the bundle under budget."""
    tree = ast.parse(source)

    def _strip_string_exprs(body: list[ast.stmt]) -> list[ast.stmt]:
        out: list[ast.stmt] = []
        for node in body:
            if (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                continue
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                node.body = _strip_string_exprs(node.body)
            out.append(node)
        return out

    tree.body = _strip_string_exprs(tree.body)
    return ast.unparse(tree).rstrip() + "\n"


def _bid_value_arg(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError(
            f"--bid must be >= 0 (IMC normalises negatives to 0; got {parsed})"
        )
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--bid",
        type=_bid_value_arg,
        default=0,
        help=(
            "Round-2 MAF bid (XIRECs). 0 abstains from the auction. "
            "Recommended: 2300 (per batch D3 hierarchical opponent model)."
        ),
    )
    args = parser.parse_args(argv)
    output_path = export_variant_to_path(out_dir=args.out_dir, bid_value=args.bid)
    size_kb = output_path.stat().st_size / 1024
    try:
        rel = output_path.relative_to(REPO_ROOT)
    except ValueError:  # out_dir lives outside the repo (e.g. a tmp dir in tests)
        rel = output_path
    print(
        f"[{_spec(args.bid).variant}] wrote {rel} "
        f"({size_kb:.1f} KB, bid={args.bid})"
    )
    return 0


def export_variant_to_path(*, out_dir: Path, bid_value: int = 0) -> Path:
    """Export the Round-2 promoted bundle to ``out_dir`` and return the path.

    Public API used by both the CLI ``main`` entry point and the
    end-to-end integration test in ``tests/test_round2_export_e2e.py``.

    The bundler always passes ``redact_params=True`` so the upload
    banner does not publish our exact strategy parameters — the
    actual values are still in the inlined strategy classes below
    the banner, so trading behaviour is unchanged.
    """
    if bid_value < 0:
        raise ValueError(f"bid_value must be >= 0 (got {bid_value})")
    spec = _spec(bid_value)
    source, _ = build_bundle(spec, redact_params=True)
    source = _wrap_factory_call_with_bid(source, spec.factory_name, bid_value)
    compressed = _ast_compress(source)

    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"trader_{spec.variant}.py"
    output_path.write_text(compressed, encoding="utf-8")
    return output_path


if __name__ == "__main__":
    raise SystemExit(main())
