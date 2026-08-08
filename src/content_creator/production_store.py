"""Compose production-manifest refresh with low-level run persistence."""

from pathlib import Path

from .domain import RunState
from .production_manifest import refresh_production_manifest
from .storage import RunStore, StateWriter


def production_run_store(root: Path) -> RunStore:
    """Create a run store that refreshes production metadata before each save.

    Args:
        root (Path): Workspace root containing run state and production evidence.

    Returns:
        RunStore: Run persistence composed with the production-manifest hook.
    """
    return RunStore(root, before_state_save=_refresh_manifest)


def _refresh_manifest(root: Path, state: RunState, write_text: StateWriter) -> None:
    """Write production metadata through the generic storage hook.

    Args:
        root (Path): Workspace root containing the persisted run.
        state (RunState): Current state about to be persisted.
        write_text (StateWriter): Atomic text writer owned by the run store.

    Returns:
        None: Production artifacts and state paths are refreshed in place.
    """
    refresh_production_manifest(root, state, write_text)
