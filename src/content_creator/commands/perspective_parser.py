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
    perspective_deactivate.add_argument("--deactivated-by", default="repository-owner")
    _register_context_lifecycle(perspective_sub)
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


def _register_context_lifecycle(perspective_sub: argparse._SubParsersAction) -> None:
    """Register complete perspective-context lifecycle commands.

    Keep aggregate retirement routes together so their actor, reason, plan,
    and exact-hash decision arguments remain visibly consistent.

    Args:
        perspective_sub (argparse._SubParsersAction): Perspective command collection.

    Returns:
        None: Context lifecycle routes are registered in place.
    """
    perspective_reactivate = perspective_sub.add_parser("reactivate")
    perspective_reactivate.add_argument("--voice", required=True)
    perspective_reactivate.add_argument("--context", required=True)
    perspective_reactivate.add_argument("--approved-by", default="repository-owner")
    perspective_reactivate.add_argument("--reason", default="author reactivation")
    perspective_plan = perspective_sub.add_parser("retirement-plan")
    perspective_plan.add_argument("--voice", required=True)
    perspective_plan.add_argument("--context", required=True)
    perspective_retire_context = perspective_sub.add_parser("retire-context")
    perspective_retire_context.add_argument("--voice", required=True)
    perspective_retire_context.add_argument("--context", required=True)
    perspective_retire_context.add_argument("--retired-by", required=True)
    perspective_retire_context.add_argument("--reason", required=True)
    perspective_retire_context.add_argument("--plan-hash", required=True)
    perspective_retire_context.add_argument(
        "--candidate-disposition", choices=["retain", "reject", "abandon"]
    )
    perspective_retire_context.add_argument(
        "--proposal-disposition", choices=["retain", "reject", "abandon"]
    )
    perspective_restore_plan = perspective_sub.add_parser("restore-context-plan")
    perspective_restore_plan.add_argument("--voice", required=True)
    perspective_restore_plan.add_argument("--context", required=True)
    perspective_restore = perspective_sub.add_parser("restore-context")
    perspective_restore.add_argument("--voice", required=True)
    perspective_restore.add_argument("--context", required=True)
    perspective_restore.add_argument("--requested-by", required=True)
    perspective_restore.add_argument("--approved-by", required=True)
    perspective_restore.add_argument("--plan-hash", required=True)
    for decision in ("reject-candidate", "abandon-candidate"):
        candidate_decision = perspective_sub.add_parser(decision)
        candidate_decision.add_argument("--voice", required=True)
        candidate_decision.add_argument("--context", required=True)
        candidate_decision.add_argument("--candidate-hash", required=True)
        candidate_decision.add_argument("--decided-by", required=True)
        candidate_decision.add_argument("--reason", required=True)
    perspective_verify_lifecycle = perspective_sub.add_parser("verify-lifecycle")
    perspective_verify_lifecycle.add_argument("--voice", required=True)
    perspective_verify_lifecycle.add_argument("--context", required=True)
    perspective_migrate = perspective_sub.add_parser("migrate-lifecycle")
    perspective_migrate.add_argument("--voice", required=True)
    perspective_migrate.add_argument("--context", required=True)
    perspective_migrate.add_argument("--migrated-by", required=True)
