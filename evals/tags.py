"""Canonical decision-tag vocabulary (evals §4.2 + the §13 coverage join key).

``tag_vocabulary.yml`` is the single registry that (a) the decision-tag contract
checks code against, and (b) ``coverage.yml`` joins guardrail controls to eval
cases on. A tag emitted anywhere that is not listed here is a drift failure.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

VOCAB_PATH = Path(__file__).resolve().parent / "tag_vocabulary.yml"


@lru_cache(maxsize=1)
def _vocab() -> dict:
    return yaml.safe_load(VOCAB_PATH.read_text(encoding="utf-8")) or {}


def known_tags() -> set[str]:
    """The full set of canonical ``namespace:name`` tags."""
    out: set[str] = set()
    for namespace, names in (_vocab().get("tags") or {}).items():
        for name in names or []:
            out.add(f"{namespace}:{name}")
    return out


def namespaces() -> set[str]:
    return set((_vocab().get("tags") or {}).keys())


def is_known(tag: str) -> bool:
    return tag in known_tags()


def unknown_tags(tags: list[str] | set[str]) -> set[str]:
    """Tags not present in the vocabulary — the decision-tag contract failure set."""
    return {t for t in tags if not is_known(t)}


def guardrail_tags() -> set[str]:
    """The ``guardrail:*`` subset — what §13 coverage is defined over."""
    return {t for t in known_tags() if t.startswith("guardrail:")}
