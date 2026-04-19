"""Export combined bundle: v5_micro PEPPER + L1 ASH ladder.

Projected total: v5_micro PEPPER (+7,315 official) + L1 ASH (+1,786
official) = +9,101. Both legs are individually verified on the IMC
leaderboard; this bundle combines them for the first time.

PEPPER leg: ``PepperCoreLongStrategy`` with guarded carry (guard_window=32,
guard_negative_slope=0.01, guard_target=0), level1_only opening,
micro residual+imbalance overlay (size 2). Best single-product
PEPPER score across all Round-1 uploads.

ASH leg: ``AshLadderStrategy`` with L1 params (edges 2.5/3.5/5,
weights 3/1/1). All-time high ASH score, tight-outer confirmed
across 3 Phase iterations (F3a → J2 → K2 → L1).

Usage::

    PYTHONPATH=. .venv/bin/python -m src.scripts.round_1.export_round1_combined_v5micro_l1
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import asdict
from pathlib import Path

from src.core.config import round1_combined_v5micro_l1_engine_config
from src.scripts.round_1._pepper_deep_bundle import (
    DEFAULT_OUT_DIR,
    PepperBundleSpec,
    PepperInline,
    build_bundle,
)
from src.strategies.pepper_core_long import V5_MICRO_PARAMS

_ASH_INLINE = PepperInline(
    strategy_module_path="src/strategies/ash_ladder.py",
    strategy_class_name="AshLadderStrategy",
    params_class_name="LadderParams",
    new_strategy_name="ash_ladder",
    params_dict={
        "edges": (2.5, 3.5, 5.0),
        "size_mults": (1.0, 1.5, 2.0),
        "skew_coef": 2.0,
        "flatten_threshold": 0.7,
        "weights": (3, 1, 1),
    },
)

_PEPPER_INLINE = PepperInline(
    strategy_module_path="src/strategies/pepper_core_long.py",
    strategy_class_name="PepperCoreLongStrategy",
    params_class_name="CoreLongParams",
    new_strategy_name="pepper_core_long",
    params_dict=asdict(V5_MICRO_PARAMS),
)

_SPEC = PepperBundleSpec(
    variant="combined_v5micro_l1",
    factory_name="round1_combined_v5micro_l1_engine_config",
    factory=round1_combined_v5micro_l1_engine_config,
    label="Round-1 combined: v5_micro PEPPER + L1 ASH ladder",
    purpose=(
        "Final Round-1 candidate combining the best PEPPER leg "
        "(v5_micro guarded carry + micro overlay, official +7,315) "
        "with the best ASH leg (L1 ladder 2.5/3.5/5, official +1,786). "
        "Projected total +9,101."
    ),
    ash_inline=_ASH_INLINE,
    pepper_inline=_PEPPER_INLINE,
)


def _ast_compress(source: str) -> str:
    """Extra AST-level compression: unparse produces minimal whitespace."""
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)

    source, _ = build_bundle(_SPEC)
    compressed = _ast_compress(source)

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"trader_round1_{_SPEC.variant}.py"
    output_path.write_text(compressed, encoding="utf-8")
    print(f"[{_SPEC.variant}] wrote {output_path.name} ({output_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
