"""Register workspace, agent, and author-experience command arguments."""

from __future__ import annotations

import argparse

from ..agent_resources import STANDARD_TEMPLATE
from ..workspace import DEFAULT_CORE_REF, DEFAULT_CORE_SOURCE, DEFAULT_CORE_URL
from .shared import PROVIDERS


def register_workspace(subparsers: argparse._SubParsersAction) -> None:
    """Register the workspace.

    Args:
        subparsers (argparse._SubParsersAction): The argparse subparser collection
            receiving the command.

    Returns:
        None: The callable updates register workspace state and returns no value.
    """
    initialise = subparsers.add_parser("init", help=argparse.SUPPRESS)
    initialise.add_argument("--agent-template", default=STANDARD_TEMPLATE)
    workspace = subparsers.add_parser(
        "workspace",
        help="Create a complete thin repository that consumes Content Creator Core",
    )
    commands = workspace.add_subparsers(dest="workspace_command", required=True)
    create = commands.add_parser("create", help="Scaffold a new author-owned content repository")
    create.add_argument("directory", help="Destination directory; created when it does not exist")
    create.add_argument("--name", help="Repository display name")
    create.add_argument("--author-name", required=True)
    create.add_argument("--voice-id")
    create.add_argument("--voice-label")
    create.add_argument("--pack", action="append", default=[])
    create.add_argument("--agent-template", default=STANDARD_TEMPLATE)
    create.add_argument("--core-source", choices=["registry", "git"], default=DEFAULT_CORE_SOURCE)
    create.add_argument("--core-url", default=DEFAULT_CORE_URL)
    create.add_argument("--core-ref", default=DEFAULT_CORE_REF)
    create.add_argument(
        "--perspective-mode",
        choices=["automatic", "explicit", "disabled"],
        default="automatic",
    )
    upgrade = commands.add_parser("upgrade", help="Preview or apply an immutable Core upgrade")
    upgrade.add_argument("--to", required=True)
    upgrade.add_argument("--apply", action="store_true")
    resolve_run = commands.add_parser(
        "resolve-upgrade-run",
        help="Adopt current pack policy and revalidate one historical run",
    )
    resolve_run.add_argument("run_id")
    resolve_run.add_argument("--accept-current-pack", action="store_true", required=True)


def register_agents(subparsers: argparse._SubParsersAction) -> None:
    """Register the agents.

    Args:
        subparsers (argparse._SubParsersAction): The argparse subparser collection
            receiving the command.

    Returns:
        None: The callable updates register agents state and returns no value.
    """
    agents = subparsers.add_parser("agents", help=argparse.SUPPRESS)
    commands = agents.add_subparsers(dest="agent_command", required=True)
    for command_name in ("scaffold", "status", "diff-template"):
        command = commands.add_parser(command_name)
        command.add_argument("--template", default=STANDARD_TEMPLATE)


def register_experience(subparsers: argparse._SubParsersAction) -> None:
    """Register the experience.

    Args:
        subparsers (argparse._SubParsersAction): The argparse subparser collection
            receiving the command.

    Returns:
        None: The callable updates register experience state and returns no value.
    """
    plan = subparsers.add_parser("plan", help=argparse.SUPPRESS)
    plan.add_argument("request")
    plan.add_argument("--provider", choices=PROVIDERS)
    start = subparsers.add_parser("start", help="Inspect the workspace and guide the author")
    start.add_argument("request", nargs="?")
    start.add_argument("--provider", choices=PROVIDERS)
    start.add_argument("--json", action="store_true")
    overview = subparsers.add_parser("overview", help="Show workspace health and next action")
    overview.add_argument("--json", action="store_true")
    overview.add_argument("--run-limit", type=int, default=5)
    subparsers.add_parser("doctor", help="Validate offline configuration and assets")
