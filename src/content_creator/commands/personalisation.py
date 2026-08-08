"""Register and run author-facing personalisation inspection."""

from __future__ import annotations

import argparse

from ..agent_resources import ROLE_FILES
from ..context_composition import ContextLayer, render_preflight
from ..context_preflight import explain_context
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
    explain = commands.add_parser("explain", help="Preview what a role would receive at runtime")
    explain.add_argument("--role", required=True, choices=sorted(ROLE_FILES))
    explain.add_argument("--voice")
    explain.add_argument("--pack")
    explain.add_argument("--research", choices=["none", "light", "deep"], default="none")
    explain.add_argument("--perspective-context", action="append", default=[])
    explain.add_argument("--json", action="store_true")


def run(context: CommandContext) -> int:
    """Inspect and render workspace personalisation.

    Args:
        context (CommandContext): Command dependencies and arguments.

    Returns:
        int: Zero after the read-only report is emitted.
    """
    if context.arguments.personalisation_command == "explain":
        report = explain_context(
            context.root,
            role=context.arguments.role,
            voice_id=context.arguments.voice,
            pack_id=context.arguments.pack,
            research=context.arguments.research,
            perspectives=context.arguments.perspective_context,
        )
        if context.arguments.json:
            context.emit(report)
        else:
            layers = [ContextLayer.model_validate(item) for item in report["instruction_layers"]]
            print(render_preflight(report["role"], layers))
        return 0
    report = PersonalisationInspector(context.root).inspect()
    if context.arguments.json:
        context.emit(report)
    else:
        print(render_personalisation(report))
    return 0
