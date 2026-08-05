"""Implement the schema command family."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..schema_registry import schema_catalogue, write_schema_bundle


def register(subparsers: Any) -> None:
    """Register the schema workflow.

    Args:
        subparsers (Any): The argparse subparser collection receiving the command.

    Returns:
        None: The callable updates register state and returns no value.
    """
    parser = subparsers.add_parser("schema", help="Inspect versioned persisted contracts")
    commands = parser.add_subparsers(dest="schema_command", required=True)
    commands.add_parser("list")
    export = commands.add_parser("export")
    export.add_argument("directory")


def run(root: Path, args: Any, print_value: Callable[[Any], None]) -> int:
    """Run the schema workflow.

    Args:
        root (Path): The workspace root directory.
        args (Any): The parsed command-line arguments.
        print_value (Callable[[Any], None]): The print value value passed to run.

    Returns:
        int: The process exit status, where zero indicates successful handling.
    """
    if args.schema_command == "list":
        print_value(schema_catalogue())
        return 0
    destination = Path(args.directory)
    if not destination.is_absolute():
        destination = root / destination
    print_value(write_schema_bundle(destination.resolve()))
    return 0
