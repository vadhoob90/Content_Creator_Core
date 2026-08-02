"""Create and upgrade thin Content Creator workspaces."""

from __future__ import annotations

from pathlib import Path

from ..upgrade import WorkspaceUpgrader
from ..workspace import WorkspaceScaffolder
from ..workspace_scaffolding import WorkspaceCreateRequest
from .context import CommandContext


def _destination(context: CommandContext) -> Path:
    destination = Path(context.arguments.directory).expanduser()
    if not destination.is_absolute():
        base = context.root if context.arguments.root else Path.cwd()
        destination = base / destination
    return destination.resolve()


def manage_workspace(context: CommandContext) -> int:
    """Preview/apply an upgrade or scaffold a new author workspace."""
    arguments = context.arguments
    if arguments.workspace_command == "upgrade":
        upgrader = WorkspaceUpgrader(context.root)
        report = upgrader.apply(arguments.to) if arguments.apply else upgrader.preview(arguments.to)
        context.emit(report)
        return 0

    destination = _destination(context)
    context.emit(
        WorkspaceScaffolder(destination).create(
            WorkspaceCreateRequest(
                name=arguments.name or destination.name,
                author_name=arguments.author_name,
                voice_id=arguments.voice_id,
                voice_label=arguments.voice_label,
                packs=arguments.pack,
                agent_template=arguments.agent_template,
                core_source=arguments.core_source,
                core_url=arguments.core_url,
                core_ref=arguments.core_ref,
                perspective_mode=arguments.perspective_mode,
            )
        )
    )
    return 0
