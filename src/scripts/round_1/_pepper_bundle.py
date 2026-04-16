"""Shared export helpers for PEPPER research bundles.

These exporters follow the old V2/V3 pattern:

- start from the generic live submission bundle,
- patch ``Trader()`` to default to a PEPPER-specific round-1 config,
- inline the research-only ``PepperCoreLongStrategy`` at the bundle tail,
- extend ``KNOWN_STRATEGY_NAMES`` and ``STRATEGY_REGISTRY`` locally,
- minify the final bundle so it fits IMC's upload size cap.
"""

from __future__ import annotations

import ast
import hashlib
import subprocess
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.scripts.export_submission import (
    REPO_ROOT,
    ExportOptions,
    build_submission_source,
    strip_module,
)
from src.scripts.validate_submission import validate_file
from src.strategies.pepper_core_long import CoreLongParams

_DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "submissions" / "round_1" / "limit_80"
_DEFAULT_FACTORY_CALL = "self.config = config or default_engine_config()"
_PEPPER_MODULE_PATH = "src/strategies/pepper_core_long.py"

_ASH_OVERRIDE = {
    "fair_value_method": "wall_mid",
    "fair_value_fallbacks": ("mid", "microprice"),
    "maker_edge": 1.5,
    "taker_edge": 0.5,
    "inventory_skew": 4.0,
    "flatten_threshold": 0.7,
    "history_length": 48,
}

_PEPPER_OVERRIDE = {
    "strategy_name": "pepper_core_long",
    "fair_value_method": "linear_drift",
    "fair_value_fallbacks": ("depth_mid", "hybrid_wall_micro", "mid"),
    "maker_edge": 1.0,
    "taker_edge": 2.0,
    "quote_size": 10,
    "max_aggressive_size": 20,
    "inventory_skew": 2.0,
    "flatten_threshold": 0.7,
    "history_length": 32,
}


@dataclass(frozen=True)
class PepperBundleSpec:
    slug: str
    label: str
    purpose: str
    expectation: str
    core_long_params: CoreLongParams

    @property
    def factory_name(self) -> str:
        return f"round1_{self.slug}_engine_config"

    @property
    def output_name(self) -> str:
        return f"trader_round1_{self.slug}.py"

    @property
    def meta_name(self) -> str:
        return f"trader_round1_{self.slug}.meta.md"

    @property
    def const_name(self) -> str:
        return "_" + self.slug.upper()

    @property
    def strategy_factory_name(self) -> str:
        return f"_{self.slug}_pepper_strategy_factory"


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


def _replace_once(text: str, old: str, new: str) -> tuple[str, int]:
    count = text.count(old)
    return text.replace(old, new, 1), count


def _patch_default_config_call(source: str, factory_name: str) -> str:
    if _DEFAULT_FACTORY_CALL not in source:
        raise RuntimeError(
            f"Could not find {_DEFAULT_FACTORY_CALL!r} in the bundled source."
        )
    replacement = f"self.config = config or {factory_name}()"
    patched, count = _replace_once(source, _DEFAULT_FACTORY_CALL, replacement)
    if count != 1:
        raise RuntimeError(
            f"Expected exactly 1 occurrence of {_DEFAULT_FACTORY_CALL!r}; found {count}."
        )
    return patched


def _render_py_value(value: Any) -> str:
    return repr(value)


def _render_kwargs(kwargs: dict[str, Any], *, indent: int = 8) -> str:
    pad = " " * indent
    return ",\n".join(f"{pad}{key}={_render_py_value(value)}" for key, value in kwargs.items())


def _render_core_long_params(name: str, params: CoreLongParams) -> str:
    kwargs = {field.name: getattr(params, field.name) for field in fields(CoreLongParams)}
    return (
        f"{name} = CoreLongParams(\n"
        f"{_render_kwargs(kwargs, indent=4)}\n"
        ")\n"
    )


def _render_engine_factory(spec: PepperBundleSpec) -> str:
    return (
        f"def {spec.factory_name}() -> EngineConfig:\n"
        "    return _round1_engine_with(\n"
        "        ASH_COATED_OSMIUM=dict(\n"
        f"{_render_kwargs(_ASH_OVERRIDE, indent=12)}\n"
        "        ),\n"
        "        INTARIAN_PEPPER_ROOT=dict(\n"
        f"{_render_kwargs(_PEPPER_OVERRIDE, indent=12)}\n"
        "        ),\n"
        "    )\n"
    )


def _render_tail(spec: PepperBundleSpec) -> str:
    pepper_source = (REPO_ROOT / _PEPPER_MODULE_PATH).read_text(encoding="utf-8")
    pepper_body = strip_module(_PEPPER_MODULE_PATH, pepper_source).body
    params_name = f"{spec.const_name}_CORE_LONG_PARAMS"
    return (
        "\n# === PEPPER RESEARCH APPENDIX ==============================================\n\n"
        f"{pepper_body}\n\n"
        f"{_render_engine_factory(spec)}\n"
        f"{_render_core_long_params(params_name, spec.core_long_params)}\n"
        f"def {spec.strategy_factory_name}(\n"
        "    fve: FairValueEngine, sig: SignalEngine\n"
        ") -> BaseStrategy:\n"
        f"    return PepperCoreLongStrategy(fve, sig, {params_name})\n\n"
        "KNOWN_STRATEGY_NAMES = tuple(\n"
        '    sorted(set(KNOWN_STRATEGY_NAMES) | {"pepper_core_long"})\n'
        ")\n"
        "STRATEGY_REGISTRY = MappingProxyType(\n"
        f"    dict(STRATEGY_REGISTRY, pepper_core_long={spec.strategy_factory_name})\n"
        ")\n"
    )


def _build_variant_banner(spec: PepperBundleSpec, commit: str) -> str:
    return (
        f"# ROUND-1 PEPPER VARIANT: {spec.slug}\n"
        f"# Built: {datetime.now(UTC).isoformat()} (commit {commit})\n"
        f"# Factory: {spec.factory_name}\n"
    )


def _minify_source(source: str) -> str:
    tree = ast.parse(source)

    def strip_string_exprs(body: list[ast.stmt]) -> list[ast.stmt]:
        new_body: list[ast.stmt] = []
        for node in body:
            if (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                continue
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                node.body = strip_string_exprs(node.body)
            new_body.append(node)
        return new_body

    tree.body = strip_string_exprs(tree.body)
    return ast.unparse(tree).rstrip() + "\n"


def _insert_banner(source: str, banner: str) -> str:
    lines = source.splitlines(keepends=False)
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("#"):
            insert_at = i + 1
        else:
            break
    new_lines = lines[:insert_at] + ["", banner.rstrip()] + lines[insert_at:]
    return "\n".join(new_lines) + "\n"


def _write_meta(path: Path, spec: PepperBundleSpec) -> Path:
    report = validate_file(path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    meta_path = path.with_suffix(".meta.md")
    body = [
        f"# {spec.slug} submission bundle — metadata",
        "",
        f"Companion record for `{path.relative_to(REPO_ROOT)}`.",
        "",
        "## Summary",
        "",
        f"- Label: {spec.label}",
        f"- Purpose: {spec.purpose}",
        f"- Expectation: {spec.expectation}",
        f"- Source commit: `{_git_commit()}`",
        f"- SHA256: `{sha}`",
        f"- Size: `{path.stat().st_size}` bytes",
        f"- Exporter: `src.scripts.round_1.export_round1_{spec.slug}`",
        "",
        "## PEPPER CoreLongParams",
        "",
        "```python",
        f"{_render_core_long_params(spec.const_name + '_CORE_LONG_PARAMS', spec.core_long_params).rstrip()}",
        "```",
        "",
        "## Validation",
        "",
        "```text",
        report.format(),
        "```",
        "",
    ]
    meta_path.write_text("\n".join(body), encoding="utf-8")
    return meta_path


def export_pepper_bundle(
    spec: PepperBundleSpec,
    *,
    out_dir: Path = _DEFAULT_OUT_DIR,
    write_meta: bool = True,
) -> Path:
    options = ExportOptions(datamodel_mode="platform")
    bundle = build_submission_source(options)
    patched = _patch_default_config_call(bundle.source, spec.factory_name)
    with_tail = patched.rstrip() + "\n" + _render_tail(spec)
    with_banner = _insert_banner(with_tail, _build_variant_banner(spec, _git_commit()))
    minified = _minify_source(with_banner)

    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / spec.output_name
    output_path.write_text(minified, encoding="utf-8")
    if write_meta:
        _write_meta(output_path, spec)
    return output_path
