"""Small top-level commands that delegate to established application services."""

from __future__ import annotations

from typing import Callable

from ..agent_resources import AgentWorkspace
from ..evaluation import run_live_suite, run_replay_suite
from ..health import WorkspaceHealth
from ..packs import PackRegistry
from ..workspace import initialise_workspace
from . import operations as operations_commands
from . import provider as provider_commands
from . import schema as schema_commands
from . import visual as visual_commands
from .context import CommandContext

CommandHandler = Callable[[CommandContext], int]


def show_advanced(context: CommandContext) -> int:
    """Show advanced."""
    print(
        "Advanced commands:\n"
        "  init, agents, provider, plan, coordinator, pack, packs, voice,\n"
        "  perspective, approve-research, reject-research, eval\n\n"
        "Use: content-creator <command> --help"
    )
    return 0


def inspect_schema(context: CommandContext) -> int:
    """Inspect schema."""
    return schema_commands.run(context.root, context.arguments, context.emit)


def inspect_operations(context: CommandContext) -> int:
    """Inspect operations."""
    return operations_commands.run(context.root, context.arguments, context.emit)


def initialise(context: CommandContext) -> int:
    """Initialise base commands."""
    context.emit(initialise_workspace(context.root, context.arguments.agent_template))
    return 0


def manage_agents(context: CommandContext) -> int:
    """Manage agents."""
    workspace = AgentWorkspace(context.root)
    command = context.arguments.agent_command
    operations = {
        "scaffold": workspace.scaffold,
        "status": workspace.status,
        "diff-template": workspace.diff_template,
    }
    context.emit(operations[command](context.arguments.template))
    return 0


def manage_provider(context: CommandContext) -> int:
    """Manage provider."""
    return provider_commands.run(context.root, context.arguments, context.emit)


def check_workspace(context: CommandContext) -> int:
    """Check workspace."""
    report = WorkspaceHealth(context.root).report()
    context.emit(report)
    return 0 if report["status"] == "ok" else 1


def list_packs(context: CommandContext) -> int:
    """List packs."""
    context.emit([pack.model_dump(mode="json") for pack in PackRegistry(context.root).list()])
    return 0


def manage_voice(context: CommandContext) -> int:
    """Manage voice."""
    from .voice import run

    return run(context.root, context.arguments)


def manage_perspective(context: CommandContext) -> int:
    """Manage perspective."""
    from .perspective import run

    return run(context.root, context.arguments)


def evaluate(context: CommandContext) -> int:
    """Evaluate base commands."""
    runner = run_live_suite if context.arguments.mode == "live" else run_replay_suite
    report = runner(context.root, context.arguments.providers)
    context.emit(report)
    return 0 if report["passed"] == report["total"] else 1


def manage_visuals(context: CommandContext) -> int:
    """Manage visuals."""
    return visual_commands.run(context.root, context.arguments, context.emit)
