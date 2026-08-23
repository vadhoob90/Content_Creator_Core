"""Register, execute, and render the first-run setup journey."""

from __future__ import annotations

from typing import Any

from ..coordinator import ContentCoordinator
from ..coordinator_models import CoordinatorAction, FirstRunSetup
from ..first_run_setup import activate_setup_writing_style
from ..provider_setup import verify_and_select_provider
from .context import CommandContext
from .shared import PROVIDERS


def register(subparsers: Any) -> None:
    """Register the author-facing setup command.

    Args:
        subparsers (Any): Top-level CLI subparser collection.

    Returns:
        None: The parser is updated in place.
    """
    parser = subparsers.add_parser("setup", help="Reach your first draft step by step")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--details", action="store_true")
    commands = parser.add_subparsers(dest="setup_command")
    for name in ("starter", "source-derived"):
        choice = commands.add_parser(name)
        choice.add_argument("--json", action="store_true")
    provider = commands.add_parser("provider")
    provider.add_argument("provider_name", choices=PROVIDERS)
    provider.add_argument("--confirm-api-billing", action="store_true")
    provider.add_argument("--json", action="store_true")


def run(context: CommandContext) -> int:
    """Execute a read-only setup view or an explicit setup choice.

    Args:
        context (CommandContext): Resolved workspace and parsed arguments.

    Returns:
        int: Process exit status.
    """
    command = context.arguments.setup_command
    if command in {"starter", "source-derived"}:
        result = activate_setup_writing_style(context.root, command)
        _emit_result(context, result, render_writing_style_result(result))
        return 0
    if command == "provider":
        status, result = verify_and_select_provider(
            context.root,
            context.arguments.provider_name,
            confirm_api_billing=context.arguments.confirm_api_billing,
        )
        _emit_result(context, result, render_provider_result(result))
        return status
    snapshot = ContentCoordinator(context.root).snapshot()
    if context.arguments.json:
        context.emit(snapshot.setup)
    else:
        print(render_setup(snapshot.setup, details=context.arguments.details))
    return 0


def render_setup(setup: FirstRunSetup | None, *, details: bool = False) -> str:
    """Render setup progress without exposing audit vocabulary by default.

    Args:
        setup (FirstRunSetup | None): Derived setup state.
        details (bool): Whether to show advanced identifiers. Defaults to ``False``.

    Returns:
        str: Human-readable setup view.

    Raises:
        ValueError: If the coordinator omitted setup state.
    """
    if setup is None:
        raise ValueError("Setup state is unavailable")
    lines = [
        "Content Creator setup",
        f"{setup.completed_count} of {setup.total_count} ready",
        "",
    ]
    for milestone in setup.milestones:
        marker = "[x]" if milestone.status in {"ready", "reviewable", "complete"} else "[ ]"
        lines.append(f"{marker} {milestone.label}: {milestone.summary}")
    lines.extend(["", f"Next: {setup.recommended_action.label}"])
    command = _render_command(setup.recommended_action)
    if command:
        lines.append(command)
    if setup.choices:
        lines.extend(["", "Choose:"])
        lines.extend(f"- {choice.label}: {_render_command(choice)}" for choice in setup.choices)
    if details:
        lines.extend(
            [
                "",
                "Advanced details:",
                "content-creator overview --details",
                "content-creator personalisation show",
            ]
        )
    return "\n".join(lines)


def render_writing_style_result(result: dict[str, Any]) -> str:
    """Render a concise writing-style decision result.

    Args:
        result (dict[str, Any]): Structured setup mutation result.

    Returns:
        str: Human-readable result.
    """
    if result["status"] == "writing-style-ready":
        heading = "Writing style ready"
    else:
        heading = "Personalised writing setup started"
    return "\n".join([heading, f"Author: {result['author_name']}", result["next_step"]])


def render_provider_result(result: dict[str, Any]) -> str:
    """Render provider confirmation or success without credential detail.

    Args:
        result (dict[str, Any]): Structured provider setup result.

    Returns:
        str: Human-readable result.
    """
    if result["status"] == "confirmation-required":
        return "\n".join(["Billing confirmation required", result["message"]])
    return "\n".join(
        [
            "Model connection ready",
            f"Provider: {result['provider']}",
            "Tell me what you want to create.",
        ]
    )


def _emit_result(context: CommandContext, result: dict[str, Any], human: str) -> None:
    """Render and emit a setup result in the selected representation.

    Args:
        context (CommandContext): Resolved workspace and parsed arguments.
        result (dict[str, Any]): Structured setup result.
        human (str): Human-readable rendering.

    Returns:
        None: Output is emitted to the selected interface.
    """
    if context.arguments.json:
        context.emit(result)
    else:
        print(human)


def _render_command(action: CoordinatorAction) -> str:
    """Render an action command for direct copy and execution.

    Args:
        action (CoordinatorAction): Typed coordinator action.

    Returns:
        str: Complete command or empty text.
    """
    if not action.command:
        return ""
    return "content-creator {}".format(" ".join(action.command))
