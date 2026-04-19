"""Export the four Round-2 test-upload variants in one shot.

Per the post-batch-E test plan: rather than only uploading the final
``round2_promoted`` bundle, we also upload three ablation / sanity
variants so the IMC test sandbox actually validates our analytical
claims (wide_w113 > L1 ASH, kill switches don't help, simulator
behaves consistently with R1). All bundles use ``bid=0`` because the
MAF auction is ignored during testing.

The four variants:

1. **round2_promoted** — actual upload candidate (v5_micro PEPPER +
   wide_w113 ASH, kills disabled). Shipped 3× to estimate the noise
   floor from the 80 % randomized quote subsample.
2. **round2_L1_ash** — same PEPPER, L1 ASH ladder (R1 winner) instead
   of wide_w113. Tests the batch-D1 sweep claim.
3. **round2_killswitches_on** — same configuration as `round2_promoted`
   but with the batch-B kill thresholds active. Tests the batch-D2
   "kills are redundant on this stack" finding.
4. **round1_v5micro_l1** — the R1 winning bundle, unchanged. Anchors
   the simulator-consistency baseline.

Each bundle:
- Uses the shared ``build_bundle`` machinery in
  ``src/scripts/round_1/_pepper_deep_bundle.py``.
- Passes ``redact_params=True`` so the upload banner does not
  publish strategy-parameter dicts (matches the production export).
- Is AST-compressed to strip docstrings + comments.
- Validates against the standard Round-2 size budgets (96 KiB soft,
  120 KiB hard).

Outputs land under ``outputs/submissions/round_2/test_variants/``
with a ``MANIFEST.md`` that records SHA256 + size per file.

Usage::

    PYTHONPATH=. .venv/bin/python -m src.scripts.round_2.export_test_variants
"""

from __future__ import annotations

import argparse
import hashlib
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable

from src.core.config import (
    EngineConfig,
    round1_combined_v5micro_l1_engine_config,
    round2_v5micro_wide113_engine_config,
)
from src.scripts.round_1._pepper_deep_bundle import (
    PepperBundleSpec,
    PepperInline,
    build_bundle,
)
from src.scripts.round_2.export_round2_submission import (
    _ast_compress,
    _wrap_factory_call_with_bid,
)
from src.scripts.validate_submission import validate_source
from src.strategies.pepper_core_long import V5_MICRO_PARAMS, CoreLongParams

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "submissions" / "round_2" / "test_variants"


# --------------------------------------------------------------- ASH presets

_WIDE_W113_ASH: dict[str, object] = {
    "edges": (3.0, 5.0, 8.0),
    "size_mults": (1.0, 2.0, 3.0),
    "weights": (1, 1, 3),
    "skew_coef": 1.0,
    "flatten_threshold": 0.7,
}

_L1_ASH: dict[str, object] = {
    "edges": (2.5, 3.5, 5.0),
    "size_mults": (1.0, 1.5, 2.0),
    "weights": (3, 1, 1),
    "skew_coef": 2.0,
    "flatten_threshold": 0.7,
}


# --------------------------------------------------------------- PEPPER presets

# Batch-B kill-switch thresholds (defended by the D2 sweep on
# adverse tapes). Disabled in the promoted bundle; enabled in the
# `round2_killswitches_on` ablation.
_BATCH_B_KILLS: CoreLongParams = replace(
    V5_MICRO_PARAMS,
    kill_slope_window=50,
    kill_consecutive_neg_slope_n=20,
    kill_slope_pause_snaps=50,
    kill_residual_threshold=35.0,
    kill_residual_release=15.0,
    kill_step_move_threshold=40.0,
    kill_step_move_pause_snaps=10,
    kill_intraday_pnl_threshold=2_500.0,
)


# --------------------------------------------------------------- variant specs


@dataclass(frozen=True)
class TestVariantSpec:
    label: str
    purpose: str
    factory_name: str
    factory: Callable[[], EngineConfig]
    ash_params_dict: dict[str, object]
    pepper_params: CoreLongParams

    def to_pepper_bundle_spec(self) -> PepperBundleSpec:
        return PepperBundleSpec(
            variant=self.label,
            factory_name=self.factory_name,
            factory=self.factory,
            label=f"Round-2 test variant: {self.label}",
            purpose=self.purpose,
            ash_inline=PepperInline(
                strategy_module_path="src/strategies/ash_ladder.py",
                strategy_class_name="AshLadderStrategy",
                params_class_name="LadderParams",
                new_strategy_name="ash_ladder",
                params_dict=self.ash_params_dict,
            ),
            pepper_inline=PepperInline(
                strategy_module_path="src/strategies/pepper_core_long.py",
                strategy_class_name="PepperCoreLongStrategy",
                params_class_name="CoreLongParams",
                new_strategy_name="pepper_core_long",
                params_dict=asdict(self.pepper_params),
            ),
        )


VARIANTS: tuple[TestVariantSpec, ...] = (
    TestVariantSpec(
        label="round2_promoted",
        purpose=(
            "Actual upload candidate. v5_micro PEPPER + wide_w113 ASH, "
            "kill switches DISABLED. Upload 3x to estimate noise floor "
            "from the 80% randomized quote subsample."
        ),
        factory_name="round2_v5micro_wide113_engine_config",
        factory=round2_v5micro_wide113_engine_config,
        ash_params_dict=_WIDE_W113_ASH,
        pepper_params=V5_MICRO_PARAMS,
    ),
    TestVariantSpec(
        label="round2_L1_ash",
        purpose=(
            "Ablation: PEPPER unchanged, ASH = L1 ladder (R1 winner). "
            "Tests batch-D1 claim that wide_w113 > L1 on R2. If this "
            "scores >= round2_promoted average, wide_w113 is not real."
        ),
        factory_name="round2_v5micro_wide113_engine_config",
        factory=round2_v5micro_wide113_engine_config,
        ash_params_dict=_L1_ASH,
        pepper_params=V5_MICRO_PARAMS,
    ),
    TestVariantSpec(
        label="round2_killswitches_on",
        purpose=(
            "Ablation: same as round2_promoted but with batch-B kill "
            "thresholds active. Tests batch-D2 claim that kill switches "
            "are redundant with v5_micro's existing guard. If this scores "
            ">= round2_promoted, kills DO help on the official sim."
        ),
        factory_name="round2_v5micro_wide113_engine_config",
        factory=round2_v5micro_wide113_engine_config,
        ash_params_dict=_WIDE_W113_ASH,
        pepper_params=_BATCH_B_KILLS,
    ),
    TestVariantSpec(
        label="round1_v5micro_l1",
        purpose=(
            "R1 winning bundle, unchanged. Simulator-consistency anchor: "
            "if this scores ~ R1 final scaled to 100k ticks (~+9k), the "
            "R2 simulator behaves like R1's. Materially different = R2 "
            "tape microstructure changed."
        ),
        factory_name="round1_combined_v5micro_l1_engine_config",
        factory=round1_combined_v5micro_l1_engine_config,
        ash_params_dict=_L1_ASH,
        pepper_params=V5_MICRO_PARAMS,
    ),
)


# --------------------------------------------------------------- export


def export_variant_to_path(spec: TestVariantSpec, *, out_dir: Path) -> Path:
    """Build a single test variant bundle and write it to ``out_dir``.

    Mirrors ``export_round2_submission.export_variant_to_path`` but
    accepts an arbitrary ``TestVariantSpec`` (different ASH/PEPPER
    inlines per variant). Always exports with ``bid=0`` — the MAF
    auction is ignored during testing.
    """
    bundle_spec = spec.to_pepper_bundle_spec()
    source, _ = build_bundle(bundle_spec, redact_params=True)
    source = _wrap_factory_call_with_bid(source, spec.factory_name, 0)
    compressed = _ast_compress(source)

    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"trader_{spec.label}.py"
    output_path.write_text(compressed, encoding="utf-8")
    return output_path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


@dataclass(frozen=True)
class ExportResult:
    spec: TestVariantSpec
    path: Path
    size_bytes: int
    sha256: str
    validator_ok: bool
    validator_summary: str


def _validate(path: Path) -> tuple[bool, str]:
    report = validate_source(path.read_text(encoding="utf-8"))
    summary = (
        f"{len(report.errors)} error(s), {len(report.warnings)} warning(s), "
        f"size {report.size_bytes} bytes"
    )
    return report.ok, summary


# --------------------------------------------------------------- manifest


def _render_manifest(results: list[ExportResult]) -> str:
    lines = [
        "# Round-2 test-upload variants — manifest",
        "",
        "Built by `src/scripts/round_2/export_test_variants.py`. All bundles",
        "use `bid=0` (MAF auction is ignored during testing). Upload these",
        "to the IMC sandbox per the test plan and record results in",
        "`outputs/round_2/test_uploads/log.md`.",
        "",
        "## Bundles",
        "",
        "| variant | size (bytes) | validator | SHA256 | purpose |",
        "|---|---:|---|---|---|",
    ]
    for r in results:
        validator_cell = "✅ OK" if r.validator_ok else "❌ FAIL"
        lines.append(
            f"| `{r.spec.label}` | {r.size_bytes} | {validator_cell} "
            f"({r.validator_summary}) | `{r.sha256}` | {r.spec.purpose} |"
        )
    lines.append("")
    lines.append("## Reproduce")
    lines.append("")
    lines.append("```bash")
    lines.append(
        "PYTHONPATH=. .venv/bin/python -m src.scripts.round_2.export_test_variants"
    )
    lines.append("shasum -a 256 outputs/submissions/round_2/test_variants/*.py")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)
    out_dir: Path = args.out_dir

    results: list[ExportResult] = []
    for spec in VARIANTS:
        path = export_variant_to_path(spec, out_dir=out_dir)
        size = path.stat().st_size
        sha = _sha256(path)
        ok, summary = _validate(path)
        results.append(ExportResult(spec, path, size, sha, ok, summary))
        try:
            rel = path.relative_to(REPO_ROOT)
        except ValueError:
            rel = path
        marker = "✅" if ok else "❌"
        print(
            f"{marker} {spec.label:<28s} → {rel} ({size} B, sha256={sha[:12]}…)"
        )

    manifest_path = out_dir / "MANIFEST.md"
    manifest_path.write_text(_render_manifest(results))
    print(f"[wrote] {manifest_path.relative_to(REPO_ROOT)}")

    if any(not r.validator_ok for r in results):
        print("[ERROR] one or more variants failed validation")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
