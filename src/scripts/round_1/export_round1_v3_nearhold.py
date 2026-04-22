"""Export the V3_nearhold Round-1 submission bundle.

V3_nearhold is the Phase-11 ``pepper_sparse_overlay`` search winner.
Near-buy-and-hold PEPPER (base_long=80, opening seed=65, window=500)
+ same wall_mid ASH leg as V3_nearhold / H1 / F5 / Alt. Routed through
the research-only ``PepperCoreLongStrategy``. Uses the same export
pipeline as V3_nearhold (live bundle + inlined research strategy +
wiring appendix + minifier); only the params and banner differ. See
``export_round1_v3_nearhold.py`` for mechanism commentary.

Usage::

    PYTHONPATH=. .venv/bin/python -m src.scripts.round_1.export_round1_v3_nearhold
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from src.core import config as _config
from src.core.config import EngineConfig, round1_v3_nearhold_engine_config
from src.scripts.export_submission import (
    REPO_ROOT,
    ExportOptions,
    build_submission_source,
    strip_module,
)

_PEPPER_CORE_LONG_PATH = "src/strategies/pepper_core_long.py"

_DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "submissions" / "round_1" / "limit_80"
_DEFAULT_OUT_NAME = "trader_round1_v3_nearhold.py"

_DEFAULT_FACTORY_CALL = "config = default_engine_config()"
_V3_NEARHOLD_FACTORY_CALL = (
    "self.config = config or round1_v3_nearhold_engine_config()"
)


# --------------------------------------------------------------------------- #
# V3_nearhold params — MUST match                                              #
# outputs/round_1/pepper_sparse_overlay/shortlist.md                           #
# --------------------------------------------------------------------------- #

V3_NEARHOLD_PARAMS: dict[str, object] = {
    "base_long": 80,
    "add_thresh": 3.0,
    "trim_thresh": 8.0,
    "add_gain": 5.0,
    "trim_gain": 2.0,
    "floor": 40,
    "ceiling": 80,
    "step": 8,
    "exec_style": "taker",
    "hybrid_threshold": 2.0,
    "maker_edge_offset": 0.0,
    "open_seed_size": 65,
    "open_window": 500,
    "open_no_short": True,
}


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


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
        "# ROUND-1 UPLOAD VARIANT: v3_nearhold\n"
        "# Label   : Round-1 Phase-11 pepper_sparse_overlay winner\n"
        "# Purpose : V3_nearhold PEPPER (near-buy-and-hold + sparse overlay) + "
        "wall_mid ASH. base_long=80 with opening seed=65/window=500. "
        "Matches buy_hold_80 carry on the proxy (+7351 vs +7279) with "
        "overlay optionality preserved for reversing days.\n"
        f"# Factory : src.core.config.round1_v3_nearhold_engine_config\n"
        f"# Built   : {datetime.now(UTC).isoformat()} (commit {commit})\n"
        "# Embedded product configs:\n"
        f"{_format_product_summary(config)}\n"
        "# PEPPER strategy: PepperCoreLongStrategy (research-only, inlined "
        "at bundle tail; NOT part of the shipped STRATEGY_REGISTRY)\n"
        "# PEPPER CoreLongParams:\n"
        f"#   {V3_NEARHOLD_PARAMS}\n"
        "# " + "=" * 72 + "\n"
    )


def _patch_default_config_call(source: str) -> str:
    if _DEFAULT_FACTORY_CALL not in source:
        raise RuntimeError(
            f"Could not find {_DEFAULT_FACTORY_CALL!r} in the bundled source. "
            "The Trader.__init__ default config call may have changed."
        )
    if source.count(_DEFAULT_FACTORY_CALL) != 1:
        raise RuntimeError(
            f"Expected exactly 1 occurrence of {_DEFAULT_FACTORY_CALL!r}."
        )
    return source.replace(_DEFAULT_FACTORY_CALL, _V3_NEARHOLD_FACTORY_CALL, 1)


def _load_stripped_pepper_core_long() -> str:
    path = REPO_ROOT / _PEPPER_CORE_LONG_PATH
    source = path.read_text(encoding="utf-8")
    stripped = strip_module(_PEPPER_CORE_LONG_PATH, source)
    if stripped.hoisted_imports:
        # pepper_core_long.py imports ``math`` and ``dataclasses`` which
        # are also imported by the live path; the base bundle already
        # has them de-duped at the top. Any new import the strip
        # surfaces here would need to be added above the module banner,
        # but none are expected. If this fires, add a de-dupe step.
        expected = {"import math", "from dataclasses import dataclass", "from types import MappingProxyType"}
        actual = {h.strip() for h in stripped.hoisted_imports}
        extras = actual - expected
        if extras:
            raise RuntimeError(
                f"pepper_core_long.py has unexpected hoisted imports not "
                f"already in the base bundle: {extras}"
            )
    if stripped.datamodel_symbols:
        raise RuntimeError(
            "pepper_core_long.py should not import anything from src.datamodel; "
            f"found: {stripped.datamodel_symbols}"
        )
    return stripped.body


# --------------------------------------------------------------------------- #
# Wiring appendix                                                             #
# --------------------------------------------------------------------------- #
#
# Defines at module scope, after the Trader class is defined, the V3_nearhold
# strategy factory and registers it in STRATEGY_REGISTRY under the name
# "pepper_core_long". STRATEGY_REGISTRY is a MappingProxyType (immutable),
# so we REBIND the module-level name to a new MappingProxyType that wraps
# the existing entries plus the V3_nearhold factory. The Trader looks up
# STRATEGY_REGISTRY by name at call time, so the rebinding takes effect
# before any Trader() instance is constructed by the IMC container.

_WIRING_APPENDIX_TEMPLATE = '''\

# ========================================================================
# V3_nearhold wiring — research-only PepperCoreLongStrategy is now in scope.
# Extend KNOWN_STRATEGY_NAMES + STRATEGY_REGISTRY in lock-step so the
# engine config factory can construct a ProductConfig with
# strategy_name="pepper_core_long" without tripping the shipped
# validation. Pin the V3_nearhold CoreLongParams so the factory signature
# matches the existing registry contract (fve, sig) -> strategy.
# ========================================================================

_V3_NEARHOLD_CORE_LONG_PARAMS = CoreLongParams(
{params_block}
)


def _v3_nearhold_pepper_strategy_factory(
    fve: FairValueEngine, sig: SignalEngine
) -> BaseStrategy:
    return PepperCoreLongStrategy(fve, sig, _V3_NEARHOLD_CORE_LONG_PARAMS)


# Extend BOTH invariant halves: KNOWN_STRATEGY_NAMES (validated by
# ProductConfig) and STRATEGY_REGISTRY (consumed by Trader). Rebinding
# the module-level names takes effect before any Trader() is built by
# the IMC container.
KNOWN_STRATEGY_NAMES = tuple(
    sorted(set(KNOWN_STRATEGY_NAMES) | {{"pepper_core_long"}})
)
STRATEGY_REGISTRY = MappingProxyType(
    dict(STRATEGY_REGISTRY, pepper_core_long=_v3_nearhold_pepper_strategy_factory)
)
'''


def _build_wiring_appendix() -> str:
    params_lines = []
    for key, value in V3_NEARHOLD_PARAMS.items():
        params_lines.append(f"    {key}={value!r},")
    return _WIRING_APPENDIX_TEMPLATE.format(params_block="\n".join(params_lines))


# --------------------------------------------------------------------------- #
# Minifier — strips docstrings + comment-only lines + collapses blanks.       #
#                                                                             #
# Phase-10 added this so ``trader_round1_v3_nearhold.py`` fits under the real    #
# IMC 100 KiB upload cap. Docstrings and comments are pure text — removing    #
# them cannot change runtime behaviour (nothing in the engine introspects     #
# ``__doc__`` or source comments at runtime). Strategy logic is untouched.    #
#                                                                             #
# The minifier runs as the LAST step of ``_build_v3_nearhold_source`` so it      #
# operates on the finished bundle, not on source modules. It keeps:           #
# - the auto-generated top header (for identification on disk)                #
# - the V3_nearhold banner (for audit traceability)                              #
# - all executable statements                                                 #
# And removes:                                                                #
# - module-, class-, and function-level docstrings                            #
# - pure comment-only lines beyond the preserved header block                 #
# - repeated blank lines (collapsed to at most one)                           #
# --------------------------------------------------------------------------- #


def _is_string_only_expr(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _strip_docstrings(source: str) -> str:
    """Remove module/class/function docstrings via AST line ranges.

    If a node's only body element is the docstring, it is replaced by
    ``pass`` at the docstring's indent. Module docstrings are simply
    dropped (an empty module is valid). Formatting of all other lines
    is preserved.
    """
    tree = ast.parse(source)
    lines = source.split("\n")
    # removal: list of (start_line_0idx, end_line_0idx_inclusive, replacement_lines)
    removals: list[tuple[int, int, list[str]]] = []

    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        body = node.body
        if not body or not _is_string_only_expr(body[0]):
            continue
        ds = body[0]
        start = ds.lineno - 1
        end = (ds.end_lineno or ds.lineno) - 1
        if len(body) == 1 and not isinstance(node, ast.Module):
            # Need to replace with ``pass`` at the docstring's indent
            # so the def/class still has a legal body.
            indent_match = re.match(r"^(\s*)", lines[start])
            indent = indent_match.group(1) if indent_match else ""
            removals.append((start, end, [indent + "pass"]))
        else:
            removals.append((start, end, []))

    # Apply in reverse order so indices stay valid.
    removals.sort(key=lambda r: r[0], reverse=True)
    for start, end, repl in removals:
        lines[start : end + 1] = repl

    return "\n".join(lines)


def _strip_comment_lines(source: str, *, keep_header_lines: int) -> str:
    """Drop pure comment-only lines past ``keep_header_lines``.

    ``keep_header_lines`` protects the identifying header (auto-generated
    comment + V3_nearhold banner) so the file remains auditable. A line is
    a "pure comment" if its first non-whitespace character is ``#``;
    inline trailing comments on code lines are NOT removed (those would
    require a tokenize pass and savings are negligible).
    """
    lines = source.split("\n")
    out: list[str] = []
    header_emitted = 0
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("#"):
            if header_emitted < keep_header_lines:
                out.append(line)
                header_emitted += 1
                continue
            # Drop pure comment.
            continue
        out.append(line)
        # Count non-blank, non-comment lines toward the header boundary
        # only when we're still in the header region; otherwise they're
        # just normal code.
        if header_emitted < keep_header_lines and stripped:
            header_emitted += 1
    return "\n".join(out)


def _collapse_blank_lines(source: str) -> str:
    """Collapse runs of 2+ blank lines to a single blank line.

    Line-based (not regex-based) because a regex like
    ``(?:\\n[ \\t]*){3,}`` eats the leading indent of the first
    NON-blank line after the run — which breaks ``@staticmethod``
    decorators and any other indented line immediately following a
    blank gap.
    """
    out: list[str] = []
    prev_blank = False
    for line in source.split("\n"):
        is_blank = not line.strip()
        if is_blank and prev_blank:
            continue
        out.append(line)
        prev_blank = is_blank
    return "\n".join(out)


def _count_header_lines(source: str, *, banner_sentinel: str) -> int:
    """Return the 1-based line number of the V3_nearhold banner's closing rule.

    The banner ends at the FIRST ``# ====``-style rule that follows
    the ``ROUND-1 UPLOAD VARIANT: v3_nearhold`` marker (the closing rule
    of the V3_nearhold banner itself, NOT any subsequent module banner
    added by the bundler).
    """
    lines = source.split("\n")
    seen_marker = False
    for i, line in enumerate(lines, start=1):
        if banner_sentinel in line:
            seen_marker = True
            continue
        if seen_marker and line.startswith("# " + "=" * 40):
            return i
    return 0


def _minify_bundle(source: str) -> str:
    """Strip docstrings, comment-only lines, and excess blanks."""
    banner_sentinel = "ROUND-1 UPLOAD VARIANT: v3_nearhold"
    header_cut = _count_header_lines(source, banner_sentinel=banner_sentinel)
    # Safety: if the banner isn't found for some reason, keep the first
    # 3 lines (the auto-generated header only).
    if header_cut == 0:
        header_cut = 3

    source = _strip_docstrings(source)
    # Re-locate the header cut — docstring removal may have shifted
    # line numbers. We re-scan the stripped source for the same sentinel.
    header_cut = _count_header_lines(source, banner_sentinel=banner_sentinel) or 3
    source = _strip_comment_lines(source, keep_header_lines=header_cut)
    source = _collapse_blank_lines(source)
    # Final sanity: the result must still parse.
    ast.parse(source)
    return source


# --------------------------------------------------------------------------- #
# Composition                                                                 #
# --------------------------------------------------------------------------- #


def _build_v3_nearhold_source() -> str:
    # 1. Standard live bundle.
    options = ExportOptions(datamodel_mode="platform")
    bundle = build_submission_source(options)

    # 2. Patch default engine config call.
    source = _patch_default_config_call(bundle.source)

    # 3. Insert V3_nearhold banner after the auto-generated header. The
    # engine config factory's PEPPER ProductConfig uses
    # ``strategy_name="pepper_core_long"`` which is NOT in the shipped
    # ``KNOWN_STRATEGY_NAMES`` whitelist (the bundle-tail wiring
    # extends the whitelist at runtime). Temporarily augment the
    # whitelist during the export-time banner build, then restore it.
    _original_known = _config.KNOWN_STRATEGY_NAMES
    _config.KNOWN_STRATEGY_NAMES = tuple(
        sorted(set(_original_known) | {"pepper_core_long"})
    )
    try:
        config = round1_v3_nearhold_engine_config()
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

    # 4. Strip pepper_core_long.py and append its body as a new module block.
    pepper_body = _load_stripped_pepper_core_long()
    module_block = [
        "",
        "# " + "=" * 72,
        "# " + _PEPPER_CORE_LONG_PATH
        + " (V3_nearhold: research-only module, inlined at bundle tail)",
        "# " + "=" * 72,
        pepper_body,
    ]

    # 5. Append the wiring appendix.
    wiring = _build_wiring_appendix()

    composed = "\n".join(lines) + "\n" + "\n".join(module_block) + "\n" + wiring
    # Ensure trailing newline.
    if not composed.endswith("\n"):
        composed += "\n"

    # 6. Minify — strip docstrings, comment-only lines, collapse blanks.
    # Target: under the real IMC 100 KiB upload cap. Strategy logic is
    # unchanged (docstrings and comments are pure text; no runtime code
    # path reads them).
    composed = _minify_bundle(composed)
    return composed


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #


def export_v3_nearhold(*, out_dir: Path = _DEFAULT_OUT_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    source = _build_v3_nearhold_source()
    output_path = out_dir / _DEFAULT_OUT_NAME
    output_path.write_text(source, encoding="utf-8")
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=_DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)

    path = export_v3_nearhold(out_dir=args.out_dir)
    size_bytes = path.stat().st_size
    rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
    print(f"[v3_nearhold] wrote {rel} ({size_bytes} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
