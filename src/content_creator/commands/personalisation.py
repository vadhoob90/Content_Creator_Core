"""Register and run author-facing personalisation inspection."""

from __future__ import annotations

import argparse

from ..personalisation import PersonalisationInspector, render_personalisation
from .context import CommandContext


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register the personalisation command family.

    Args:
        subparsers (argparse._SubParsersAction): Top-level parser collection.

    Returns:
        None: The parser is updated in place.
    """
    personalisation = subparsers.add_parser(
        "personalisation",
        help="Explain your agents, learning, voice, and perspectives",
    )
    commands = personalisation.add_subparsers(dest="personalisation_command", required=True)
    show = commands.add_parser("show", help="Show the effective personalisation")
    show.add_argument("--json", action="store_true")


def run(context: CommandContext) -> int:
    """Inspect and render workspace personalisation.

    Args:
        context (CommandContext): Command dependencies and arguments.

    Returns:
        int: Zero after the read-only report is emitted.
    """
    report = PersonalisationInspector(context.root).inspect()
    if context.arguments.json:
        context.emit(report)
    else:
        print(render_personalisation(report))
    return 0
