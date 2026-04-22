"""Shared bundle-builder for Phase-F ASH deep-dive uploads.

Consolidates the boilerplate used by the `export_round1_ash_deep_*`
scripts: banner generation, factory patching, research-module
inlining, bundle-tail wiring appendix, and the v2_clean-style
minifier pipeline.

Each per-variant export script provides an :class:`AshDeepBundleSpec`
and calls :func:`export_bundle`. Two inlining modes:

- **Config-only** (``inline=None``): no research strategy. Bundle is
  built at shipped size with just the F-variant banner and factory
  patch. Not minified (matches F2c / F2d / F1 control behavior).
- **Research-strategy inlining** (``inline=InlineSpec(...)``): strips
  a research module, appends it, extends
  ``KNOWN_STRATEGY_NAMES`` + ``STRATEGY_REGISTRY`` at bundle tail,
  then minifies to fit under 100 KiB.

NOT an ``export_round1_*`` bundle builder script itself — purely a
helper. The shipped ``export_round1_submission.py`` /
``export_round1_v2_clean.py`` / ``export_round1_v3_nearhold.py``
remain unmodified.
"""

from __future__ import annotations

import ast
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from src.core import config as _config
from src.core.config import EngineConfig
from src.scripts.export_submission import (
    REPO_ROOT,
    ExportOptions,
    build_submission_source,
    strip_module,
)
from src.scripts.round_1.export_round1_v2_clean import (
    _collapse_blank_lines,
    _count_header_lines,
    _strip_comment_lines,
    _strip_docstrings,
)

# Matches the call site in src/trader.py. When trader.py's init pattern
# changes, update this constant. The patcher swaps the factory name
# (not the ``config is None`` check) so each R1 variant's bundled
# __init__ pulls its own preconfigured EngineConfig by default.
_DEFAULT_FACTORY_CALL = "config = default_engine_config()"

DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "submissions" / "round_1" / "limit_80"


# --------------------------------------------------------------- spec types


@dataclass(frozen=True)
class InlineSpec:
    """Describes a research strategy to inline into the bundle."""

    strategy_module_path: str
    strategy_class_name: str
    params_class_name: str
    new_strategy_name: str
    params_dict: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class AshDeepBundleSpec:
    """One Phase-F upload spec."""

    variant: str                                 # e.g. "ash_deep_f2a"
    factory_name: str                            # e.g. "round1_ash_deep_f2a_engine_config"
    factory: Callable[[], EngineConfig]
    label: str
    purpose: str
    inline: InlineSpec | None = None


# --------------------------------------------------------------- helpers


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


def _build_banner(spec: AshDeepBundleSpec, config: EngineConfig, commit: str) -> str:
    inline_line = ""
    if spec.inline is not None:
        inline_line = (
            f"# ASH strategy: {spec.inline.strategy_class_name} (research-only, "
            f"inlined at bundle tail; NOT in shipped STRATEGY_REGISTRY)\n"
            f"# ASH params: {spec.inline.params_dict}\n"
        )
    return (
        "# " + "=" * 72 + "\n"
        f"# ROUND-1 UPLOAD VARIANT: {spec.variant}\n"
        f"# Label   : {spec.label}\n"
        f"# Purpose : {spec.purpose}\n"
        f"# Factory : src.core.config.{spec.factory_name}\n"
        f"# Built   : {datetime.now(UTC).isoformat()} (commit {commit})\n"
        "# Embedded product configs:\n"
        f"{_format_product_summary(config)}\n"
        f"{inline_line}"
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


def _load_stripped_module(path: str) -> str:
    file_path = REPO_ROOT / path
    source = file_path.read_text(encoding="utf-8")
    stripped = strip_module(path, source)
    if stripped.datamodel_symbols:
        raise RuntimeError(
            f"{path} must not import from src.datamodel; "
            f"found: {stripped.datamodel_symbols}"
        )
    return stripped.body


_WIRING_APPENDIX_TEMPLATE = '''\

# ========================================================================
# {variant} wiring — research-only {strategy_class_name} now in scope.
# Extend KNOWN_STRATEGY_NAMES + STRATEGY_REGISTRY in lock-step so the
# {variant} engine-config factory can construct a ProductConfig with
# strategy_name="{new_strategy_name}" without tripping the shipped
# validation whitelist.
# ========================================================================

_{variant_upper}_PARAMS = {params_class_name}(
{params_block}
)


def _{variant}_ash_strategy_factory(
    fve: FairValueEngine, sig: SignalEngine
) -> BaseStrategy:
    return {strategy_class_name}(fve, sig, _{variant_upper}_PARAMS)


KNOWN_STRATEGY_NAMES = tuple(
    sorted(set(KNOWN_STRATEGY_NAMES) | {{"{new_strategy_name}"}})
)
STRATEGY_REGISTRY = MappingProxyType(
    dict(STRATEGY_REGISTRY, {new_strategy_name}=_{variant}_ash_strategy_factory)
)
'''


def _build_wiring_appendix(spec: AshDeepBundleSpec) -> str:
    if spec.inline is None:
        return ""
    params_lines = []
    for key, value in spec.inline.params_dict.items():
        params_lines.append(f"    {key}={value!r},")
    return _WIRING_APPENDIX_TEMPLATE.format(
        variant=spec.variant,
        variant_upper=spec.variant.upper(),
        strategy_class_name=spec.inline.strategy_class_name,
        new_strategy_name=spec.inline.new_strategy_name,
        params_class_name=spec.inline.params_class_name,
        params_block="\n".join(params_lines),
    )


def _minify(source: str, banner_sentinel: str) -> str:
    header_cut = _count_header_lines(source, banner_sentinel=banner_sentinel) or 3
    source = _strip_docstrings(source)
    header_cut = _count_header_lines(source, banner_sentinel=banner_sentinel) or 3
    source = _strip_comment_lines(source, keep_header_lines=header_cut)
    source = _collapse_blank_lines(source)
    ast.parse(source)
    return source


# ----------------------------------------------------------------- main API


def build_bundle(spec: AshDeepBundleSpec) -> tuple[str, EngineConfig]:
    """Assemble the bundle source for one Phase-F variant."""
    options = ExportOptions(datamodel_mode="platform")
    bundle = build_submission_source(options)
    source = _patch_default_config_call(bundle.source, spec.factory_name)

    # Temporarily whitelist a new strategy name during factory construction
    # so validation doesn't trip on the unknown name (bundle-tail wiring
    # re-extends KNOWN_STRATEGY_NAMES at runtime before any Trader builds).
    # ``extend_known_strategy_names`` keeps both ``config.py`` and
    # ``config_core.py`` copies of the whitelist in sync since
    # ``ProductConfig.__post_init__`` reads from config_core.
    if spec.inline is not None:
        original_known = _config.extend_known_strategy_names(
            (spec.inline.new_strategy_name,)
        )
    else:
        original_known = _config.KNOWN_STRATEGY_NAMES
    try:
        config = spec.factory()
    finally:
        _config.restore_known_strategy_names(original_known)

    banner = _build_banner(spec, config, _git_commit())
    source = _insert_banner(source, banner)

    if spec.inline is not None:
        strategy_body = _load_stripped_module(spec.inline.strategy_module_path)
        module_block = [
            "",
            "# " + "=" * 72,
            "# " + spec.inline.strategy_module_path
            + f" ({spec.variant}: research-only, inlined at bundle tail)",
            "# " + "=" * 72,
            strategy_body,
        ]
        wiring = _build_wiring_appendix(spec)
        source = source + "\n" + "\n".join(module_block) + "\n" + wiring
        if not source.endswith("\n"):
            source += "\n"
        source = _minify(
            source, banner_sentinel=f"ROUND-1 UPLOAD VARIANT: {spec.variant}",
        )

    return source, config


def export_bundle(
    spec: AshDeepBundleSpec, *, out_dir: Path = DEFAULT_OUT_DIR,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    source, _config_out = build_bundle(spec)
    output_path = out_dir / f"trader_round1_{spec.variant}.py"
    output_path.write_text(source, encoding="utf-8")
    return output_path
