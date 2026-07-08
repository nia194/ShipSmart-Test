"""Dataset manifest (evals guide §3.2) — runners load through this, not filenames.

``datasets/MANIFEST.yml`` maps each suite -> active version -> file -> sha256 ->
case count -> last-reviewed date. Bumping a dataset is a reviewed diff, not a
silent append; reports record the versions they ran.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

DATASETS_DIR = Path(__file__).resolve().parent / "datasets"
MANIFEST_PATH = DATASETS_DIR / "MANIFEST.yml"


@dataclass(frozen=True)
class SuiteEntry:
    suite: str
    layer: int
    active_version: str
    file: str
    sha256: str
    case_count: int
    last_reviewed: str

    @property
    def path(self) -> Path:
        return DATASETS_DIR / self.file


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(path: str | Path = MANIFEST_PATH) -> list[SuiteEntry]:
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    entries: list[SuiteEntry] = []
    for suite, meta in (doc.get("suites") or {}).items():
        entries.append(
            SuiteEntry(
                suite=suite,
                layer=int(meta["layer"]),
                active_version=meta["active_version"],
                file=meta["file"],
                sha256=meta.get("sha256", ""),
                case_count=int(meta.get("case_count", 0)),
                last_reviewed=str(meta.get("last_reviewed", "")),
            )
        )
    return entries


def verify(entry: SuiteEntry) -> None:
    """Fail loudly if the dataset file is missing or its content drifted."""
    if not entry.path.exists():
        raise FileNotFoundError(f"{entry.suite}: dataset file missing: {entry.path}")
    if entry.sha256:
        actual = _sha256(entry.path)
        if actual != entry.sha256:
            raise ValueError(
                f"{entry.suite}: sha256 drift — manifest {entry.sha256[:12]}… "
                f"!= file {actual[:12]}… (bump the dataset version via a reviewed diff)"
            )


def compute_sha256(file: str) -> str:
    """Helper for authoring: the sha256 to record in the manifest for a file."""
    return _sha256(DATASETS_DIR / file)
