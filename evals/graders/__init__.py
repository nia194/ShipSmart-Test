"""Graders map (Case, Response) -> Verdict.

- rule_based: deterministic, keyless — runs in every lane (the CI grade).
- semantic:   label-based recall/precision + embedding relevance (nightly, keys).
- llm_judge:  faithfulness / answer-relevance / quality rubrics (nightly/release, keys).

A case is graded by rule_based always; semantic/judge only apply when the case
declares the relevant expectation (relevant_doc_ids / judge_rubric) AND the lane
is nightly/release AND a real provider is configured. F0 smoke cases declare
neither, so all three lanes run keyless.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Verdict:
    passed: bool
    grader: str
    reason: str = ""
    score: float | None = None
    tags_seen: list[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        return "pass" if self.passed else "fail"


__all__ = ["Verdict"]
