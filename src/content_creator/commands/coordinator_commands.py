"""Coordinator inspection command handlers."""

from __future__ import annotations

from ..coordinator import ContentCoordinator
from .context import CommandContext


def inspect_coordinator(context: CommandContext) -> int:
    coordinator = ContentCoordinator(context.root)
    arguments = context.arguments
    operations = {
        "capabilities": lambda: coordinator.capabilities(),
        "context": lambda: coordinator.context(arguments.run_limit),
        "runs": lambda: coordinator.runs(arguments.limit),
        "next-actions": lambda: coordinator.next_actions(arguments.run_id),
    }
    context.emit(operations[arguments.coordinator_command]())
    return 0
