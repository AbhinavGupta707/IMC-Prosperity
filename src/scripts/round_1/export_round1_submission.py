"""Export Round-1 Prosperity submission files (Phase 6).

Builds a self-contained ``.py`` for each Round-1 upload variant
(baseline / promoted / alt) by reusing
``src.scripts.export_submission.build_submission_source`` and then
patching the bundle so ``Trader()`` defaults to the chosen variant's
``EngineConfig`` factory instead of the multi-product
``default_engine_config()``.

Outputs land in ``outputs/submissions/round_1/`` so they do not
collide with the tutorial submissions in ``outputs/submissions/``.

Each emitted file:

- Imports the Prosperity-platform datamodel (``--datamodel platform``).
- Constructs ``Trader()`` with **only** the two Round-1 products
  (ASH_COATED_OSMIUM, INTARIAN_PEPPER_ROOT) registered.
- Carries an explicit "ROUND-1 UPLOAD VARIANT" banner identifying the
  variant, the FV / edge / inventory parameters, and the source
  commit (so a reviewer can grep for which file is which).

Usage::

    PYTHONPATH=. .venv/bin/python -m src.scripts.round_1.export_round1_submission
    PYTHONPATH=. .venv/bin/python -m src.scripts.round_1.export_round1_submission --variant promoted
    PYTHONPATH=. .venv/bin/python -m src.scripts.round_1.export_round1_submission --variant alt --output /tmp/alt.py
"""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from src.core.config import (
    EngineConfig,
    round1_alt_engine_config,
    round1_baseline_engine_config,
    round1_f5_engine_config,
    round1_h1_engine_config,
    round1_promoted_engine_config,
    round1_test_engine_config,
)
from src.scripts.export_submission import (
    REPO_ROOT,
    ExportOptions,
    build_submission_source,
    write_submission,
)

_DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "submissions" / "round_1"

_DEFAULT_FACTORY_CALL = "config = default_engine_config()"

_VARIANTS: dict[str, dict[str, object]] = {
    "baseline": {
        "factory_name": "round1_baseline_engine_config",
        "factory": round1_baseline_engine_config,
        "label": "Round-1 baseline / control",
        "purpose": (
            "Reference point. Phase-3 minimum-viable Round-1 default. "
            "Every other variant should beat this on official PnL."
        ),
    },
    "promoted": {
        "factory_name": "round1_promoted_engine_config",
        "factory": round1_promoted_engine_config,
        "label": "Round-1 promoted / robust default",
        "purpose": (
            "Phase-5 promoted candidates. C-ASH-A (ewma_mid, t=0.25) + "
            "C-PEP-A (linear_drift h=32, t=2.0, flatten=0.7). Designed "
            "for cross-day robustness and minimal limit-pinning."
        ),
    },
    "alt": {
        "factory_name": "round1_alt_engine_config",
        "factory": round1_alt_engine_config,
        "label": "Round-1 higher-upside alternate",
        "purpose": (
            "Phase-5 higher-upside candidates. C-ASH-B (wall_mid, t=0.5) "
            "+ C-PEP-B (linear_drift h=32, skew=1.0, flatten=0.9). "
            "Larger PnL ceiling at the cost of more taker / inventory "
            "exposure."
        ),
    },
    "h1": {
        "factory_name": "round1_h1_engine_config",
        "factory": round1_h1_engine_config,
        "label": "Round-1 Phase-8.5 hybrid (promoted PEPPER + alt ASH)",
        "purpose": (
            "Phase-8.5 narrow hybrid candidate. Promoted PEPPER leg "
            "(validated robust default) + alt ASH leg (best official "
            "ASH on the one Round-1 data point). Captures the "
            "empirically-justified ASH uplift without adopting alt "
            "PEPPER's higher-variance inventory bet."
        ),
    },
    "f5": {
        "factory_name": "round1_f5_engine_config",
        "factory": round1_f5_engine_config,
        "label": "Round-1 Phase-9 asymmetric-taker PEPPER + alt ASH",
        "purpose": (
            "Phase-9 fastsearch winner. Wall-based ASH (same leg as "
            "H1 / alt) + promoted PEPPER with per-side taker edges "
            "(buy=1.5, sell=3.0). A surgical sell-widening that keeps "
            "promoted's inventory profile and targets the official-"
            "day Baseline failure mode (early wrong-side PEPPER "
            "sells) without adopting alt PEPPER's near-limit tail."
        ),
    },
    "test": {
        "factory_name": "round1_test_engine_config",
        "factory": round1_test_engine_config,
        "label": "Round-1 ad-hoc directional (wall ASH + buy-and-hold PEPPER)",
        "purpose": (
            "Directional experiment. Wall-based ASH (same leg as F5 "
            "/ H1) + buy-and-hold PEPPER — take any ask up to the "
            "position limit, then hold. Upper-bound reference for "
            "how much of PEPPER's official PnL is drift MTM vs "
            "market-making edge. Additive; never replaces any "
            "shipped bundle."
        ),
    },
}


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception:  # pragma: no cover
        return "unknown"


def _format_product_summary(config: EngineConfig) -> str:
    lines: list[str] = []
    for product in sorted(config.products):
        pc = config.product_config(product)
        if pc is None:
            continue
        snippet = asdict(pc)
        snippet.pop("strategy_name", None)
        snippet.pop("tick_size", None)
        snippet.pop("ewma_alpha", None)
        lines.append(f"#   {product}: {snippet}")
    return "\n".join(lines)


def _build_variant_banner(
    variant: str, info: dict[str, object], commit: str, *, bid_value: int = 0
) -> str:
    config = info["factory"]()
    bid_line = (
        f"# MAF bid : {bid_value} XIRECs (Round-2 only; ignored in earlier rounds)\n"
    )
    return (
        "# " + "=" * 72 + "\n"
        f"# ROUND-1 UPLOAD VARIANT: {variant}\n"
        f"# Label   : {info['label']}\n"
        f"# Purpose : {info['purpose']}\n"
        f"# Factory : src.core.config.{info['factory_name']}\n"
        f"# Built   : {datetime.now(UTC).isoformat()} (commit {commit})\n"
        f"{bid_line}"
        "# Embedded product configs:\n"
        f"{_format_product_summary(config)}\n"
        "# " + "=" * 72 + "\n"
    )


def _patch_default_config_call(
    source: str, factory_name: str, *, bid_value: int = 0
) -> str:
    if _DEFAULT_FACTORY_CALL not in source:
        raise RuntimeError(
            f"Could not find {_DEFAULT_FACTORY_CALL!r} in the bundled source. "
            "The Trader.__init__ default config call may have changed; "
            "update _DEFAULT_FACTORY_CALL in this script accordingly."
        )
    if bid_value < 0:
        raise ValueError(f"bid_value must be >= 0 (got {bid_value})")
    if bid_value:
        # Round-2 MAF bundles wrap the factory in with_bid_value(...) so
        # the embedded config carries the per-variant auction bid.
        replacement = (
            f"self.config = config or with_bid_value({factory_name}(), {bid_value})"
        )
    else:
        # Default path matches the Round-1 bundle shape exactly so the
        # already-shipped fingerprints remain reproducible.
        replacement = f"config = {factory_name}()"
    patched, count = _replace_once(source, _DEFAULT_FACTORY_CALL, replacement)
    if count != 1:
        raise RuntimeError(
            f"Expected exactly 1 occurrence of {_DEFAULT_FACTORY_CALL!r}; "
            f"found {count}."
        )
    return patched


def _replace_once(text: str, old: str, new: str) -> tuple[str, int]:
    count = text.count(old)
    return text.replace(old, new, 1), count


def _output_path_for(variant: str, *, out_dir: Path) -> Path:
    return out_dir / f"trader_round1_{variant}.py"


def _build_variant_source(
    variant: str, info: dict[str, object], *, bid_value: int = 0
) -> str:
    options = ExportOptions(datamodel_mode="platform")
    bundle = build_submission_source(options)
    patched = _patch_default_config_call(
        bundle.source, info["factory_name"], bid_value=bid_value
    )
    banner = _build_variant_banner(variant, info, _git_commit(), bid_value=bid_value)
    # Insert banner right after the auto-generated header (3 leading lines).
    lines = patched.splitlines(keepends=False)
    # The exporter's header is the first part block; banner immediately
    # after the auto-generated comment + before "from __future__".
    # Find the last '#' comment in the header and insert there.
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("#"):
            insert_at = i + 1
        else:
            break
    new_lines = lines[:insert_at] + ["", banner.rstrip()] + lines[insert_at:]
    return "\n".join(new_lines) + "\n"


def export_variant(
    variant: str, *, out_dir: Path = _DEFAULT_OUT_DIR, bid_value: int = 0
) -> Path:
    if variant not in _VARIANTS:
        raise SystemExit(
            f"Unknown variant {variant!r}. Choose from {sorted(_VARIANTS)}."
        )
    info = _VARIANTS[variant]
    out_dir.mkdir(parents=True, exist_ok=True)
    source = _build_variant_source(variant, info, bid_value=bid_value)
    output_path = _output_path_for(variant, out_dir=out_dir)
    output_path.write_text(source, encoding="utf-8")
    return output_path


def _bid_value_arg(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError(
            f"--bid must be >= 0 (IMC normalises negatives to 0; got {parsed})"
        )
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variant",
        choices=list(_VARIANTS) + ["all"],
        default="all",
        help="Which variant to export (default: all three).",
    )
    parser.add_argument("--out-dir", type=Path, default=_DEFAULT_OUT_DIR)
    parser.add_argument(
        "--bid",
        type=_bid_value_arg,
        default=0,
        help=(
            "Round-2 Market Access Fee bid (XIRECs) embedded in the bundle. "
            "0 (default) abstains from the auction; matches the Round-1 "
            "bundle shape exactly so existing fingerprints stay reproducible."
        ),
    )
    args = parser.parse_args(argv)

    targets = list(_VARIANTS) if args.variant == "all" else [args.variant]
    for variant in targets:
        path = export_variant(variant, out_dir=args.out_dir, bid_value=args.bid)
        size_kb = path.stat().st_size / 1024
        rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
        print(f"[{variant}] wrote {rel} ({size_kb:.1f} KB, bid={args.bid})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# Re-exported for tests / tooling that wants to introspect the variants.
VARIANTS = _VARIANTS
