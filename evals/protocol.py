"""The system-under-test seam.

A ``SystemUnderTest`` maps a Case to a Response. F0 ships a deterministic,
keyless ``EchoSUT`` so the harness runs end-to-end with no services; later
phases plug in real SUTs (live API over httpx, scripted-provider agent, Web
unit lane) per layer — the runner/grader code does not change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .case_model import Case


@dataclass
class Response:
    text: str = ""
    refused: bool = False
    sources: list[str] = field(default_factory=list)  # cited source ids/filenames
    retrieved_doc_ids: list[str] = field(default_factory=list)  # for context precision/recall
    decisions: list[str] = field(default_factory=list)  # emitted tags
    tool_calls: list[str] = field(default_factory=list)
    steps: int = 0  # agent loop step count (for the §6.1 max_steps assertion)
    latency_ms: float = 0.0
    tokens: int = 0
    cost_usd: float = 0.0
    provider: str | None = None
    model: str | None = None


class SystemUnderTest(Protocol):
    def __call__(self, case: Case) -> Response: ...


class EchoSUT:
    """Deterministic, keyless SUT for the foundation smoke suite.

    It fabricates a Response that satisfies the case's own ``expected`` so the
    pipeline (load -> run -> grade -> gate -> trace -> history) is exercised
    with zero external dependencies. It is NOT a product test — real SUTs
    replace it per layer.
    """

    provider = "echo"
    model = "echo"

    def __call__(self, case: Case) -> Response:
        exp = case.expected
        refused = exp.behavior == "refusal"
        text = "SAFE_REFUSAL" if refused else f"echo:{case.input.get('query', case.id)}"
        # Echo the case's own tool/tag assertions so the harness exercises the §6.1
        # grading path deterministically (a real scripted-agent SUT replaces this).
        tool_calls = [] if refused else list(exp.required_tools)
        return Response(
            text=text,
            refused=refused,
            sources=list(exp.must_cite_any[:1]),
            retrieved_doc_ids=list(exp.relevant_doc_ids),
            decisions=list(case.tags) + list(exp.required_tags),
            tool_calls=tool_calls,
            steps=len(tool_calls),
            provider=self.provider,
            model=self.model,
        )
