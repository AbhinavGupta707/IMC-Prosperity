"""Validate a bundled Prosperity submission file.

This is the single source of truth for what "submission-ready" means
structurally. It runs on the *bundled* output of
:mod:`src.scripts.export_submission` (never on the live ``src/``
source tree), and answers one question:

    If we uploaded this file right now, would the Prosperity runtime
    accept it and be able to call ``Trader.run(state)``?

It does *not* answer "is the strategy good". That is the job of the
backtest / review pipeline.

Checks (all AST-based; the file is parsed once and walked):

- **structure**: exactly one module-level ``class Trader`` exists, and
  it defines a ``run`` method with ``self`` plus at least one argument.
- **return contract**: ``Trader.run`` contains at least one ``return``
  whose value is a three-tuple (best-effort static check; the runtime
  smoke test in :mod:`tests.test_submission_export` is the strict one).
- **forbidden imports**: anything in ``FORBIDDEN_IMPORT_ROOTS`` (network
  sockets, subprocess, importlib hacks) is an ERROR. Anything in
  ``DEV_ONLY_IMPORT_ROOTS`` (src.backtest, src.scripts, tests, pytest)
  is an ERROR because it proves the bundler failed or a dev-only file
  leaked into the live path.
- **no residual src imports**: if any ``from src.*`` line survives in
  the bundled file, the exporter is broken.
- **no file I/O**: bare ``open(...)`` calls and ``os.system`` /
  ``os.popen`` are ERRORs; ``.read_text`` / ``.write_text`` /
  ``.write_bytes`` method calls are WARNs because they may be false
  positives on unrelated ``.write_text`` attributes.
- **debug artifacts**: ``print(...)`` calls are WARNs. The engine uses
  the logging module for diagnostics; ``print`` is usually a leftover.
- **size**: two thresholds. Above ``SOFT_SIZE_BYTES`` is a WARN
  ("you are getting close"), above ``MAX_SIZE_BYTES`` is an ERROR
  ("do not upload this"). The report header always prints the
  current size alongside both thresholds.
- **inline dev-only marker**: if the bundle header shows
  ``Datamodel mode: inline``, we raise a WARN that the artifact is
  dev-only and must not be uploaded to Prosperity. The exporter
  marks the mode in the top banner; the validator is the
  independent double-check.

The validator is intentionally strict on "clearly wrong" and lenient
on "probably fine". A WARN never fails CI; an ERROR always does.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TARGET = REPO_ROOT / "outputs" / "submissions" / "trader_submission.py"

# Hard-coded budgets. Prosperity has historically capped submissions
# around 128 KiB of source; we stay comfortably under that.
#
# Two thresholds:
# - ``SOFT_SIZE_BYTES`` raises a WARN — "you are getting close,
#   time to think about what is in the live path".
# - ``MAX_SIZE_BYTES`` raises an ERROR — "do not upload this".
#
# The soft threshold is deliberately well below the hard ceiling so
# that a WARN gives us meaningful lead time as the codebase grows.
SOFT_SIZE_BYTES: int = 72 * 1024
MAX_SIZE_BYTES: int = 96 * 1024

# Modules a live submission must never import. Roots are matched as
# either an exact module name or a prefix (``x.y.z`` matches ``x``).
FORBIDDEN_IMPORT_ROOTS: frozenset[str] = frozenset(
    {
        "subprocess",
        "socket",
        "urllib",
        "http",
        "httpx",
        "requests",
        "aiohttp",
        "smtplib",
        "ftplib",
        "imaplib",
        "poplib",
        "xmlrpc",
        "importlib",
        "ctypes",
        "multiprocessing",
    }
)

# Dev-only / test-only modules. If the bundler does its job, none of
# these should appear in the output. Their presence is an error
# because they prove the live path has leaked.
DEV_ONLY_IMPORT_ROOTS: frozenset[str] = frozenset(
    {
        "src.backtest",
        "src.scripts",
        "tests",
        "pytest",
        "unittest",
        "mock",
        "notebooks",
    }
)

# Method attribute names that look like file I/O. These are WARNs, not
# ERRORs, because they can be false positives on unrelated classes.
IO_METHOD_ATTRS: frozenset[str] = frozenset(
    {"read_text", "write_text", "read_bytes", "write_bytes"}
)

Severity = str  # "error" | "warn"
ERROR: Severity = "error"
WARN: Severity = "warn"


@dataclass(frozen=True)
class Issue:
    severity: Severity
    code: str
    message: str
    line: int = 0

    def format(self) -> str:
        loc = f"line {self.line}" if self.line else "-"
        return f"[{self.severity.upper()}] {self.code} ({loc}): {self.message}"


@dataclass
class ValidationReport:
    target: Path
    size_bytes: int
    issues: list[Issue]

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == WARN]

    @property
    def ok(self) -> bool:
        return not self.errors

    def format(self) -> str:
        soft_pct = 100.0 * self.size_bytes / SOFT_SIZE_BYTES if SOFT_SIZE_BYTES else 0.0
        hard_pct = 100.0 * self.size_bytes / MAX_SIZE_BYTES if MAX_SIZE_BYTES else 0.0
        lines = [
            f"Validation target: {self.target}",
            (
                f"Size: {self.size_bytes} bytes "
                f"(soft {SOFT_SIZE_BYTES}, hard {MAX_SIZE_BYTES}, "
                f"{soft_pct:.0f}% of soft / {hard_pct:.0f}% of hard)"
            ),
            f"Issues: {len(self.errors)} error(s), {len(self.warnings)} warning(s)",
        ]
        for issue in self.issues:
            lines.append("  " + issue.format())
        if self.ok:
            lines.append("Result: OK")
        else:
            lines.append("Result: FAIL")
        return "\n".join(lines)


# ------------------------------------------------------------------ scan


def _import_root(module: str) -> str:
    return module.split(".", 1)[0]


def _is_forbidden(module: str) -> bool:
    if module in FORBIDDEN_IMPORT_ROOTS:
        return True
    root = _import_root(module)
    return root in FORBIDDEN_IMPORT_ROOTS


def _is_dev_only(module: str) -> bool:
    if module in DEV_ONLY_IMPORT_ROOTS:
        return True
    for prefix in DEV_ONLY_IMPORT_ROOTS:
        if module == prefix or module.startswith(prefix + "."):
            return True
    return False


def _is_residual_src_import(module: str) -> bool:
    return module == "src" or module.startswith("src.")


def _check_imports(tree: ast.AST) -> list[Issue]:
    issues: list[Issue] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name
                issues.extend(_issues_for_module(module, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if not module:
                continue
            issues.extend(_issues_for_module(module, node.lineno))
    return issues


def _issues_for_module(module: str, line: int) -> list[Issue]:
    out: list[Issue] = []
    if _is_forbidden(module):
        out.append(
            Issue(
                severity=ERROR,
                code="forbidden_import",
                message=f"submission imports forbidden module {module!r}",
                line=line,
            )
        )
    if _is_dev_only(module):
        out.append(
            Issue(
                severity=ERROR,
                code="dev_only_import",
                message=f"submission imports dev-only module {module!r}",
                line=line,
            )
        )
    if _is_residual_src_import(module):
        out.append(
            Issue(
                severity=ERROR,
                code="residual_src_import",
                message=(
                    f"bundled file still imports {module!r}; the exporter "
                    "should have stripped this"
                ),
                line=line,
            )
        )
    return out


def _find_trader_class(tree: ast.Module) -> ast.ClassDef | None:
    matches = [
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Trader"
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def _find_run_method(cls: ast.ClassDef) -> ast.FunctionDef | None:
    for node in cls.body:
        if isinstance(node, ast.FunctionDef) and node.name == "run":
            return node
    return None


def _check_structure(tree: ast.Module) -> list[Issue]:
    issues: list[Issue] = []
    trader_class = _find_trader_class(tree)
    if trader_class is None:
        issues.append(
            Issue(
                severity=ERROR,
                code="missing_trader",
                message="bundled file does not define a top-level class Trader",
            )
        )
        return issues

    run = _find_run_method(trader_class)
    if run is None:
        issues.append(
            Issue(
                severity=ERROR,
                code="missing_run",
                message="class Trader is missing a run() method",
                line=trader_class.lineno,
            )
        )
        return issues

    # Must accept at least (self, state).
    positional = [*run.args.posonlyargs, *run.args.args]
    if len(positional) < 2:
        issues.append(
            Issue(
                severity=ERROR,
                code="run_signature",
                message=(
                    f"Trader.run must accept at least (self, state) "
                    f"(got {len(positional)} positional arg(s))"
                ),
                line=run.lineno,
            )
        )

    # Best-effort: at least one return statement inside run must return
    # a 3-tuple. This is static — the real proof is the dry-run smoke
    # test that imports the file and calls run() on a fake state.
    has_three_tuple_return = False
    for child in ast.walk(run):
        if (
            isinstance(child, ast.Return)
            and isinstance(child.value, ast.Tuple)
            and len(child.value.elts) == 3
        ):
            has_three_tuple_return = True
            break
    if not has_three_tuple_return:
        issues.append(
            Issue(
                severity=WARN,
                code="return_shape",
                message=(
                    "Trader.run has no literal 3-tuple return; relying on "
                    "delegation. The runtime smoke test is the strict check."
                ),
                line=run.lineno,
            )
        )

    return issues


def _check_forbidden_calls(tree: ast.AST) -> list[Issue]:
    issues: list[Issue] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func

        if isinstance(func, ast.Name):
            if func.id == "open":
                issues.append(
                    Issue(
                        severity=ERROR,
                        code="file_io_open",
                        message="bare open() call is forbidden in live path",
                        line=node.lineno,
                    )
                )
            elif func.id == "print":
                issues.append(
                    Issue(
                        severity=WARN,
                        code="debug_print",
                        message="print() call found; use logging instead",
                        line=node.lineno,
                    )
                )

        elif isinstance(func, ast.Attribute):
            if func.attr in IO_METHOD_ATTRS:
                issues.append(
                    Issue(
                        severity=WARN,
                        code="maybe_file_io",
                        message=(
                            f"method call .{func.attr}() looks like file I/O; "
                            "verify it is not touching disk"
                        ),
                        line=node.lineno,
                    )
                )
            if (
                func.attr in ("system", "popen")
                and isinstance(func.value, ast.Name)
                and func.value.id == "os"
            ):
                issues.append(
                    Issue(
                        severity=ERROR,
                        code="os_process",
                        message=f"os.{func.attr}() is forbidden in live path",
                        line=node.lineno,
                    )
                )
    return issues


def _check_size(source: str) -> list[Issue]:
    size = len(source.encode("utf-8"))
    if size > MAX_SIZE_BYTES:
        return [
            Issue(
                severity=ERROR,
                code="oversize",
                message=(
                    f"bundled file is {size} bytes, exceeds hard budget of "
                    f"{MAX_SIZE_BYTES} bytes"
                ),
            )
        ]
    if size > SOFT_SIZE_BYTES:
        return [
            Issue(
                severity=WARN,
                code="size_approaching_limit",
                message=(
                    f"bundled file is {size} bytes, above soft budget of "
                    f"{SOFT_SIZE_BYTES} bytes (hard budget "
                    f"{MAX_SIZE_BYTES} bytes); trim the live path before "
                    "the hard ceiling is hit"
                ),
            )
        ]
    return []


# Header fragment emitted by ``src.scripts.export_submission`` when the
# bundle was built with ``--datamodel=inline``. Detecting it on the
# validator side lets us warn loudly that the artifact is dev-only,
# even when a user copies the inline bundle around manually.
_INLINE_HEADER_MARKER = "Datamodel mode: inline"


def _check_inline_dev_only(source: str) -> list[Issue]:
    # Only inspect the first ~400 chars to avoid false positives from
    # arbitrary strings later in the file. The exporter writes the
    # marker in the first comment block.
    header = source[:400]
    if _INLINE_HEADER_MARKER not in header:
        return []
    return [
        Issue(
            severity=WARN,
            code="inline_datamodel_dev_only",
            message=(
                "bundle was built with --datamodel=inline; this is a "
                "DEV-ONLY artifact for local smoke tests and MUST NOT be "
                "uploaded to Prosperity. Re-export with the default "
                "--datamodel=platform before submission."
            ),
        )
    ]


# -------------------------------------------------------------- public api


def validate_source(source: str, *, target: Path | None = None) -> ValidationReport:
    """Validate an in-memory bundled submission string.

    Used by both the CLI (``validate`` reads from disk) and the test
    suite (``validate_source`` skips the file system).
    """
    issues: list[Issue] = []
    issues.extend(_check_size(source))
    issues.extend(_check_inline_dev_only(source))

    try:
        tree = ast.parse(source, filename=str(target or "<bundle>"))
    except SyntaxError as exc:
        issues.append(
            Issue(
                severity=ERROR,
                code="syntax_error",
                message=f"bundled file failed to parse: {exc.msg}",
                line=exc.lineno or 0,
            )
        )
        return ValidationReport(
            target=target or Path("<bundle>"),
            size_bytes=len(source.encode("utf-8")),
            issues=issues,
        )

    issues.extend(_check_structure(tree))
    issues.extend(_check_imports(tree))
    issues.extend(_check_forbidden_calls(tree))

    return ValidationReport(
        target=target or Path("<bundle>"),
        size_bytes=len(source.encode("utf-8")),
        issues=issues,
    )


def validate_file(path: Path) -> ValidationReport:
    path = path.expanduser().resolve()
    if not path.exists():
        return ValidationReport(
            target=path,
            size_bytes=0,
            issues=[
                Issue(
                    severity=ERROR,
                    code="missing_file",
                    message=f"no submission file at {path}",
                )
            ],
        )
    source = path.read_text(encoding="utf-8")
    return validate_source(source, target=path)


# -------------------------------------------------------------------- cli


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate_submission",
        description="Validate a bundled Prosperity submission file.",
    )
    parser.add_argument(
        "target",
        type=Path,
        nargs="?",
        default=DEFAULT_TARGET,
        help=f"Path to the bundled submission (default: {DEFAULT_TARGET}).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print the final OK/FAIL line.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = validate_file(args.target)

    if args.quiet:
        print("OK" if report.ok else "FAIL")
    else:
        print(report.format())

    return 0 if report.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
