"""Persist diagnostic events and pre-run invocation summaries fail-safely."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from ..storage import RunStore
from .models import DiagnosticEvent

logger = logging.getLogger(__name__)


def invocation_directory(root: Path, invocation_id: Optional[str]) -> Path:
    """Return the workspace-local directory for a diagnostic invocation.

    Args:
        root (Path): The workspace root directory.
        invocation_id (Optional[str]): The stable identifier for the invocation.

    Returns:
        Path: The resolved filesystem path for invocation directory.
    """
    return root / ".content-creator" / "invocations" / (invocation_id or "unknown")


def append_event(
    store: RunStore,
    *,
    enabled: bool,
    run_id: Optional[str],
    invocation_dir: Path,
    event: DiagnosticEvent,
) -> None:
    """Append one event without allowing diagnostics to fail a content run.

    Args:
        store (RunStore): The persistence service used to load and save state.
        enabled (bool): Whether enabled behavior is enabled.
        run_id (Optional[str]): The stable identifier for the content run.
        invocation_dir (Path): The filesystem path containing the invocation dir.
        event (DiagnosticEvent): The diagnostic or lifecycle event to record.

    Returns:
        None: The callable updates append event state and returns no value.
    """
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
    except OSError as exc:
        logger.warning("Unable to persist diagnostic event (%s)", exc.__class__.__name__)


def write_invocation_summary(
    root: Path,
    invocation_id: Optional[str],
    exc: Exception,
    classification: Dict[str, Any],
    safe_detail: str,
) -> Optional[Path]:
    """Write the failure summary used when run creation never completed.

    Persist the summary before updating the latest-invocation pointer so callers only
    receive a path to an artifact that was actually written. Pointer failures remain
    observable without replacing the original application exception.

    Args:
        root (Path): The workspace root directory.
        invocation_id (Optional[str]): The stable identifier for the invocation.
        exc (Exception): The exception raised by the failed operation.
        classification (Dict[str, Any]): The classification collection consumed while
            write invocation summary.
        safe_detail (str): The safe detail text processed when write invocation summary.

    Returns:
        Optional[Path]: The persisted diagnostic summary path, or ``None`` when the
            summary could not be written.
    """
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
    except OSError as exc:
        logger.warning(
            "Unable to persist invocation diagnostic summary (%s)",
            exc.__class__.__name__,
        )
        return None
    try:
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
    except OSError as exc:
        logger.warning(
            "Persisted the invocation summary but not its latest pointer (%s)",
            exc.__class__.__name__,
        )
    return summary
