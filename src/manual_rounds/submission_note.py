"""Structured submission-note builder.

Every manual-round answer must pass the validation protocol in
``Tutorial/Manual Strategy Plan.md``: chosen answer, core assumptions,
backup answer, biggest risk. This module renders that checklist into
a markdown note that can be pasted into the team's notes folder or the
submission confirmation dialog.

Deliberately small and side-effect-free: the note is returned as a
string. Callers decide where to write it (usually
``outputs/notes/round_N_manual.md``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SubmissionNote:
    round_name: str
    family: str
    chosen_answer: str
    payoff_explanation: str
    core_assumptions: Sequence[str] = field(default_factory=tuple)
    naive_baseline: str = ""
    crowd_adjusted: str = ""
    robustness_range: str = ""
    backup_answer: str = ""
    failure_mode: str = ""
    top_alternatives: Sequence[str] = field(default_factory=tuple)

    def render(self) -> str:
        def bullets(items: Sequence[str]) -> str:
            if not items:
                return "_n/a_"
            return "\n".join(f"- {item}" for item in items)

        lines: list[str] = [
            f"# {self.round_name} — manual submission note",
            "",
            f"**Problem family:** {self.family}",
            "",
            "## Chosen answer",
            self.chosen_answer,
            "",
            "## Payoff structure",
            self.payoff_explanation,
            "",
            "## Naive (no-opponent) baseline",
            self.naive_baseline or "_n/a_",
            "",
            "## Crowd / opponent-adjusted answer",
            self.crowd_adjusted or "_n/a_",
            "",
            "## Core assumptions",
            bullets(self.core_assumptions),
            "",
            "## Robustness range",
            self.robustness_range or "_n/a_",
            "",
            "## Backup answer if assumptions fail",
            self.backup_answer or "_n/a_",
            "",
            "## Biggest failure mode",
            self.failure_mode or "_n/a_",
            "",
            "## Top alternatives considered",
            bullets(self.top_alternatives),
        ]
        return "\n".join(lines) + "\n"
