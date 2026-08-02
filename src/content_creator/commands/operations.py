"""Operational recovery command family."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..operations import build_support_bundle, recovery_report


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser("operations", help="Inspect and recover local runtime state")
    commands = parser.add_subparsers(dest="operations_command", required=True)
    support = commands.add_parser("support-bundle")
    support.add_argument("run_id")
    commands.add_parser("recovery-report")


def run(root: Path, args: Any, print_value: Callable[[Any], None]) -> int:
    if args.operations_command == "support-bundle":
        print_value(build_support_bundle(root, args.run_id))
    else:
        print_value(recovery_report(root))
    return 0
