"""Export the Phase-F F2d submission bundle — wall_mid ASH m=2.5 + buy_hold PEPPER.

Additive script; does NOT modify the shipped
``export_round1_submission.py`` bundle builder. Same pattern as
``export_round1_ash_deep_f2c.py``.

See ``outputs/round_1/ash_deep_dive/PLAN.md`` sec 7.1 for the upload-
cohort rationale and ``phase_b/PHASE_B_MEMO.md`` sec 3.2 for the B2
edge-width evidence.
"""

from __future__ import annotations

import subprocess
from dataclasses import asdict
from datetime import UTC, datetime

from src.core.config import EngineConfig, round1_ash_deep_f2d_engine_config
from src.scripts.export_submission import (
    REPO_ROOT,
    ExportOptions,
    build_submission_source,
)

_DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "submissions" / "round_1" / "limit_80"
_DEFAULT_FACTORY_CALL = "config = default_engine_config()"
_VARIANT = "ash_deep_f2d"
_FACTORY_NAME = "round1_ash_deep_f2d_engine_config"
_LABEL = "Round-1 Phase-F F2d — wall_mid ASH m=2.5 + buy_hold PEPPER"
_PURPOSE = (
    "ASH deep-dive upload F2d. ASH uses wall_mid at wider maker "
    "edge m=2.5 (Phase-B B2 edge-width winner) with taker edge "
    "t=0.5 and shipped skew=4.0 / flatten=0.7. PEPPER pinned at "
    "buy-and-hold with max_aggressive_size=80. Tests whether the "
    "Phase-B fill-mix improvement (18 maker fills vs 6 on shipped) "
    "transfers to official."
)


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
        snippet.pop("tick_size", None)
        snippet.pop("ewma_alpha", None)
        lines.append(f"#   {product}: {snippet}")
    return "\n".join(lines)


def _build_banner(config: EngineConfig, commit: str) -> str:
    return (
        "# " + "=" * 72 + "\n"
        f"# ROUND-1 UPLOAD VARIANT: {_VARIANT}\n"
        f"# Label   : {_LABEL}\n"
        f"# Purpose : {_PURPOSE}\n"
        f"# Factory : src.core.config.{_FACTORY_NAME}\n"
        f"# Built   : {datetime.now(UTC).isoformat()} (commit {commit})\n"
        "# Embedded product configs:\n"
        f"{_format_product_summary(config)}\n"
        "# " + "=" * 72 + "\n"
    )


def _patch_default_config_call(source: str, factory_name: str) -> str:
    if _DEFAULT_FACTORY_CALL not in source:
        raise RuntimeError(
            f"Could not find {_DEFAULT_FACTORY_CALL!r} in the bundled source."
        )
    replacement = f"config = {factory_name}()"
    return source.replace(_DEFAULT_FACTORY_CALL, replacement, 1)


def _insert_banner(source: str, banner: str) -> str:
    lines = source.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("#"):
            insert_at = i + 1
        else:
            break
    new_lines = [*lines[:insert_at], "", banner.rstrip(), *lines[insert_at:]]
    return "\n".join(new_lines) + "\n"


def build_f2d_source() -> tuple[str, EngineConfig]:
    options = ExportOptions(datamodel_mode="platform")
    bundle = build_submission_source(options)
    patched = _patch_default_config_call(bundle.source, _FACTORY_NAME)
    config = round1_ash_deep_f2d_engine_config()
    commit = _git_commit()
    banner = _build_banner(config, commit)
    source = _insert_banner(patched, banner)
    return source, config


def main() -> int:
    out_dir = _DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    source, _config = build_f2d_source()
    output_path = out_dir / f"trader_round1_{_VARIANT}.py"
    output_path.write_text(source, encoding="utf-8")
    size_kb = output_path.stat().st_size / 1024
    rel = (
        output_path.relative_to(REPO_ROOT)
        if output_path.is_relative_to(REPO_ROOT) else output_path
    )
    print(f"[{_VARIANT}] wrote {rel} ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
