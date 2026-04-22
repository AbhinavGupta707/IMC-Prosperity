"""Bundle the live trading engine into a single submission file.

Prosperity expects one ``.py`` file whose top-level namespace contains a
``Trader`` class with a ``run()`` method. Our engine is split across
many small modules for clarity and test isolation, so this script is
the single place that knows how to flatten those modules back into one
file without changing semantics.

Design notes:

- **Textual concat**. We read each file as text, use ``ast`` only to
  find import line ranges, and slice them out. Everything else
  (comments, blank lines, docstrings) is preserved. This is on purpose:
  the bundled file is the audit trail for what actually shipped.

- **Explicit dependency order**. ``LIVE_MODULE_ORDER`` below is
  hand-maintained. If a new module is added to the live path, it must
  be registered here. The exporter refuses to run otherwise. This
  makes the live surface an explicit, versioned decision instead of
  something that silently changes with a directory scan.

- **Two datamodel modes**. The Prosperity container provides its own
  ``datamodel`` module. The default ``--datamodel=platform`` mode emits
  ``from datamodel import ...`` at the top of the bundle so the real
  platform types are used. ``--datamodel=inline`` inlines our local
  ``src/datamodel.py`` instead, producing a self-contained file that
  can be imported and smoke-tested without monkey-patching
  ``sys.modules``. The test suite uses ``inline`` for its dry-run
  smoke test.

- **What this script does NOT do**: optimize, minify, or rename. The
  bundled file is as close to the original source as possible so a
  human can still read it.
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Hand-maintained topological order of live-path modules. Everything
# depends on what comes before it in this list.
LIVE_MODULE_ORDER: tuple[str, ...] = (
    "src/core/utils.py",
    "src/core/types.py",
    # Config is split: config_core.py holds the types (ProductConfig,
    # EngineConfig, with_bid_value) and config.py adds the R1/R2 product
    # factories. Core must precede the wrapper so re-exports resolve.
    "src/core/config_core.py",
    "src/core/config.py",
    "src/core/logger.py",
    "src/core/market_data.py",
    "src/core/fair_value.py",
    "src/core/state_store.py",
    "src/signals/__init__.py",
    "src/signals/flow_analyzer.py",
    "src/core/signals.py",
    "src/core/execution.py",
    "src/core/risk.py",
    "src/core/residual.py",
    "src/strategies/base.py",
    "src/strategies/market_making.py",
    "src/strategies/buy_and_hold.py",
    "src/strategies/__init__.py",
    "src/trader.py",
)
# NOTE: ``src/core/primitives/*`` and ``src/conversions/*`` are deliberately
# NOT in the R2 bundle. R2 Prosperity submissions construct Trader with
# orchestrator=None, so shipping those modules would waste the 120KB
# bundle budget. R3+ submissions use ``R3_MODULE_ORDER`` below.

# R3+ extension. Adds only the cross-product primitives the Trader +
# Orchestrator CONTRACT needs. Engine-specific helpers (sst,
# volume_robust_mid, hysteresis_sizer, predictive_estimator) and
# research-only modules (signal_validation, sweep_selector) are
# deliberately NOT in this default; opt them in per submission via
# ``ExportOptions.extra_modules`` when the engines that consume them
# are being shipped, to keep the core R3 bundle under 128 KB.
#
# Modules omitted on purpose:
#   - config.py              — R1/R2 product factories (factories
#                              not used by an orchestrator-driven Trader)
#   - fill_calibration.py    — offline backtest harness (imports src.backtest.*)
#   - sst.py                 — consumed by engines, not by Trader directly
#   - volume_robust_mid.py   — ditto
#   - hysteresis_sizer.py    — ditto
#   - predictive_estimator.py — fair-value extension, opt-in per product
#   - signal_validation.py   — offline validation harness
#   - sweep_selector.py      — offline sweep-evaluation harness
#
# Only ``config_core.py`` (types) is carried. ``default_engine_config``
# is imported lazily inside ``Trader.__init__`` only when no config is
# supplied, which never happens for an R3 submission that builds its
# own EngineConfig.
def _r3_modules() -> tuple[str, ...]:
    # Drop R1/R2-only modules that an orchestrator-driven Trader never
    # loads: the product factories, the fair-value engine (lazy-loaded
    # only when a product has a strategy_name), and the single-product
    # strategies. This saves ~37 KB vs shipping the full R2 base.
    drop = {
        "src/core/config.py",
        "src/core/fair_value.py",
        "src/strategies/base.py",
        "src/strategies/market_making.py",
        "src/strategies/buy_and_hold.py",
        "src/strategies/__init__.py",
    }
    base = tuple(m for m in LIVE_MODULE_ORDER[:-1] if m not in drop)
    return base + (
        "src/core/primitives/__init__.py",
        "src/core/primitives/crash_telemetry.py",
        "src/core/primitives/portfolio_context.py",
        "src/core/primitives/portfolio_risk.py",
        "src/core/primitives/signal_bus.py",
        "src/core/primitives/engine_orchestrator.py",
        "src/conversions/__init__.py",
        "src/conversions/layer.py",
        "src/conversions/adapter.py",
        "src/trader.py",
    )


R3_MODULE_ORDER: tuple[str, ...] = _r3_modules()

DATAMODEL_PATH: str = "src/datamodel.py"

DEFAULT_OUTPUT: Path = REPO_ROOT / "outputs" / "submissions" / "trader_submission.py"

DATAMODEL_MODES = ("platform", "inline")
EXPORT_PROFILES = ("r2", "r3")

_BANNER_RULE = "# " + "=" * 72


@dataclass(frozen=True)
class ExportOptions:
    """User-facing knobs for the exporter.

    ``profile`` selects the module-order manifest:

    - ``"r2"`` (default): the R1/R2 live path — no orchestrator, no
      primitives, no conversion plumbing. Produces a ~65 KB bundle
      that stays well under the 120 KB hard cap.
    - ``"r3"``: R1/R2 core PLUS cross-product primitives and the
      conversion adapter. Use when the shipped Trader constructs an
      ``EngineOrchestrator``. Expect ~100 KB; engines (options_mm,
      basket_arb, stat_arb, counterparty_intel) are deliberately opt-in
      per submission — add them via ``extra_modules``.
    """

    datamodel_mode: str = "platform"
    output_path: Path = DEFAULT_OUTPUT
    profile: str = "r2"
    extra_modules: tuple[str, ...] = ()
    """Extra ``src/...`` paths appended to the selected profile's order.

    Use for per-round engine opt-in (e.g. add
    ``("src/options/bsm.py", "src/engines/options_mm.py")`` when
    shipping an options engine). Paths must exist under the repo root.
    """

    def __post_init__(self) -> None:
        if self.datamodel_mode not in DATAMODEL_MODES:
            raise ValueError(
                f"datamodel_mode must be one of {DATAMODEL_MODES!r} "
                f"(got {self.datamodel_mode!r})"
            )
        if self.profile not in EXPORT_PROFILES:
            raise ValueError(
                f"profile must be one of {EXPORT_PROFILES!r} (got {self.profile!r})"
            )


def _module_order_for(profile: str) -> tuple[str, ...]:
    if profile == "r3":
        return R3_MODULE_ORDER
    return LIVE_MODULE_ORDER


@dataclass
class StrippedModule:
    """Parsed view of a single source file."""

    path: str
    body: str
    hoisted_imports: list[str] = field(default_factory=list)
    datamodel_symbols: set[str] = field(default_factory=set)


@dataclass
class Bundle:
    """Result of :func:`build_submission_source`."""

    source: str
    module_count: int
    datamodel_mode: str
    datamodel_symbols: tuple[str, ...]
    hoisted_import_count: int

    @property
    def size_bytes(self) -> int:
        return len(self.source.encode("utf-8"))


# ---------------------------------------------------------------- parsing


def _read_module(path: str, *, root: Path) -> str:
    full = root / path
    if not full.exists():
        raise FileNotFoundError(f"Live module not found: {path}")
    return full.read_text(encoding="utf-8")


def _import_line_range(node: ast.stmt) -> range:
    start = node.lineno - 1
    end = node.end_lineno or node.lineno
    return range(start, end)


def strip_module(path: str, source: str) -> StrippedModule:
    """Split ``source`` into hoisted imports, stripped src imports, and body.

    - ``from __future__`` lines are removed (the bundler emits one at
      the very top of the output).
    - ``from src.*`` lines are removed (their symbols are already in
      the bundle's global namespace).
    - ``from src.datamodel import X`` lines are removed and the named
      symbols are tracked so the bundler can emit one
      ``from datamodel import ...`` header in platform mode.
    - Everything else — stdlib and third-party imports — is collected
      as ``hoisted_imports`` so the bundler can put them once at the
      top and strip duplicates.
    - The remaining body preserves all other comments, blank lines,
      docstrings, and statements verbatim.
    """
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"Failed to parse {path}: {exc}") from exc

    lines = source.splitlines()
    removal: set[int] = set()
    hoisted_indices: set[int] = set()
    hoisted_imports: list[str] = []
    datamodel_symbols: set[str] = set()

    def _process_import_node(node: ast.stmt, *, hoist: bool) -> None:
        line_range = _import_line_range(node)
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "__future__":
                removal.update(line_range)
                return
            if module == "src.datamodel":
                removal.update(line_range)
                datamodel_symbols.update(alias.name for alias in node.names)
                return
            if module == "src" or module.startswith("src."):
                removal.update(line_range)
                return
        elif isinstance(node, ast.Import):
            # ``import src.core.config_core as _core`` — strip entirely,
            # and also strip any non-src ``import X`` that was given a
            # single alias? We only touch src.* names; non-src plain
            # imports fall through to the hoist path.
            if all(
                alias.name == "src" or alias.name.startswith("src.")
                for alias in node.names
            ) and node.names:
                removal.update(line_range)
                return
        if not hoist:
            # Nested (non-top-level) non-src imports stay in the body so
            # the local code path still works (e.g., a function-level
            # stdlib import). We only hoist from module scope.
            return
        hoisted_indices.update(line_range)
        hoisted_imports.append("\n".join(lines[line_range.start : line_range.stop]))

    def _scan_typecheck_block(if_node: ast.If) -> None:
        """Strip the entire ``if TYPE_CHECKING:`` block.

        By convention these blocks contain only import statements for
        type-only references that never run at runtime. Removing the
        block outright avoids "expected an indented block" syntax
        errors after the inner imports are stripped. The condition
        must be a bare ``TYPE_CHECKING`` name or ``typing.TYPE_CHECKING``
        attribute access; other ``if`` blocks at module scope are
        ignored.
        """
        test = if_node.test
        is_tc = False
        if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
            is_tc = True
        elif (
            isinstance(test, ast.Attribute)
            and test.attr == "TYPE_CHECKING"
        ):
            is_tc = True
        if not is_tc:
            return
        # Remove the whole block — header plus body (including any
        # ``else`` branch, which by convention is empty here).
        start = if_node.lineno - 1
        end = if_node.end_lineno or if_node.lineno
        removal.update(range(start, end))

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            _process_import_node(node, hoist=True)
            continue
        if isinstance(node, ast.If):
            _scan_typecheck_block(node)

    # Strip nested ``from src.*`` imports at any depth (e.g. lazy imports
    # inside function bodies used by R3+ code paths). In the submission
    # bundle those modules aren't shipped; the lazy path is unreachable
    # because the orchestrator is always disabled in R1/R2 bundles, so
    # removing the import line just avoids validator false-positives.
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        module = node.module or ""
        if module != "src" and not module.startswith("src."):
            continue
        if module == "src.datamodel":
            continue  # handled separately
        start = node.lineno - 1
        end = node.end_lineno or node.lineno
        removal.update(range(start, end))

    body_lines = [
        line for idx, line in enumerate(lines) if idx not in removal and idx not in hoisted_indices
    ]
    # Trim leading / trailing blank lines on the module body so
    # consecutive modules in the bundle don't accumulate giant gaps.
    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)
    while body_lines and not body_lines[-1].strip():
        body_lines.pop()
    body = "\n".join(body_lines)

    return StrippedModule(
        path=path,
        body=body,
        hoisted_imports=hoisted_imports,
        datamodel_symbols=datamodel_symbols,
    )


# --------------------------------------------------------------- assembly


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _module_banner(path: str) -> str:
    return f"{_BANNER_RULE}\n# {path}\n{_BANNER_RULE}"


# --------------------------------------------------------- completeness


def _resolve_src_module(module: str, root: Path) -> Path | None:
    """Turn a ``src.x.y`` module name into a filesystem path.

    Tries ``src/x/y.py`` first, then ``src/x/y/__init__.py``. Returns
    ``None`` if neither exists.
    """
    if not module.startswith("src."):
        return None
    dotted = module[len("src.") :]
    module_file = root / "src" / (dotted.replace(".", "/") + ".py")
    if module_file.is_file():
        return module_file
    package_file = root / "src" / dotted.replace(".", "/") / "__init__.py"
    if package_file.is_file():
        return package_file
    return None


def _collect_src_imports(source: str, *, path: str) -> set[str]:
    """Return every top-level ``src.*`` module name imported by ``source``."""
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"Failed to parse {path}: {exc}") from exc

    def _in_typecheck_block(path_stack: tuple[ast.AST, ...]) -> bool:
        """True if this node is nested under ``if TYPE_CHECKING:``.

        TYPE_CHECKING-guarded imports never run at runtime and are
        stripped by ``strip_module``, so they must not trigger the
        completeness check.
        """
        for anc in path_stack:
            if not isinstance(anc, ast.If):
                continue
            test = anc.test
            if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
                return True
            if (
                isinstance(test, ast.Attribute)
                and test.attr == "TYPE_CHECKING"
            ):
                return True
        return False

    deps: set[str] = set()

    def _walk(node: ast.AST, stack: tuple[ast.AST, ...]) -> None:
        modules_from_node: list[str] = []
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "src" or module.startswith("src."):
                modules_from_node.append(module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "src" or alias.name.startswith("src."):
                    modules_from_node.append(alias.name)
        if modules_from_node:
            # Runtime src imports only: skip function/method-body
            # imports (lazy), skip TYPE_CHECKING blocks.
            if _in_typecheck_block(stack):
                return
            if any(
                isinstance(anc, (ast.FunctionDef, ast.AsyncFunctionDef))
                for anc in stack
            ):
                return
            deps.update(modules_from_node)
            return
        for child in ast.iter_child_nodes(node):
            _walk(child, stack + (node,))

    _walk(tree, ())
    return deps


def verify_live_module_order(
    module_paths: list[str],
    *,
    root: Path,
) -> None:
    """Fail loudly if a live module imports something not in the order list.

    The exporter is intentionally driven by an explicit
    ``LIVE_MODULE_ORDER`` so that adding a new live module is a single,
    reviewable line change. This check is the safety net that catches
    the common mistake of adding the new module and forgetting to
    register it: if *any* module currently in the order list imports
    a ``src.*`` target that is not on the list (and is not the
    datamodel, which has its own platform / inline handling), we
    raise immediately with a clear message.

    Unresolvable imports (e.g. ``from src.future_feature import X``
    where the file does not exist) are surfaced as errors too, because
    they indicate either a typo or a dangling reference.
    """
    allowed_files = {(root / p).resolve() for p in [*module_paths, DATAMODEL_PATH]}
    missing: dict[str, list[str]] = {}
    unresolved: dict[str, list[str]] = {}

    for module_path in module_paths:
        if module_path == DATAMODEL_PATH:
            continue
        source = _read_module(module_path, root=root)
        for dep in sorted(_collect_src_imports(source, path=module_path)):
            if dep == "src.datamodel":
                continue  # handled by platform / inline modes
            resolved = _resolve_src_module(dep, root)
            if resolved is None:
                unresolved.setdefault(module_path, []).append(dep)
                continue
            if resolved.resolve() not in allowed_files:
                missing.setdefault(module_path, []).append(dep)

    if not missing and not unresolved:
        return

    lines = [
        "Live-path completeness check failed. "
        "LIVE_MODULE_ORDER is missing one or more modules that are "
        "imported by the current live path:"
    ]
    for src_path in sorted(missing):
        for dep in missing[src_path]:
            resolved = _resolve_src_module(dep, root)
            target = resolved.relative_to(root).as_posix() if resolved is not None else "?"
            lines.append(
                f"  - {src_path} imports {dep!r} -> {target} "
                "(add the target to LIVE_MODULE_ORDER)"
            )
    for src_path in sorted(unresolved):
        for dep in unresolved[src_path]:
            lines.append(
                f"  - {src_path} imports {dep!r} but no matching file was "
                "found under src/ (typo or dangling reference)"
            )
    raise RuntimeError("\n".join(lines))


def build_submission_source(
    options: ExportOptions | None = None,
    *,
    root: Path | None = None,
) -> Bundle:
    """Assemble the flat submission source string.

    The returned :class:`Bundle` is side-effect free: nothing is written
    to disk. Call :func:`write_submission` to persist it.
    """
    options = options or ExportOptions()
    root = root or REPO_ROOT

    base_order = list(_module_order_for(options.profile))
    # Append per-submission extra modules (engines, options math, etc).
    # De-dupe while preserving order so calling with extras containing
    # a path already in the profile is a no-op.
    seen_in_base = set(base_order)
    for extra in options.extra_modules:
        if extra in seen_in_base:
            continue
        base_order.append(extra)
        seen_in_base.add(extra)

    module_paths: list[str] = list(base_order)
    if options.datamodel_mode == "inline":
        module_paths = [DATAMODEL_PATH, *module_paths]

    # Guard against the #1 long-term failure mode of a hand-maintained
    # order list: forgetting to add a new live module. This raises
    # before any bundling work so the error message is the first
    # thing the caller sees.
    verify_live_module_order(base_order, root=root)

    stripped_modules: list[StrippedModule] = []
    all_hoisted: list[str] = []
    all_datamodel_symbols: set[str] = set()

    for module_path in module_paths:
        source = _read_module(module_path, root=root)
        stripped = strip_module(module_path, source)
        stripped_modules.append(stripped)
        all_hoisted.extend(stripped.hoisted_imports)
        all_datamodel_symbols.update(stripped.datamodel_symbols)

    hoisted_imports = _dedupe_preserve_order(all_hoisted)
    datamodel_symbols = tuple(sorted(all_datamodel_symbols))

    parts: list[str] = []
    parts.append(
        "# Auto-generated by src/scripts/export_submission.py. DO NOT EDIT.\n"
        f"# Datamodel mode: {options.datamodel_mode}.\n"
        f"# Source modules: {len(module_paths)}."
    )
    parts.append("from __future__ import annotations")

    if options.datamodel_mode == "platform" and datamodel_symbols:
        parts.append("from datamodel import " + ", ".join(datamodel_symbols))

    if hoisted_imports:
        parts.append("\n".join(hoisted_imports))

    for stripped in stripped_modules:
        parts.append(_module_banner(stripped.path))
        parts.append(stripped.body)

    source = "\n\n".join(part for part in parts if part).rstrip() + "\n"

    return Bundle(
        source=source,
        module_count=len(stripped_modules),
        datamodel_mode=options.datamodel_mode,
        datamodel_symbols=datamodel_symbols,
        hoisted_import_count=len(hoisted_imports),
    )


def write_submission(bundle: Bundle, path: Path) -> Path:
    """Write ``bundle.source`` to ``path`` (creating parents as needed)."""
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(bundle.source, encoding="utf-8")
    return path


# -------------------------------------------------------------------- cli


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="export_submission",
        description="Bundle the live trading engine into one submission file.",
    )
    parser.add_argument(
        "--datamodel",
        choices=DATAMODEL_MODES,
        default="platform",
        help=(
            "How to handle datamodel types. 'platform' (default) imports "
            "from the Prosperity-provided datamodel module and is the only "
            "mode suitable for real submissions. 'inline' copies "
            "src/datamodel.py into the bundle; this produces a DEV-ONLY "
            "self-contained file used by the local smoke tests and MUST "
            "NOT be uploaded to Prosperity."
        ),
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output path (default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print the bundled source to stdout instead of writing to --output.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the summary line (useful for piping).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    options = ExportOptions(
        datamodel_mode=args.datamodel,
        output_path=args.output,
    )
    bundle = build_submission_source(options)

    if args.stdout:
        sys.stdout.write(bundle.source)
        return 0

    path = write_submission(bundle, options.output_path)
    if not args.quiet:
        rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
        print(
            f"Exported {bundle.module_count} modules "
            f"({bundle.size_bytes} bytes, datamodel={bundle.datamodel_mode}) "
            f"to {rel}"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
