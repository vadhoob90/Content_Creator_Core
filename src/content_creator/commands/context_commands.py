"""Register and render historical runtime context composition."""

from __future__ import annotations

import argparse

from ..context_composition import ContextCompositionStore, render_context_manifest
from .context import CommandContext


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register historical context-composition inspection.

    Args:
        subparsers (argparse._SubParsersAction): Top-level parser collection.

    Returns:
        None: The parser is updated in place.
    """
    context = subparsers.add_parser(
        "context", help="Show what was injected into each agent invocation"
    )
    commands = context.add_subparsers(dest="context_command", required=True)
    show = commands.add_parser("show", help="Show composition for a persisted run")
    show.add_argument("run_id")
    show.add_argument("--json", action="store_true")


def run(context: CommandContext) -> int:
    """Render one persisted composition manifest.

    Args:
        context (CommandContext): Command dependencies and arguments.

    Returns:
        int: Zero after the read-only report is emitted.
    """
    manifest = ContextCompositionStore(context.root).read(context.arguments.run_id)
    if context.arguments.json:
        context.emit(manifest)
    else:
        print(render_context_manifest(manifest))
    return 0
