"""Schema catalogue command family."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..schema_registry import schema_catalogue, write_schema_bundle


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser("schema", help="Inspect versioned persisted contracts")
    commands = parser.add_subparsers(dest="schema_command", required=True)
    commands.add_parser("list")
    export = commands.add_parser("export")
    export.add_argument("directory")


def run(root: Path, args: Any, print_value: Callable[[Any], None]) -> int:
    if args.schema_command == "list":
        print_value(schema_catalogue())
        return 0
    destination = Path(args.directory)
    if not destination.is_absolute():
        destination = root / destination
    print_value(write_schema_bundle(destination.resolve()))
    return 0
