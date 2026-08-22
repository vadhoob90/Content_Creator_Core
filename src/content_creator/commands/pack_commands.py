"""Implement the pack commands command family."""

from __future__ import annotations

from ..packs import PackRegistry
from .context import CommandContext


def _create_pack(context: CommandContext, packs: PackRegistry) -> int:
    """Create the pack.

    Args:
        context (CommandContext): The operation context and its resolved dependencies.
        packs (PackRegistry): The packs value passed to create pack.

    Returns:
        int: The created numeric value for pack.
    """
    arguments = context.arguments
    context.emit(packs.create(arguments.pack_id, arguments.extends))
    return 0


def manage_pack(context: CommandContext) -> int:
    """Manage the pack.

    Args:
        context (CommandContext): The operation context and its resolved dependencies.

    Returns:
        int: The resulting numeric value for manage pack.
    """
    packs = PackRegistry(context.root)
    arguments = context.arguments
    if arguments.pack_command == "create":
        return _create_pack(context, packs)
    if arguments.pack_command == "list":
        context.emit([pack.model_dump(mode="json") for pack in packs.list()])
        return 0
    should_resolve = arguments.pack_command in {"show", "validate"} or arguments.resolved
    context.emit(
        packs.resolve(arguments.pack_id) if should_resolve else packs.get(arguments.pack_id)
    )
    return 0
