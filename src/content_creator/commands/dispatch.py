"""Route parsed commands to focused handlers without embedding domain behaviour."""

from __future__ import annotations

from typing import Callable, List, Optional

from ..orchestrator import Orchestrator
from .base_commands import (
    check_workspace,
    evaluate,
    initialise,
    inspect_operations,
    inspect_schema,
    list_packs,
    manage_agents,
    manage_perspective,
    manage_provider,
    manage_visuals,
    manage_voice,
    show_advanced,
)
from .context import CommandContext
from .coordinator_commands import inspect_coordinator
from .experience_commands import plan, show_overview, start
from .lifecycle_commands import (
    approve_research,
    inspect_diagnostics,
    publish,
    reject_research,
    show_status,
    show_submission,
)
from .pack_commands import manage_pack
from .parser import build_parser
from .run_commands import run as run_content
from .shared import print_json, resolve_root
from .workspace_commands import manage_workspace

Handler = Callable[[CommandContext], int]
ROUTES: dict[str, Handler] = {
    "advanced": show_advanced,
    "agents": manage_agents,
    "approve-research": approve_research,
    "coordinator": inspect_coordinator,
    "diagnostics": inspect_diagnostics,
    "doctor": check_workspace,
    "eval": evaluate,
    "init": initialise,
    "operations": inspect_operations,
    "overview": show_overview,
    "pack": manage_pack,
    "packs": list_packs,
    "perspective": manage_perspective,
    "plan": plan,
    "provider": manage_provider,
    "publish": publish,
    "reject-research": reject_research,
    "run": run_content,
    "schema": inspect_schema,
    "start": start,
    "status": show_status,
    "submission": show_submission,
    "visual": manage_visuals,
    "voice": manage_voice,
    "workspace": manage_workspace,
}


def run(argv: Optional[List[str]] = None) -> int:
    """Run the dispatch workflow.

    Args:
        argv (Optional[List[str]]): The command-line argument sequence. Defaults to
            ``None``.

    Returns:
        int: The process exit status, where zero indicates successful handling.
    """
    arguments = build_parser().parse_args(argv)
    handler = ROUTES.get(arguments.command)
    if handler is None:
        return 2
    context = CommandContext(
        root=resolve_root(arguments.root),
        arguments=arguments,
        emit=print_json,
        orchestrator_type=Orchestrator,
    )
    return handler(context)
