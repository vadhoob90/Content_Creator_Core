"""Execute governed import and legacy placement migration commands."""

import argparse
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..packs import PackRegistry
from ..run_queries import RunQueries
from ..visual_contracts import VisualError
from ..visual_imports import VisualImportRequest, import_visual
from ..visual_migration import migrate_slots


def run_slot_command(root: Path, args: argparse.Namespace, emit: Callable[[Any], None]) -> int:
    """Dispatch typed import or migration through visual application boundaries.

    Args:
        root (Path): Workspace root.
        args (argparse.Namespace): Parsed command arguments.
        emit (Callable[[Any], None]): Structured result renderer.

    Returns:
        int: Zero after a successful operation.

    Raises:
        VisualError: If import input or migration evidence is invalid.
    """
    try:
        if args.visual_command == "migrate-slots":
            emit(migrate_slots(root, args.run_id))
        else:
            state = RunQueries(root).state(args.run_id)
            pack = PackRegistry(root).resolve(
                state.work_order.content_pack, state.work_order.pack_options
            )
            request = VisualImportRequest.model_validate_json(Path(args.request_file).read_bytes())
            if request.run_id != args.run_id:
                raise VisualError("Import request run ID differs from the selected run")
            emit(import_visual(root, pack.visuals, request))
    except (OSError, ValueError) as exc:
        raise VisualError(f"Invalid visual operation: {exc}") from exc
    return 0
