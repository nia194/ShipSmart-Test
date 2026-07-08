"""
Helpers for the cross-repo CONTRACT tests.

The five ShipSmart services each have a top-level ``app`` package, so they cannot
all be imported into one process. Contract tests therefore parse the sibling
source files as TEXT and assert the shapes line up — catching drift between, say,
ShipSmart-API's response models and ShipSmart-Web's TypeScript types without
running anything.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # the directory holding all repos
WEB = ROOT / "ShipSmart-Web"
API = ROOT / "ShipSmart-API"
MCP = ROOT / "ShipSmart-MCP"
JAVA = ROOT / "ShipSmart-Orchestrator"
INFRA = ROOT / "ShipSmart-Infra"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def ts_interface_fields(src: str, name: str) -> set[str]:
    """Field names of a TS ``export interface Name { ... }``."""
    m = re.search(rf"export interface {name}\s*\{{(.*?)\n\}}", src, re.S)
    assert m, f"TS interface {name} not found"
    return set(re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\??\s*:", m.group(1), re.M))


def py_model_fields(src: str, name: str) -> set[str]:
    """Top-level field names of a pydantic ``class Name(BaseModel):`` block."""
    m = re.search(rf"class {name}\(BaseModel\):(.*?)(?:\nclass |\Z)", src, re.S)
    assert m, f"pydantic model {name} not found"
    # Indented `field: annotation` lines, skipping decorators/docstrings.
    return set(re.findall(r"^\s{4}([a-z_][A-Za-z0-9_]*)\s*:", m.group(1), re.M))


def py_class_fields(src: str, name: str) -> set[str]:
    """Top-level field names of any ``class Name(<base>):`` block.

    Like :func:`py_model_fields` but base-class-agnostic — needed for models that
    subclass a shared base (e.g. ShipSmart-API's frozen domain models extend a
    private ``_Frozen(BaseModel)``, so the ``(BaseModel)`` matcher misses them).
    """
    m = re.search(rf"class {name}\([^)]*\):(.*?)(?:\nclass |\Z)", src, re.S)
    assert m, f"python class {name} not found"
    return set(re.findall(r"^\s{4}([a-z_][A-Za-z0-9_]*)\s*:", m.group(1), re.M))


def java_record_components(src: str, name: str) -> set[str]:
    """Component names of a Java ``record Name( Type a, Type b, ... )``."""
    m = re.search(rf"record {name}\((.*?)\)\s*\{{", src, re.S)
    assert m, f"java record {name} not found"
    out: set[str] = set()
    for comp in m.group(1).split(","):
        toks = comp.replace("\n", " ").split()
        if toks:
            out.add(toks[-1])  # last token is the component name
    return out


def json_schema_required(py_src: str, tool_class: str) -> tuple[set[str], set[str]]:
    """Extract (required, property names) from a MCP tool's ``input_schema()``.

    Parses the dict literal inside the named tool class — good enough since the
    schema is a static literal.
    """
    cls = re.search(rf"class {tool_class}\(Tool\):(.*?)(?:\nclass |\Z)", py_src, re.S)
    assert cls, f"tool class {tool_class} not found"
    body = cls.group(1)
    req_block = re.search(r'"required":\s*\[(.*?)\]', body, re.S)
    required = set(re.findall(r'"([a-z_]+)"', req_block.group(1))) if req_block else set()
    props_block = re.search(r'"properties":\s*\{(.*)\n\s*\},', body, re.S)
    props = (
        set(re.findall(r'\n\s{16}"([a-z_]+)":\s*\{', props_block.group(1)))
        if props_block
        else set()
    )
    return required, props


# ── ShipSmart-API decision tags + settings flags (evals §4.2 contract) ─────────

_TAG_NAMESPACES = ("agent", "concierge", "compliance", "workflow", "guardrail", "budget")
# Base must start with [a-z_] (a real tag segment), which excludes log/prose
# strings like "concierge: dispatch degraded ..." (space after the colon).
_TAG_LITERAL = re.compile(r"""["'](""" + "|".join(_TAG_NAMESPACES) + r"""):([a-z_][^"']*)["']""")


def api_decision_tags() -> set[str]:
    """Emitted decision-tag prefixes (``namespace:base``) across ShipSmart-API source.

    Scans every ``app/**/*.py`` for tag-shaped string literals in the known
    namespaces and returns the ``namespace:base`` prefix — the dynamic detail tail
    (e.g. ``agent:retrieve:{n}`` -> ``agent:retrieve``) is dropped. A fully dynamic
    base (segment is a ``{var}``) yields ``namespace:*``.
    """
    out: set[str] = set()
    for path in sorted((API / "app").rglob("*.py")):
        for ns, rest in _TAG_LITERAL.findall(read(path)):
            base = re.split(r"[:{]", rest, maxsplit=1)[0]
            out.add(f"{ns}:{base}" if base else f"{ns}:*")
    return out


def api_settings_flags() -> set[str]:
    """The ``*_enabled`` feature flags declared on ShipSmart-API's Settings."""
    src = read(API / "app" / "core" / "config.py")
    return set(re.findall(r"^\s{4}([a-z_]+_enabled)\s*:\s*bool", src, re.M))


def env_example_vars(repo: Path) -> set[str]:
    """UPPER_SNAKE var names assigned in a repo's ``.env.example``."""
    return set(re.findall(r"^([A-Z][A-Z0-9_]*)=", read(repo / ".env.example"), re.M))


def api_test_blob() -> str:
    """Concatenated ShipSmart-API test source — for 'is this flag gated somewhere' checks."""
    return "\n".join(read(p) for p in sorted((API / "tests").rglob("*.py")))


def api_tool_policy_names() -> set[str]:
    """Tool names the ShipSmart-API tool-policy registry (DEFAULT_TOOL_POLICIES) governs."""
    src = read(API / "app" / "security" / "tool_policy.py")
    m = re.search(r"DEFAULT_TOOL_POLICIES.*?=\s*\{(.*?)\n\}", src, re.S)
    assert m, "DEFAULT_TOOL_POLICIES not found in ShipSmart-API tool_policy.py"
    return set(re.findall(r'"([a-z_]+)":\s*ToolCallPolicy', m.group(1)))


def mcp_tool_names() -> set[str]:
    """Tool names ShipSmart-MCP actually serves (its READ_ONLY_TOOL_ALLOWLIST)."""
    src = read(MCP / "app" / "main.py")
    m = re.search(r"READ_ONLY_TOOL_ALLOWLIST.*?\{(.*?)\}", src, re.S)
    assert m, "READ_ONLY_TOOL_ALLOWLIST not found in ShipSmart-MCP main.py"
    return set(re.findall(r'"([a-z_]+)"', m.group(1)))
