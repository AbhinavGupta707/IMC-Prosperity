"""Export the Phase-F F3a submission bundle — D5 empirical stack.

F3a = weighted_mid FV + m=2.5/t=0.5 + linear skew c=2 + hard flatten,
delivered via the research-only ``AshShapeOverrideStrategy`` (not in
the shipped ``STRATEGY_REGISTRY``). Mirrors the v2_clean export
pipeline: stripped module appended to the bundle + bundle-tail
wiring that extends KNOWN_STRATEGY_NAMES + STRATEGY_REGISTRY.

See ``outputs/round_1/ash_deep_dive/phase_d/PHASE_D_MEMO.md`` sec 2 and
``phase_e/PHASE_E_MEMO.md`` sec 3.
"""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from src.core import config as _config
from src.core.config import EngineConfig, round1_ash_deep_f3a_engine_config
from src.scripts.export_submission import (
    REPO_ROOT,
    ExportOptions,
    build_submission_source,
    strip_module,
)

_SHAPE_OVERRIDE_PATH = "src/strategies/ash_shape_override.py"
_DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "submissions" / "round_1" / "limit_80"
_DEFAULT_OUT_NAME = "trader_round1_ash_deep_f3a.py"
_DEFAULT_FACTORY_CALL = "config = default_engine_config()"
_F3A_FACTORY_CALL = (
    "self.config = config or round1_ash_deep_f3a_engine_config()"
)
_STRATEGY_NAME = "ash_shape_override"

# D5 empirical-stack shape parameters (Phase-D D5).
F3A_SHAPE_PARAMS: dict[str, object] = {
    "skew_mode": "linear",
    "skew_coef": 2.0,
    "flatten_mode": "hard",
    "flatten_threshold": 0.7,
    "size_mode": "constant",
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
        snippet.pop("tick_size", None)
        snippet.pop("ewma_alpha", None)
        lines.append(f"#   {product}: {snippet}")
    return "\n".join(lines)


def _build_banner(config: EngineConfig, commit: str) -> str:
    return (
        "# " + "=" * 72 + "\n"
        "# ROUND-1 UPLOAD VARIANT: ash_deep_f3a\n"
        "# Label   : Round-1 Phase-F F3a — D5 empirical stack "
        "(weighted_mid + m=2.5 + linear skew c=2)\n"
        "# Purpose : Phase-D D5 empirical stack — highest local PnL on "
        "record (+3 446/day on 3-day CV) AND one of the three stress-"
        "tape-robust candidates (zero losses on all six Phase-E "
        "ASH stress tapes). Uses the research-only "
        "AshShapeOverrideStrategy, inlined at bundle tail.\n"
        "# Factory : src.core.config.round1_ash_deep_f3a_engine_config\n"
        f"# Built   : {datetime.now(UTC).isoformat()} (commit {commit})\n"
        "# Embedded product configs:\n"
        f"{_format_product_summary(config)}\n"
        f"# ASH strategy: AshShapeOverrideStrategy (research-only, "
        f"inlined at bundle tail; NOT part of the shipped STRATEGY_REGISTRY)\n"
        "# ASH ShapeParams:\n"
        f"#   {F3A_SHAPE_PARAMS}\n"
        "# " + "=" * 72 + "\n"
    )


def _patch_default_config_call(source: str) -> str:
    if _DEFAULT_FACTORY_CALL not in source:
        raise RuntimeError(
            f"Could not find {_DEFAULT_FACTORY_CALL!r} in the bundled source."
        )
    return source.replace(_DEFAULT_FACTORY_CALL, _F3A_FACTORY_CALL, 1)


def _load_stripped_shape_override() -> str:
    path = REPO_ROOT / _SHAPE_OVERRIDE_PATH
    source = path.read_text(encoding="utf-8")
    stripped = strip_module(_SHAPE_OVERRIDE_PATH, source)
    if stripped.datamodel_symbols:
        raise RuntimeError(
            f"{_SHAPE_OVERRIDE_PATH} must not import from src.datamodel; "
            f"found: {stripped.datamodel_symbols}"
        )
    return stripped.body


_WIRING_APPENDIX_TEMPLATE = '''\

# ========================================================================
# F3a wiring — research-only AshShapeOverrideStrategy is now in scope.
# Extend KNOWN_STRATEGY_NAMES + STRATEGY_REGISTRY in lock-step so the
# F3a engine-config factory can construct a ProductConfig with
# strategy_name="ash_shape_override" without tripping the shipped
# validation whitelist. Pin the F3a ShapeParams.
# ========================================================================

_F3A_SHAPE_PARAMS = ShapeParams(
{params_block}
)


def _f3a_ash_strategy_factory(
    fve: FairValueEngine, sig: SignalEngine
) -> BaseStrategy:
    return AshShapeOverrideStrategy(fve, sig, _F3A_SHAPE_PARAMS)


KNOWN_STRATEGY_NAMES = tuple(
    sorted(set(KNOWN_STRATEGY_NAMES) | {{"ash_shape_override"}})
)
STRATEGY_REGISTRY = MappingProxyType(
    dict(STRATEGY_REGISTRY, ash_shape_override=_f3a_ash_strategy_factory)
)
'''


def _build_wiring_appendix() -> str:
    params_lines = []
    for key, value in F3A_SHAPE_PARAMS.items():
        params_lines.append(f"    {key}={value!r},")
    return _WIRING_APPENDIX_TEMPLATE.format(params_block="\n".join(params_lines))


# Use the v2_clean minifier — it's a proven tool for keeping bundles under 100 KiB.


def _build_f3a_source() -> str:
    options = ExportOptions(datamodel_mode="platform")
    bundle = build_submission_source(options)
    source = _patch_default_config_call(bundle.source)

    # Temporarily whitelist the new strategy name for the factory call.
    _original_known = _config.extend_known_strategy_names((_STRATEGY_NAME,))
    try:
        config = round1_ash_deep_f3a_engine_config()
    finally:
        _config.restore_known_strategy_names(_original_known)

    banner = _build_banner(config, _git_commit())
    lines = source.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("#"):
            insert_at = i + 1
        else:
            break
    lines = [*lines[:insert_at], "", banner.rstrip(), *lines[insert_at:]]

    # Append the stripped shape_override module body.
    strategy_body = _load_stripped_shape_override()
    module_block = [
        "",
        "# " + "=" * 72,
        "# " + _SHAPE_OVERRIDE_PATH
        + " (F3a: research-only module, inlined at bundle tail)",
        "# " + "=" * 72,
        strategy_body,
    ]

    wiring = _build_wiring_appendix()
    composed = "\n".join(lines) + "\n" + "\n".join(module_block) + "\n" + wiring
    if not composed.endswith("\n"):
        composed += "\n"

    # Reuse the v2_clean minifier pipeline with F3a's banner sentinel.
    # The lower-level strip/compress functions are generic; only the
    # sentinel used to locate the end of the identifying header block
    # is variant-specific.
    import ast

    from src.scripts.round_1.export_round1_v2_clean import (
        _collapse_blank_lines,
        _count_header_lines,
        _strip_comment_lines,
        _strip_docstrings,
    )

    banner_sentinel = "ROUND-1 UPLOAD VARIANT: ash_deep_f3a"
    header_cut = _count_header_lines(composed, banner_sentinel=banner_sentinel)
    if header_cut == 0:
        header_cut = 3
    composed = _strip_docstrings(composed)
    header_cut = (
        _count_header_lines(composed, banner_sentinel=banner_sentinel) or 3
    )
    composed = _strip_comment_lines(composed, keep_header_lines=header_cut)
    composed = _collapse_blank_lines(composed)
    # Sanity: the result must still parse.
    ast.parse(composed)
    return composed


def export_f3a(*, out_dir: Path = _DEFAULT_OUT_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    source = _build_f3a_source()
    output_path = out_dir / _DEFAULT_OUT_NAME
    output_path.write_text(source, encoding="utf-8")
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=_DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)
    path = export_f3a(out_dir=args.out_dir)
    size_bytes = path.stat().st_size
    rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
    print(f"[ash_deep_f3a] wrote {rel} ({size_bytes} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
