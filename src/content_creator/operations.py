"""Privacy-safe operational failure classification and recovery evidence."""

from __future__ import annotations

import json
import os
import re
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

from .storage import RunStore
from .version import VERSION
from .versioned_artifacts import hash_file


class FailureCode(str, Enum):
    """Represent a failure code."""

    PROVIDER_FAILURE = "provider_failure"
    CORRUPT_STATE = "corrupt_state"
    STALE_LOCK = "stale_lock"
    VALIDATION_FAILURE = "validation_failure"
    UNKNOWN = "unknown"


def classify_failure(message: Optional[str]) -> FailureCode:
    """Classify failure."""
    normalized = (message or "").lower()
    if any(term in normalized for term in ("provider", "unavailable", "api")):
        return FailureCode.PROVIDER_FAILURE
    if any(term in normalized for term in ("json", "corrupt", "decode")):
        return FailureCode.CORRUPT_STATE
    if "lock" in normalized:
        return FailureCode.STALE_LOCK
    if any(term in normalized for term in ("validation", "invalid")):
        return FailureCode.VALIDATION_FAILURE
    return FailureCode.UNKNOWN


def build_support_bundle(root: Path, run_id: str) -> Dict[str, Any]:
    """Build support bundle."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise ValueError("run_id must use letters, digits, underscores, and hyphens")
    root = root.resolve()
    run = root / "runs" / run_id
    state_path = run / "state.json"
    state: Dict[str, Any] = {}
    if state_path.is_file():
        try:
            loaded = json.loads(state_path.read_text(encoding="utf-8"))
            state = loaded if isinstance(loaded, dict) else {}
        except (OSError, json.JSONDecodeError):
            state = {"status": "corrupt", "last_error": "corrupt state JSON"}
    artifacts = {
        str(path.relative_to(run)): {
            "size": path.stat().st_size,
            "sha256": hash_file(path),
        }
        for path in sorted(run.rglob("*"))
        if path.is_file()
    }
    bundle = {
        "schema_version": "1.0",
        "core_version": VERSION,
        "run_id": run_id,
        "run_status": state.get("status", "unknown"),
        "failure": {
            "code": classify_failure(str(state.get("last_error", ""))).value,
            "recoverable": state.get("status") != "published",
        },
        "artifacts": artifacts,
        "privacy": {
            "author_content_included": False,
            "secrets_included": False,
            "artifact_contents_included": False,
        },
    }
    destination = root / ".content-creator" / "support" / "{}.json".format(run_id)
    RunStore._atomic_text(destination, json.dumps(bundle, indent=2))
    return bundle


def recovery_report(root: Path) -> Dict[str, Any]:
    """Return the recovery report."""
    root = root.resolve()
    locks = []
    active_locks = []
    for path in sorted(root.rglob(".activation.lock")):
        if not path.is_file():
            continue
        relative = str(path.relative_to(root))
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
            pid = int(metadata["pid"])
            os.kill(pid, 0)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            locks.append(relative)
        else:
            active_locks.append(relative)
    corrupt = []
    for path in sorted((root / "runs").glob("*/state.json")):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            corrupt.append(str(path.relative_to(root)))
    return {
        "status": "needs_attention" if locks or corrupt else "ok",
        "stale_activation_locks": locks,
        "active_activation_locks": active_locks,
        "corrupt_run_states": corrupt,
        "safe_actions": {
            "stale_lock": "Inspect the owning process before removing a lock.",
            "corrupt_state": "Restore state.json from version control or a reviewed backup.",
        },
    }
