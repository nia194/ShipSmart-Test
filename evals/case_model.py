"""The one JSONL case schema every layer reuses (evals guide §3.1).

Only ``expected`` varies by layer. ``relevant_doc_ids`` makes RAG context
precision/recall computable without a judge; ``tags`` carrying ``guardrail:*``
is what the §13 coverage check joins on.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

SPLITS = {"dev", "holdout"}
SEVERITIES = {"critical", "major", "minor"}
PROVENANCES = {"authored", "online_promoted", "incident"}


@dataclass(frozen=True)
class Expected:
    behavior: str  # grounded_answer | refusal | clarify | tool_call | ...
    must_cite_any: list[str] = field(default_factory=list)
    relevant_doc_ids: list[str] = field(default_factory=list)  # ground truth for precision/recall
    forbidden: list[str] = field(default_factory=list)
    # Layer-3 agent/tool-use assertions (evals §6.1): which tools MUST be called,
    # which must NOT (a forbidden tool executing fails loudly), which decision
    # tags must/mustn't appear, and the step-count ceiling.
    required_tools: list[str] = field(default_factory=list)
    forbidden_tools: list[str] = field(default_factory=list)
    required_tags: list[str] = field(default_factory=list)
    forbidden_tags: list[str] = field(default_factory=list)
    max_steps: int | None = None
    judge_rubric: str | None = None  # nightly/release only


@dataclass(frozen=True)
class Case:
    id: str
    layer: int  # 1..6
    suite: str  # e.g. "rag/policy", "safety/redteam"
    dataset_version: str
    split: str  # dev | holdout
    provenance: str
    added_in: str
    flaky: bool
    runs: int  # runs>1 in model lanes
    input: dict
    expected: Expected
    severity: str
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.split not in SPLITS:
            raise ValueError(f"{self.id}: split {self.split!r} not in {sorted(SPLITS)}")
        if self.severity not in SEVERITIES:
            raise ValueError(f"{self.id}: severity {self.severity!r} not in {sorted(SEVERITIES)}")
        if self.provenance not in PROVENANCES:
            raise ValueError(
                f"{self.id}: provenance {self.provenance!r} not in {sorted(PROVENANCES)}"
            )
        if not (1 <= self.layer <= 6):
            raise ValueError(f"{self.id}: layer {self.layer} out of range 1..6")

    @property
    def is_safety_critical(self) -> bool:
        """Safety-critical cases run pass-all-of-N; quality cases majority-of-N."""
        return self.severity == "critical"


def _case_from_obj(obj: dict) -> Case:
    exp = obj.get("expected", {})
    return Case(
        id=obj["id"],
        layer=int(obj["layer"]),
        suite=obj["suite"],
        dataset_version=obj["dataset_version"],
        split=obj.get("split", "dev"),
        provenance=obj.get("provenance", "authored"),
        added_in=obj.get("added_in", "v1.0"),
        flaky=bool(obj.get("flaky", False)),
        runs=int(obj.get("runs", 1)),
        input=obj.get("input", {}),
        expected=Expected(
            behavior=exp["behavior"],
            must_cite_any=list(exp.get("must_cite_any", [])),
            relevant_doc_ids=list(exp.get("relevant_doc_ids", [])),
            forbidden=list(exp.get("forbidden", [])),
            required_tools=list(exp.get("required_tools", [])),
            forbidden_tools=list(exp.get("forbidden_tools", [])),
            required_tags=list(exp.get("required_tags", [])),
            forbidden_tags=list(exp.get("forbidden_tags", [])),
            max_steps=exp.get("max_steps"),
            judge_rubric=exp.get("judge_rubric"),
        ),
        severity=obj.get("severity", "major"),
        tags=list(obj.get("tags", [])),
    )


def load_jsonl(path: str | Path) -> list[Case]:
    """Parse a ``*.vN.jsonl`` dataset file into validated Cases (one per line)."""
    p = Path(path)
    cases: list[Case] = []
    seen: set[str] = set()
    for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:  # noqa: PERF203
            raise ValueError(f"{p}:{lineno}: invalid JSON: {e}") from e
        case = _case_from_obj(obj)
        if case.id in seen:
            raise ValueError(f"{p}:{lineno}: duplicate case id {case.id!r}")
        seen.add(case.id)
        cases.append(case)
    return cases
