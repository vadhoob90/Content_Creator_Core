"""Manage nested visual operations with author edits and publication."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from typing import Any

from .versioned_artifacts import ActivationLock
from .visual_contracts import VisualError

_ACTIVE: ContextVar[frozenset[str]] = ContextVar("visual_mutations", default=frozenset())


@contextmanager
def visual_lock(root: Path, run_id: str) -> Iterator[None]:
    """Manage a shared run lock throughout a complete nested visual operation.

    Args:
        root (Path): Workspace root.
        run_id (str): Validated run identifier.

    Returns:
        Iterator[None]: Guarded mutation context.

    Raises:
        VisualError: If run identity or interrupted edit evidence is invalid.
    """
    from .visual_contracts import VisualBrief

    VisualBrief.validate_run_id(run_id)
    run = root / "runs" / run_id
    if not (run / "state.json").is_file() or run.is_symlink():
        raise VisualError("Unknown or unsafe visual run")
    if (run / "author-edit-transaction.json").exists():
        raise VisualError("Recover the interrupted author edit before changing visuals")
    key = str(run.resolve())
    if key in _ACTIVE.get():
        yield
        return
    with ActivationLock(
        run / ".author-edit.lock", "Another run operation is in progress", VisualError
    ):
        token = _ACTIVE.set(_ACTIVE.get() | {key})
        try:
            yield
        finally:
            _ACTIVE.reset(token)


def serialize_visual(operation: Callable[..., Any]) -> Callable[..., Any]:
    """Provide visual application methods with the shared reentrant run lock.

    Args:
        operation (Callable[..., Any]): Method receiving a run ID, brief, or render request.

    Returns:
        Callable[..., Any]: Serialized application method.
    """

    @wraps(operation)
    def locked(workflow: Any, *args: Any, **kwargs: Any) -> Any:
        """Execute one complete visual mutation under its owning run lock.

        Args:
            workflow (Any): Visual application boundary.
            *args (tuple[Any, ...]): Positional operation arguments.
            **kwargs (dict[str, Any]): Named operation arguments.

        Returns:
            Any: Wrapped operation result.
        """
        candidate = kwargs.get("request") or kwargs.get("brief") or kwargs.get("run_id")
        if candidate is None:
            candidate = args[1] if operation.__name__ == "render" else args[0]
        run_id = candidate if isinstance(candidate, str) else candidate.run_id
        with visual_lock(workflow.root, run_id):
            result = operation(workflow, *args, **kwargs)
            from .visual_projection import project_visual_manifest

            project_visual_manifest(workflow.root, run_id)
            return result

    return locked
