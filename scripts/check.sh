#!/usr/bin/env bash
# Local CI-style gate for the IMC Prosperity repo.
#
# This script exists so that "did I break something" has one answer you
# can run before a commit or a submission. Each step is independent;
# the script runs them all and exits non-zero if any failed. That way
# you see every failure in one pass instead of fixing them one at a
# time.
#
# Two conceptual gates share this one script:
#
# 1. **Repo-wide gate** (default). Runs every lint, type check, and
#    test across ``src`` and ``tests``. This is honest but noisy:
#    it surfaces pre-existing issues in earlier-phase WIP files.
#
# 2. **Submission-critical gate** (``--submission``). Runs the same
#    checks but narrowed to the files that actually ship in the
#    Prosperity submission plus the Phase 9 packaging surface.
#    Nothing else. Use this before every real upload — it is the
#    signal that "whatever is in the live path will import, run,
#    and bundle into a valid submission right now."
#
# Steps (in order):
#   1. ruff   (lint)
#   2. black --check (formatting)
#   3. mypy   (static types)
#   4. pytest (unit + integration)
#   5. export_submission  (build the platform-mode bundle)
#   6. validate_submission (check the bundle we just built)
#   7. smoke: the dry-run tests are already part of pytest, so if
#      pytest passed the smoke is already green. No second run needed.
#
# Usage:
#   ./scripts/check.sh                  # repo-wide, runs everything
#   ./scripts/check.sh --submission     # submission-critical scope only
#   ./scripts/check.sh --fast           # skip mypy (slowest step)
#   ./scripts/check.sh --export-only    # only export + validate
#
# Flags compose: ``--submission --fast`` is valid and runs the
# submission-critical scope without mypy.
#
# The script honors a ``PYTHON`` env var so CI can point it at a
# specific interpreter. It defaults to ``.venv/bin/python`` if that
# exists, otherwise ``python3``.

set -u

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

PYTHON="${PYTHON:-}"
if [[ -z "${PYTHON}" ]]; then
    if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
        PYTHON="${REPO_ROOT}/.venv/bin/python"
    else
        PYTHON="python3"
    fi
fi

FAST=0
EXPORT_ONLY=0
SUBMISSION_ONLY=0
for arg in "$@"; do
    case "${arg}" in
        --fast) FAST=1 ;;
        --export-only) EXPORT_ONLY=1 ;;
        --submission) SUBMISSION_ONLY=1 ;;
        -h|--help)
            sed -n '2,45p' "$0"
            exit 0
            ;;
        *)
            echo "Unknown option: ${arg}" >&2
            exit 2
            ;;
    esac
done

# Submission-critical scope: every module that actually ships in the
# bundle plus the Phase 9 packaging surface. Any change here must be
# mirrored against the exporter's LIVE_MODULE_ORDER so the two stay
# consistent.
SUBMISSION_PATHS=(
    src/datamodel.py
    src/trader.py
    src/core
    src/strategies
    src/scripts/export_submission.py
    src/scripts/validate_submission.py
    tests/test_submission_export.py
)

red()   { printf '\033[31m%s\033[0m\n' "$1"; }
green() { printf '\033[32m%s\033[0m\n' "$1"; }
blue()  { printf '\033[34m%s\033[0m\n' "$1"; }

declare -a FAILURES=()

run_step() {
    local name="$1"
    shift
    blue "==> ${name}"
    if "$@"; then
        green "    ${name}: ok"
    else
        red "    ${name}: FAIL"
        FAILURES+=("${name}")
    fi
    echo
}

if [[ "${SUBMISSION_ONLY}" -eq 1 ]]; then
    blue "Scope: submission-critical (${#SUBMISSION_PATHS[@]} paths)"
    echo
fi

if [[ "${EXPORT_ONLY}" -eq 0 ]]; then
    if [[ "${SUBMISSION_ONLY}" -eq 1 ]]; then
        run_step "ruff" \
            "${PYTHON}" -m ruff check "${SUBMISSION_PATHS[@]}"
        run_step "black --check" \
            "${PYTHON}" -m black --check "${SUBMISSION_PATHS[@]}"
        if [[ "${FAST}" -eq 0 ]]; then
            run_step "mypy" \
                "${PYTHON}" -m mypy "${SUBMISSION_PATHS[@]}"
        fi
        run_step "pytest (submission)" \
            "${PYTHON}" -m pytest -q tests/test_submission_export.py
    else
        run_step "ruff"          "${PYTHON}" -m ruff check src tests
        run_step "black --check" "${PYTHON}" -m black --check src tests
        if [[ "${FAST}" -eq 0 ]]; then
            run_step "mypy" "${PYTHON}" -m mypy
        fi
        run_step "pytest" "${PYTHON}" -m pytest -q
    fi
fi

run_step "export_submission" \
    "${PYTHON}" -m src.scripts.export_submission --quiet

run_step "validate_submission" \
    "${PYTHON}" -m src.scripts.validate_submission --quiet

echo
if [[ "${#FAILURES[@]}" -eq 0 ]]; then
    green "All checks passed."
    exit 0
else
    red "Failed steps: ${FAILURES[*]}"
    exit 1
fi
