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
