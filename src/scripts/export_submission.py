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
    "src/strategies/__init__.py",
    "src/trader.py",
)

DATAMODEL_PATH: str = "src/datamodel.py"

DEFAULT_OUTPUT: Path = REPO_ROOT / "outputs" / "submissions" / "trader_submission.py"

DATAMODEL_MODES = ("platform", "inline")

_BANNER_RULE = "# " + "=" * 72


@dataclass(frozen=True)
class ExportOptions:
    """User-facing knobs for the exporter."""

    datamodel_mode: str = "platform"
    output_path: Path = DEFAULT_OUTPUT

    def __post_init__(self) -> None:
        if self.datamodel_mode not in DATAMODEL_MODES:
            raise ValueError(
                f"datamodel_mode must be one of {DATAMODEL_MODES!r} "
                f"(got {self.datamodel_mode!r})"
            )


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

    for node in tree.body:
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue

        line_range = _import_line_range(node)

        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "__future__":
                removal.update(line_range)
                continue
            if module == "src.datamodel":
                removal.update(line_range)
                datamodel_symbols.update(alias.name for alias in node.names)
                continue
            if module == "src" or module.startswith("src."):
                removal.update(line_range)
                continue

        # Non-src, non-future import: hoist the raw text.
        hoisted_indices.update(line_range)
        hoisted_imports.append("\n".join(lines[line_range.start : line_range.stop]))

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

    deps: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        module = node.module or ""
        if module == "src" or module.startswith("src."):
            deps.add(module)
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

    module_paths: list[str] = list(LIVE_MODULE_ORDER)
    if options.datamodel_mode == "inline":
        module_paths = [DATAMODEL_PATH, *module_paths]

    # Guard against the #1 long-term failure mode of a hand-maintained
    # order list: forgetting to add a new live module. This raises
    # before any bundling work so the error message is the first
    # thing the caller sees.
    verify_live_module_order(list(LIVE_MODULE_ORDER), root=root)

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
