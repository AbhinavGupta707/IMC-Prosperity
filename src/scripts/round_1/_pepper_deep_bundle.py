"""Dual-inline bundle builder for PEPPER candidate uploads.

Extension of ``_ash_deep_bundle.py`` that inlines TWO research
strategy modules (one for ASH, one for PEPPER) into a single
submission bundle. The 5 new PEPPER candidates keep the K2-proven
``AshLadderStrategy`` for ASH and only swap the PEPPER leg, so both
legs need inlining.

Mechanism (same as ``_ash_deep_bundle.py`` but x2):

1. Build the live submission source.
2. Patch ``Trader.__init__`` to use the candidate engine-config factory.
3. Insert an upload banner.
4. Inline each research strategy module body.
5. Append a wiring appendix that extends ``KNOWN_STRATEGY_NAMES`` and
   ``STRATEGY_REGISTRY`` with BOTH strategies.
6. Minify to fit the IMC 100 KiB upload cap.

Note: shipped STRATEGY_REGISTRY is immutable (MappingProxyType). We
rebind it to a new one that wraps the existing entries plus the
inlined factories. The Trader resolves strategy names at call time,
so the rebind takes effect before IMC constructs Trader.
"""

from __future__ import annotations

import ast
import re
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

_DEFAULT_FACTORY_CALL = "config = default_engine_config()"

DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "submissions" / "round_1" / "limit_80"


# --------------------------------------------------------------- spec types


@dataclass(frozen=True)
class PepperInline:
    """One inlined research strategy + wiring info."""

    strategy_module_path: str
    strategy_class_name: str
    params_class_name: str
    new_strategy_name: str  # what STRATEGY_REGISTRY key it registers under
    params_dict: dict[str, object] = field(default_factory=dict)
    factory_var: str = ""    # e.g. "_pepper_passive_maker_factory" (auto if empty)


@dataclass(frozen=True)
class PepperBundleSpec:
    """One PEPPER candidate upload spec."""

    variant: str                                 # e.g. "pepper_passive_maker"
    factory_name: str                            # e.g. "round1_pepper_passive_maker_engine_config"
    factory: Callable[[], EngineConfig]
    label: str
    purpose: str
    ash_inline: PepperInline                     # always present: K2 ash_ladder
    pepper_inline: PepperInline                  # the candidate PEPPER strategy


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


def _build_banner(
    spec: PepperBundleSpec,
    config: EngineConfig,
    commit: str,
    *,
    redact_params: bool = False,
) -> str:
    """Build the upload banner.

    When ``redact_params`` is True, the banner omits the per-product
    parameter dump and the inlined-strategy params dicts. The bundle
    itself still contains the parameters at runtime — this only
    redacts the **comment** so a competitor reading the uploaded file
    cannot grep the strategy edges/weights/thresholds without
    decompiling the actual class definitions. Default False preserves
    the Round-1 banner shape for historical bundle reproducibility.
    """
    if redact_params:
        body = (
            f"# Built     : {datetime.now(UTC).isoformat()} (commit {commit})\n"
            "# (Embedded parameters intentionally redacted from the banner;\n"
            "#  see the inlined strategy classes below for the actual values.)\n"
        )
    else:
        body = (
            f"# Built   : {datetime.now(UTC).isoformat()} (commit {commit})\n"
            "# Embedded product configs:\n"
            f"{_format_product_summary(config)}\n"
            f"# ASH strategy: {spec.ash_inline.strategy_class_name} (research-only, inlined)\n"
            f"# ASH params: {spec.ash_inline.params_dict}\n"
            f"# PEPPER strategy: {spec.pepper_inline.strategy_class_name} (research-only, inlined)\n"
            f"# PEPPER params: {spec.pepper_inline.params_dict}\n"
        )
    return (
        "# " + "=" * 72 + "\n"
        f"# ROUND-1 UPLOAD VARIANT: {spec.variant}\n"
        f"# Label   : {spec.label}\n"
        f"# Purpose : {spec.purpose}\n"
        f"# Factory : src.core.config.{spec.factory_name}\n"
        f"{body}"
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
            f"{path} must not import from src.datamodel; found: {stripped.datamodel_symbols}"
        )
    return stripped.body


_PARAMS_BLOCK_TEMPLATE = """\
_{upper}_PARAMS = {params_cls}(
{body}
)


def {factory_var}(fve: FairValueEngine, sig: SignalEngine) -> BaseStrategy:
    return {strategy_cls}(fve, sig, _{upper}_PARAMS)
"""


def _format_params_block(inline: PepperInline, var_prefix: str) -> tuple[str, str]:
    factory_var = inline.factory_var or f"_{var_prefix}_factory"
    upper = var_prefix.upper()
    params_lines = [f"    {k}={v!r}," for k, v in inline.params_dict.items()]
    block = _PARAMS_BLOCK_TEMPLATE.format(
        upper=upper,
        params_cls=inline.params_class_name,
        strategy_cls=inline.strategy_class_name,
        body="\n".join(params_lines),
        factory_var=factory_var,
    )
    return block, factory_var


_WIRING_APPENDIX_TEMPLATE = '''\

# ========================================================================
# {variant} wiring — two research-only strategies now in scope.
# Extend KNOWN_STRATEGY_NAMES + STRATEGY_REGISTRY in lock-step so the
# engine-config factory can construct ProductConfigs referencing these
# strategy names without tripping the shipped validation whitelist.
# Rebinding the module-level names takes effect before IMC builds
# any Trader() instance.
# ========================================================================

{ash_params_block}

{pepper_params_block}

KNOWN_STRATEGY_NAMES = tuple(
    sorted(set(KNOWN_STRATEGY_NAMES) | {{"{ash_name}", "{pepper_name}"}})
)
STRATEGY_REGISTRY = MappingProxyType(
    dict(
        STRATEGY_REGISTRY,
        **{{
            "{ash_name}": {ash_factory_var},
            "{pepper_name}": {pepper_factory_var},
        }}
    )
)
'''


def _build_wiring_appendix(spec: PepperBundleSpec) -> str:
    ash_block, ash_factory_var = _format_params_block(spec.ash_inline, "ash_" + spec.variant)
    pep_block, pep_factory_var = _format_params_block(spec.pepper_inline, "pep_" + spec.variant)
    return _WIRING_APPENDIX_TEMPLATE.format(
        variant=spec.variant,
        ash_params_block=ash_block.rstrip(),
        pepper_params_block=pep_block.rstrip(),
        ash_name=spec.ash_inline.new_strategy_name,
        pepper_name=spec.pepper_inline.new_strategy_name,
        ash_factory_var=ash_factory_var,
        pepper_factory_var=pep_factory_var,
    )


def _strip_post_init_bodies(source: str) -> str:
    """Replace ``__post_init__`` method bodies with ``pass``.

    Params dataclasses validate at construction time. The bundle ships
    with pre-validated param values baked in as literals in the wiring
    appendix — the validation code is dead weight at runtime. We keep
    the method signature so ``@dataclass(frozen=True)`` decorator logic
    that introspects for it still works; only the body is replaced.

    Safe: the validation is redundant here (params are constants) and
    never caught at runtime.
    """
    tree = ast.parse(source)
    lines = source.split("\n")
    removals: list[tuple[int, int, list[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != "__post_init__":
            continue
        body = node.body
        if not body:
            continue
        start = body[0].lineno - 1
        end = (body[-1].end_lineno or body[-1].lineno) - 1
        # Preserve indentation from the first body line.
        indent_match = re.match(r"^(\s*)", lines[start])
        indent = indent_match.group(1) if indent_match else "        "
        removals.append((start, end, [indent + "pass"]))

    removals.sort(key=lambda r: r[0], reverse=True)
    for start, end, repl in removals:
        lines[start : end + 1] = repl
    return "\n".join(lines)


def _strip_inline_comments_and_trailing_ws(source: str) -> str:
    """Remove inline (trailing) comments on code lines and trim whitespace.

    Uses tokenize so string literals containing ``#`` are never touched.
    Whole-line comments (first non-ws char is ``#``) are preserved here
    — ``_strip_comment_lines`` handles those separately with the header
    protection. Trailing whitespace is stripped on every line.

    Produces bundle-identical behavior: comments are pure text, no
    runtime code path reads them.
    """
    import io
    import tokenize

    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except tokenize.TokenizeError:
        # Fall back: return source unchanged if tokenization fails.
        return source

    # Build a set of (line, col_start, col_end) ranges of inline comments
    # to drop. A comment is "inline" if something non-whitespace appears
    # earlier on the same line.
    lines = source.split("\n")
    # Track first non-ws column per line.
    first_code_col: dict[int, int] = {}
    for tok in tokens:
        if tok.type in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING, tokenize.ENDMARKER):
            continue
        if tok.type == tokenize.STRING and tok.start[0] == tok.end[0]:
            pass  # strings count as code for "is line pure comment" check
        line_no = tok.start[0]
        if line_no not in first_code_col:
            first_code_col[line_no] = tok.start[1]
        else:
            first_code_col[line_no] = min(first_code_col[line_no], tok.start[1])

    # Drop inline comments: for each COMMENT token on a line that has
    # prior code, remove from comment col to end of line.
    cuts: dict[int, int] = {}
    for tok in tokens:
        if tok.type != tokenize.COMMENT:
            continue
        line_no = tok.start[0]
        col = tok.start[1]
        if line_no in first_code_col and first_code_col[line_no] < col:
            # Keep the smallest cut column for each line.
            cuts[line_no] = min(cuts.get(line_no, col), col)

    out: list[str] = []
    for i, line in enumerate(lines, start=1):
        cut = cuts.get(i)
        if cut is not None:
            line = line[:cut].rstrip()
        else:
            line = line.rstrip()
        out.append(line)
    return "\n".join(out)


def _minify(source: str, banner_sentinel: str) -> str:
    header_cut = _count_header_lines(source, banner_sentinel=banner_sentinel) or 3
    source = _strip_docstrings(source)
    source = _strip_post_init_bodies(source)
    header_cut = _count_header_lines(source, banner_sentinel=banner_sentinel) or 3
    source = _strip_comment_lines(source, keep_header_lines=header_cut)
    source = _strip_inline_comments_and_trailing_ws(source)
    source = _collapse_blank_lines(source)
    ast.parse(source)
    return source


# ----------------------------------------------------------------- main API


def build_bundle(
    spec: PepperBundleSpec, *, redact_params: bool = False
) -> tuple[str, EngineConfig]:
    """Assemble the bundle source for one PEPPER candidate.

    ``redact_params`` strips strategy parameter values from the
    upload banner (see ``_build_banner`` for details). Default False
    preserves Round-1 banner shape; Round-2 export passes True.
    """
    options = ExportOptions(datamodel_mode="platform")
    bundle = build_submission_source(options)
    source = _patch_default_config_call(bundle.source, spec.factory_name)

    # Temporarily whitelist both new strategy names during factory
    # build. ``extend_known_strategy_names`` keeps config.py and
    # config_core.py whitelists in sync.
    original_known = _config.extend_known_strategy_names((
        spec.ash_inline.new_strategy_name,
        spec.pepper_inline.new_strategy_name,
    ))
    try:
        config = spec.factory()
    finally:
        _config.restore_known_strategy_names(original_known)

    banner = _build_banner(
        spec, config, _git_commit(), redact_params=redact_params
    )
    source = _insert_banner(source, banner)

    # Inline BOTH research strategy modules.
    ash_body = _load_stripped_module(spec.ash_inline.strategy_module_path)
    pep_body = _load_stripped_module(spec.pepper_inline.strategy_module_path)
    module_block = [
        "",
        "# " + "=" * 72,
        "# " + spec.ash_inline.strategy_module_path
        + f" ({spec.variant}: research-only, inlined at bundle tail)",
        "# " + "=" * 72,
        ash_body,
        "",
        "# " + "=" * 72,
        "# " + spec.pepper_inline.strategy_module_path
        + f" ({spec.variant}: research-only, inlined at bundle tail)",
        "# " + "=" * 72,
        pep_body,
    ]
    wiring = _build_wiring_appendix(spec)
    source = source + "\n" + "\n".join(module_block) + "\n" + wiring
    if not source.endswith("\n"):
        source += "\n"
    source = _minify(source, banner_sentinel=f"ROUND-1 UPLOAD VARIANT: {spec.variant}")
    return source, config


def export_bundle(
    spec: PepperBundleSpec, *, out_dir: Path = DEFAULT_OUT_DIR,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    source, _ = build_bundle(spec)
    output_path = out_dir / f"trader_round1_{spec.variant}.py"
    output_path.write_text(source, encoding="utf-8")
    return output_path
