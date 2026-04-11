# Phase 9 — Submission Packaging Checklist

This is the short, action-oriented checklist for turning the live
engine into a Prosperity submission. It is intentionally mechanical.
Anything that requires judgment lives in the phase notes, not here.

Phase 9 builds the *machinery* for packaging. It does **not** finalize
the submission content. Estimator choices, strategy names, config
values, and module inventory are all still in flux in the earlier
phases. The exporter is built to be flexible so changes there do not
require changes here.

---

## Pre-submit checklist

Run top-to-bottom before every upload.

- [ ] Working tree is clean (`git status`) — no stray edits in the live
      path that are not in a commit.
- [ ] All earlier phase gates are green (unit tests, backtest review,
      parameter sweep) — see the phase notes in `docs/`.
- [ ] `./scripts/check.sh` passes end-to-end.
- [ ] The bundled file at `outputs/submissions/trader_submission.py`
      was regenerated in this session, not left over from a previous
      run. The checker script regenerates it automatically; if you
      export manually, do it again after your last edit.
- [ ] You have read the top banner of the bundled file and confirmed
      `Datamodel mode: platform` and `Source modules:` matches what
      you expect.
- [ ] The dry-run smoke tests passed (they run as part of `pytest`).
- [ ] The bundled file is under the size budget in the validator
      report.
- [ ] You know which `ProductConfig` values were active at export
      time. Capture them in the commit message or the submission note.

Not part of Phase 9 (do not attempt to check these off here):

- [ ] Final estimator names / final strategy names / final config —
      these are owned by the earlier phases and are allowed to change
      between submissions.

---

## Commands

All commands assume you are in the repo root and have a working
Python environment (the scripts auto-detect `.venv/bin/python`).

### Build the bundle

```bash
# Platform-mode bundle (real submission artifact)
python -m src.scripts.export_submission

# Inline-mode bundle (self-contained, for local smoke testing)
python -m src.scripts.export_submission \
    --datamodel inline \
    --output outputs/submissions/trader_submission_inline.py
```

Default output: `outputs/submissions/trader_submission.py`.

### Validate the bundle

```bash
python -m src.scripts.validate_submission
# or, for a specific file:
python -m src.scripts.validate_submission path/to/file.py
```

Exit code is `0` on OK, `1` on FAIL.

### Dry-run smoke test

The dry run is already part of the test suite:

```bash
python -m pytest tests/test_submission_export.py -q
```

It exports the bundle into `tmp_path`, imports it in isolation with
`importlib.util.spec_from_file_location`, instantiates `Trader`, and
runs it on an empty `TradingState`.

### Full local CI gate

There are two gates in one script:

```bash
./scripts/check.sh                  # repo-wide, honest and noisy
./scripts/check.sh --submission     # submission-critical scope only
./scripts/check.sh --fast           # skip mypy (slowest step)
./scripts/check.sh --export-only    # only export + validate
```

Flags compose: `--submission --fast` runs the packaging scope without
mypy. Use `--submission` before every real upload — it is the signal
that "whatever is in the live path will bundle, validate, and run."
Use the default gate to see every pre-existing issue across the repo.

The script runs each step independently and reports every failure in
one pass, so a single broken lint doesn't mask a broken test.

**Submission-critical scope** (tracked in `SUBMISSION_PATHS` inside
`scripts/check.sh` — keep it aligned with the exporter's
`LIVE_MODULE_ORDER`):

- `src/datamodel.py`
- `src/trader.py`
- `src/core/`
- `src/strategies/`
- `src/scripts/export_submission.py`
- `src/scripts/validate_submission.py`
- `tests/test_submission_export.py`

---

## How the exporter works

Single-sentence version: it reads each live-path file as text, strips
`from __future__ import annotations` and `from src.*` imports, hoists
stdlib imports to the top of the bundle, and concatenates everything
in a hand-maintained dependency order.

Important properties:

- **Deterministic.** Two runs with the same inputs produce the same
  bundle. The tests assert this.
- **Explicit module order.** `LIVE_MODULE_ORDER` in
  `src/scripts/export_submission.py` is the only place that knows what
  the live path contains. Adding a new live module means adding one
  line here.
- **Self-checking.** Before any bundling work, the exporter walks
  every module in `LIVE_MODULE_ORDER`, parses its imports, and
  confirms every `from src.* import ...` target is either also in
  the list or is `src/datamodel.py`. If a live module imports
  something the list does not cover, the exporter raises a
  `RuntimeError` naming the missing module. This catches the #1
  long-term failure mode of a hand-maintained list: forgetting to
  register a new live module.
- **Two datamodel modes.** `platform` (the default, what Prosperity
  actually runs) emits `from datamodel import ...` and is the only
  mode suitable for real submissions. `inline` copies our local
  mirror into the bundle so the file can be imported and smoke-tested
  without any `sys.modules` monkey-patching — but the resulting
  bundle is **DEV-ONLY** and must not be uploaded. The validator
  raises a loud WARN if it sees the inline marker in the bundle
  header.
- **Refuses to "fix" broken input.** If a live module adds an import
  that violates the validator rules, the exporter bundles it
  unchanged and the validator flags it. The split means the exporter
  is simple and the validator is the single source of truth for
  what counts as "submission ready".

---

## What the validator checks

See the top docstring of `src/scripts/validate_submission.py` for the
authoritative list. In short:

**Errors (block the submission):**

- missing `class Trader` at module level
- missing `Trader.run` method
- imports in `FORBIDDEN_IMPORT_ROOTS` (network, subprocess,
  importlib, ctypes, multiprocessing, …)
- imports in `DEV_ONLY_IMPORT_ROOTS` (`src.backtest`, `src.scripts`,
  `tests`, `pytest`, `unittest`, …)
- residual `from src.*` lines (proof the exporter is broken)
- bare `open(...)` or `os.system` / `os.popen` calls
- file size above `MAX_SIZE_BYTES` (hard budget, 96 KiB)
- syntax errors

**Warnings (printed, do not block):**

- file size above `SOFT_SIZE_BYTES` (72 KiB) — operational
  early-warning as the live path grows
- `Datamodel mode: inline` marker in the bundle header —
  dev-only artifact, must not be uploaded
- `Trader.run` has no literal 3-tuple return (static check;
  the dry-run smoke test is the strict one)
- `print(...)` calls (likely debug artifacts — use `logging`)
- `.read_text` / `.write_text` / `.write_bytes` method calls
  (may be false positives)

The validator report header always shows the current size alongside
both thresholds and the percentage used, so size pressure is visible
on every run even when there is no WARN or ERROR.

---

## When things go wrong

| Symptom                                           | Likely cause                                                                            | Fix                                                                            |
| ------------------------------------------------- | --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Exporter raises `FileNotFoundError`                | A module listed in `LIVE_MODULE_ORDER` was renamed or deleted                            | Update the list or revert the rename                                           |
| Validator: `residual_src_import`                   | A live module imports `from src.something` that the exporter did not recognise          | Check the import is top-level and uses `from src.x import y` shape             |
| Validator: `forbidden_import`                      | A live module pulled in a networking / subprocess / importlib dependency                | Move that code into `src/backtest/` or `src/scripts/` where it is allowed      |
| Dry-run smoke test fails at `dataclass` decorator   | Test loader forgot to register the module in `sys.modules` before `exec_module`         | The helper in `tests/test_submission_export.py` already does this — do not remove it |
| Bundled file is `> MAX_SIZE_BYTES`                  | Real growth (too much code in the live path) OR a stray large blob committed             | Move non-essential code out of the live path; do not raise the budget casually |

---

## What Phase 9 does not decide

- Which estimator wins for each product.
- Which strategy name maps to which product.
- Which config values to ship.
- Whether a bundled file is "the final" submission.

Those decisions live in later phases. This checklist only exists to
make "turning whatever is in the live path today into an uploadable
file" a zero-judgment operation.
