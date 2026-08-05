"""Implement the operations command family."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..operations import build_support_bundle, recovery_report


def register(subparsers: Any) -> None:
    """Register the operations workflow.

    Args:
        subparsers (Any): The argparse subparser collection receiving the command.

    Returns:
        None: The callable updates register state and returns no value.
    """
    parser = subparsers.add_parser("operations", help="Inspect and recover local runtime state")
    commands = parser.add_subparsers(dest="operations_command", required=True)
    support = commands.add_parser("support-bundle")
    support.add_argument("run_id")
    commands.add_parser("recovery-report")


def run(root: Path, args: Any, print_value: Callable[[Any], None]) -> int:
    """Run the operations workflow.

    Args:
        root (Path): The workspace root directory.
        args (Any): The parsed command-line arguments.
        print_value (Callable[[Any], None]): The print value value passed to run.

    Returns:
        int: The process exit status, where zero indicates successful handling.
    """
    if args.operations_command == "support-bundle":
        print_value(build_support_bundle(root, args.run_id))
    else:
        print_value(recovery_report(root))
    return 0
