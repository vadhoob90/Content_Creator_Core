"""Persist diagnostic events and pre-run invocation summaries fail-safely."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from ..storage import RunStore
from .models import DiagnosticEvent


def invocation_directory(root: Path, invocation_id: Optional[str]) -> Path:
    """Return the workspace-local directory for a diagnostic invocation."""
    return root / ".content-creator" / "invocations" / (invocation_id or "unknown")


def append_event(
    store: RunStore,
    *,
    enabled: bool,
    run_id: Optional[str],
    invocation_dir: Path,
    event: DiagnosticEvent,
) -> None:
    """Append one event without allowing diagnostics to fail a content run."""
    if not enabled:
        return
    try:
        path = (
            store.run_dir(run_id) / "diagnostics.jsonl"
            if run_id
            else invocation_dir / "diagnostics.jsonl"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(str(path), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            os.write(descriptor, (event.model_dump_json() + "\n").encode("utf-8"))
        finally:
            os.close(descriptor)
    except OSError:
        return


def write_invocation_summary(
    root: Path,
    invocation_id: Optional[str],
    exc: Exception,
    classification: Dict[str, Any],
    safe_detail: str,
) -> Path:
    """Write the failure summary used when run creation never completed."""
    summary = invocation_directory(root, invocation_id) / "diagnostic-summary.json"
    try:
        RunStore._atomic_text(
            summary,
            json.dumps(
                {
                    "schema_version": "1.0",
                    "invocation_id": invocation_id,
                    "status": "failed_before_run",
                    "error_type": exc.__class__.__name__,
                    "safe_detail": safe_detail,
                    **classification,
                },
                indent=2,
            ),
        )
        RunStore._atomic_text(
            root / ".content-creator" / "latest-invocation.json",
            json.dumps(
                {
                    "invocation_id": invocation_id,
                    "diagnostic_summary": str(summary.relative_to(root)),
                },
                indent=2,
            ),
        )
    except OSError:
        pass
    return summary
