"""Provide read-only application queries for persisted content runs."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .domain import RunState
from .storage import RunStore


class RunQueries:
    """Read persisted run state without exposing mutable storage to entry points."""

    def __init__(self, root: Path):
        """Initialize read-only run queries for one workspace.

        Args:
            root (Path): Workspace root containing persisted runs.

        Returns:
            None: The query service is initialized in place.
        """
        self._store = RunStore(root.resolve())

    def state(self, run_id: str) -> RunState:
        """Return one persisted run state.

        Args:
            run_id (str): Stable content run identifier.

        Returns:
            RunState: Persisted state for the selected run.
        """
        return self._store.load(run_id)

    def submission(self, idempotency_key: str) -> Optional[RunState]:
        """Return the run associated with an idempotent submission.

        Args:
            idempotency_key (str): Original stable submission key.

        Returns:
            Optional[RunState]: Matching persisted state, or ``None`` when unknown.
        """
        return self._store.load_by_idempotency_key(idempotency_key)

    def artifact(self, run_id: str, relative: str) -> str:
        """Return one text artifact from a persisted run.

        Args:
            run_id (str): Stable content run identifier.
            relative (str): Run-relative artifact path.

        Returns:
            str: Persisted artifact text.
        """
        return self._store.read_artifact(run_id, relative)
