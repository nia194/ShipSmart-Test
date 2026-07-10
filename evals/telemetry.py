"""Optional eval-telemetry sink (evals §11).

When ``EVAL_TELEMETRY_SINK`` is set to an HTTP(S) URL, every lane record is
POSTed there as JSON so an external dashboard/alerting stack can consume the
same record that lands in history.jsonl. Strictly best-effort and off by
default: unset env → no-op, transport failure → one printed warning, never a
failed lane. CI stays keyless and network-free.
"""

from __future__ import annotations

import json
import os
import urllib.request
from collections.abc import Callable

ENV_VAR = "EVAL_TELEMETRY_SINK"

Transport = Callable[[str, bytes], None]


def _http_post(url: str, payload: bytes) -> None:  # pragma: no cover - live network
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=5):
        pass


def emit(record: dict, *, url: str | None = None, transport: Transport | None = None) -> bool:
    """POST a lane record to the configured sink. True only on a delivered emit."""
    target = url if url is not None else os.environ.get(ENV_VAR, "")
    if not target:
        return False
    try:
        (transport or _http_post)(target, json.dumps(record, sort_keys=True).encode())
        return True
    except Exception as e:  # noqa: BLE001 - telemetry must never fail a lane
        print(f"eval-telemetry: emit to {target} failed ({e}) — continuing")
        return False
