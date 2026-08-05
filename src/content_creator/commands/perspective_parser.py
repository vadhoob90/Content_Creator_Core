"""Implement the perspective parser command family."""

from __future__ import annotations

import argparse


def register(sub: argparse._SubParsersAction) -> None:
    """Register the perspective parser workflow.

    Register the perspective catalogue, lifecycle, comparison, and proposal subcommands
    with their complete argument contracts.

    Args:
        sub (argparse._SubParsersAction): The sub value passed to register.

    Returns:
        None: The callable updates register state and returns no value.
    """
    perspective = sub.add_parser(
        "perspective",
        help=argparse.SUPPRESS,
    )
    perspective_sub = perspective.add_subparsers(dest="perspective_command", required=True)
    perspective_create = perspective_sub.add_parser("create")
    perspective_create.add_argument("--voice", required=True)
    perspective_create.add_argument("--context", required=True)
    perspective_create.add_argument("--display-name")
    perspective_create.add_argument("--statement")
    perspective_create.add_argument("--type", default="position")
    perspective_create.add_argument("--topic", action="append", default=[])
    perspective_create.add_argument("--qualification", action="append", default=[])
    perspective_create.add_argument("--counterposition", action="append", default=[])
    perspective_create.add_argument("--evidence")
    perspective_list = perspective_sub.add_parser("list")
    perspective_list.add_argument("--voice", required=True)
    perspective_catalogue = perspective_sub.add_parser("catalogue")
    perspective_catalogue.add_argument("--voice", required=True)
    perspective_verify_catalogue = perspective_sub.add_parser("verify-catalogue")
    perspective_verify_catalogue.add_argument("--voice", required=True)
    for command in ("status", "show", "verify", "proposals"):
        item = perspective_sub.add_parser(command)
        item.add_argument("--voice", required=True)
        item.add_argument("--context", required=True)
    perspective_approve = perspective_sub.add_parser("approve")
    perspective_approve.add_argument("--voice", required=True)
    perspective_approve.add_argument("--context", required=True)
    perspective_approve.add_argument("--approved-by", default="repository-owner")
    perspective_deactivate = perspective_sub.add_parser("deactivate")
    perspective_deactivate.add_argument("--voice", required=True)
    perspective_deactivate.add_argument("--context", required=True)
    perspective_deactivate.add_argument("--reason", required=True)
    perspective_stage = perspective_sub.add_parser("stage-proposal")
    perspective_stage.add_argument("--voice", required=True)
    perspective_stage.add_argument("--context", required=True)
    perspective_stage.add_argument("--proposal", required=True)
    perspective_retire = perspective_sub.add_parser("retire")
    perspective_retire.add_argument("--voice", required=True)
    perspective_retire.add_argument("--context", required=True)
    perspective_retire.add_argument("--entry", required=True)
    perspective_retire.add_argument("--reason", required=True)
    perspective_compare = perspective_sub.add_parser("compare-create")
    perspective_compare.add_argument("--run", required=True)
    perspective_compare.add_argument("--baseline", required=True)
    perspective_record = perspective_sub.add_parser("compare-record")
    perspective_record.add_argument("--run", required=True)
    perspective_record.add_argument("--assessment", required=True)
