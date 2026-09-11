"""Manage interrupted author-edit writes using a run-local recovery journal."""

import base64
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Any

from .domain import RunState
from .storage import RunStore, StorageError
from .versioned_artifacts import ActivationLock

JOURNAL = "author-edit-transaction.json"


@contextmanager
def edit_transaction(run: Path, names: list[str]) -> Iterator[None]:
    """Preserve touched artifacts and roll them back on a failed edit operation.

    The journal remains after process interruption, preventing publication until
    explicit recovery. Only paths owned by this operation are restored.

    Args:
        run (Path): Validated run directory under an acquired edit lock.
        names (list[str]): Relative artifacts that the operation may change.

    Returns:
        Iterator[None]: Context manager permitting bounded writes before completion.

    Raises:
        StorageError: If an earlier operation requires recovery.
    """
    journal = run / JOURNAL
    if journal.exists():
        raise StorageError("Interrupted author edit; run recover-edit before another mutation")
    before = {}
    for name in names:
        path = _confined(run, name)
        before[name] = base64.b64encode(path.read_bytes()).decode() if path.exists() else None
    RunStore._atomic_text(journal, json.dumps({"schema_version": "1.0", "before": before}))
    try:
        yield
    except Exception:
        restore_edit(run)
        raise
    else:
        journal.unlink()


def restore_edit(run: Path) -> None:
    """Restore precisely the artifacts recorded by an interrupted edit operation.

    Args:
        run (Path): Run directory under an acquired edit lock.

    Returns:
        None: Prior bytes are restored and the journal is removed.

    Raises:
        StorageError: If the journal is absent, malformed, or uses an unknown version.
    """
    journal = run / JOURNAL
    if not journal.is_file():
        raise StorageError("Run has no interrupted author edit to recover")
    payload = json.loads(journal.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "1.0" or not isinstance(payload.get("before"), dict):
        raise StorageError("Invalid author-edit recovery journal")
    originals = {
        _confined(run, name): base64.b64decode(content, validate=True)
        if content is not None
        else None
        for name, content in payload["before"].items()
    }
    for path, content in originals.items():
        if content is None:
            path.unlink(missing_ok=True)
        else:
            RunStore.atomic_bytes(path, content)
    journal.unlink()


def _confined(run: Path, name: str) -> Path:
    """Validate a recovery artifact path before reading or writing bytes.

    Args:
        run (Path): Run root.
        name (str): Relative journal artifact path.

    Returns:
        Path: Confined artifact path.

    Raises:
        StorageError: If a path escapes the run or targets the journal or lock.
    """
    path = (run / name).resolve()
    if not path.is_relative_to(run.resolve()) or Path(name).is_absolute():
        raise StorageError("Author-edit artifact path leaves the run")
    if path.name in {JOURNAL, ".author-edit.lock"}:
        raise StorageError("Author-edit artifact path targets operation metadata")
    return path


def serialize_run(operation: Callable[..., RunState]) -> Callable[..., RunState]:
    """Execute revision and publication against explicit author-edit operations.

    Args:
        operation (Callable[..., RunState]): Orchestrator operation accepting a run ID.

    Returns:
        Callable[..., RunState]: Wrapped operation holding the shared run mutation lock.
    """

    @wraps(operation)
    def serialized(workflow: Any, run_id: str, *args: Any, **kwargs: Any) -> RunState:
        """Execute a run operation under the shared author-edit lock.

        Args:
            workflow (Any): Orchestrator with composed run persistence.
            run_id (str): Run to mutate.
            *args (tuple[Any, ...]): Remaining positional operation arguments.
            **kwargs (dict[str, Any]): Remaining named operation arguments.

        Returns:
            RunState: Result of the serialized operation.

        Raises:
            StorageError: If an interrupted edit must be recovered first.
        """
        run = workflow.store.run_dir(run_id)
        with ActivationLock(run / ".author-edit.lock", "Another edit is in progress", StorageError):
            if (run / JOURNAL).exists():
                raise StorageError(
                    "Interrupted author edit; run recover-edit before another mutation"
                )
            return operation(workflow, run_id, *args, **kwargs)

    return serialized
