"""Register voice command arguments in cohesive groups."""

from __future__ import annotations

import argparse

from .shared import PROVIDERS


def _register_onboard(commands: argparse._SubParsersAction) -> None:
    """Register the onboard.

    Args:
        commands (argparse._SubParsersAction): The commands value passed to register
            onboard.

    Returns:
        None: The callable updates register onboard state and returns no value.
    """
    onboard = commands.add_parser("onboard", help="Choose a starter or source-derived voice route")
    onboard.add_argument("voice_id")
    onboard.add_argument("--strategy", choices=["starter", "source-derived"], required=True)
    onboard.add_argument("--author-name", required=True)
    onboard.add_argument("--label")
    onboard.add_argument("--selected-by", default="repository-owner")
    onboard.add_argument("--use", action="append", default=[])
    onboard.add_argument(
        "--statistical-voice-score",
        choices=["disabled", "deterministic", "ml"],
        default="disabled",
    )


def _register_create(commands: argparse._SubParsersAction) -> None:
    """Register the create.

    Args:
        commands (argparse._SubParsersAction): The commands value passed to register
            create.

    Returns:
        None: The callable updates register create state and returns no value.
    """
    create = commands.add_parser("create")
    create.add_argument("--name", help="Legacy shorthand for author, label, and id")
    create.add_argument("--voice-id")
    create.add_argument("--label")
    create.add_argument("--author-name")
    create.add_argument("--author-alias", action="append", default=[])
    create.add_argument("--authorised-by")
    create.add_argument("--use", action="append", default=[])
    create.add_argument("--sources")
    create.add_argument("--documents", action="append", default=[])
    create.add_argument("--no-build", action="store_true")
    create.add_argument("--provider", choices=PROVIDERS)
    create.add_argument(
        "--statistical-voice-score",
        choices=["disabled", "deterministic", "ml"],
        default="disabled",
    )
    create.add_argument("--offline-analysis", action="store_true")


def _register_build_and_assessment(commands: argparse._SubParsersAction) -> None:
    """Register the build and assessment.

    Args:
        commands (argparse._SubParsersAction): The commands value passed to register
            build and assessment.

    Returns:
        None: The callable updates register build and assessment state and returns no
            value.
    """
    for command_name in ("build", "rebuild", "status", "show", "signature", "verify"):
        command = commands.add_parser(command_name)
        command.add_argument("voice_id")
        if command_name == "status":
            command.add_argument("--human", action="store_true")
        if command_name in {"build", "rebuild"}:
            command.add_argument("--provider", choices=PROVIDERS)
            command.add_argument("--offline-analysis", action="store_true")
            command.add_argument(
                "--full-regenerate",
                action="store_true",
                help="Explicitly replace an active voice instead of preserving it",
            )
            command.add_argument(
                "--change-set",
                help="JSON file containing evidence-backed semantic voice changes",
            )
    assess = commands.add_parser("assess")
    assess.add_argument("voice_id")
    assess.add_argument("--draft", required=True)
    assess.add_argument("--voice-version")
    score = commands.add_parser("score")
    score.add_argument("voice_id")
    score.add_argument("--draft", required=True)
    score.add_argument("--voice-version")
    score.add_argument("--method", choices=["deterministic", "ml"], required=True)
    score_config = commands.add_parser("score-config")
    score_config.add_argument("voice_id")
    score_config.add_argument("--method", choices=["deterministic", "ml"])
    score_state = score_config.add_mutually_exclusive_group(required=True)
    score_state.add_argument("--enable", action="store_true")
    score_state.add_argument("--disable", action="store_true")
    score_config.add_argument("--selected-by")


def _register_upgrade(commands: argparse._SubParsersAction) -> None:
    """Register governed voice-upgrade planning and build commands.

    Args:
        commands (argparse._SubParsersAction): Voice subcommand collection.

    Returns:
        None: Upgrade routes are registered in place.
    """
    plan = commands.add_parser(
        "upgrade-plan",
        help="Inventory evidence and learning without changing the active voice",
    )
    plan.add_argument("voice_id")
    plan.add_argument("--mode", choices=["incremental", "full-corpus"], default="incremental")
    plan.add_argument("--provider", choices=PROVIDERS)
    plan.add_argument("--offline-analysis", action="store_true")
    upgrade = commands.add_parser(
        "upgrade",
        help="Build a reviewable next-version candidate from a persisted plan",
    )
    upgrade.add_argument("voice_id")
    upgrade.add_argument("--mode", choices=["incremental", "full-corpus"], default="incremental")
    upgrade.add_argument("--learning-selection")
    upgrade.add_argument("--change-set")
    upgrade.add_argument("--idempotency-key")
    upgrade.add_argument("--approve-provider-sharing", action="store_true")
    upgrade.add_argument("--provider", choices=PROVIDERS)
    upgrade.add_argument("--offline-analysis", action="store_true")


def _register_training(commands: argparse._SubParsersAction) -> None:
    """Register the training.

    Args:
        commands (argparse._SubParsersAction): The commands value passed to register
            training.

    Returns:
        None: The callable updates register training state and returns no value.
    """
    train = commands.add_parser("train-ml")
    train.add_argument("voice_id")
    train.add_argument("--voice-version")
    train.add_argument("--comparison-documents", action="append", required=True)
    train.add_argument("--accept-low-confidence", action="store_true")
    train.add_argument("--replace", action="store_true")


def _register_lifecycle(commands: argparse._SubParsersAction) -> None:
    """Register the lifecycle.

    Args:
        commands (argparse._SubParsersAction): The commands value passed to register
            lifecycle.

    Returns:
        None: The callable updates register lifecycle state and returns no value.
    """
    commands.add_parser("list")
    commands.add_parser("verify-all")
    approve = commands.add_parser("approve")
    approve.add_argument("voice_id")
    approve.add_argument("--approved-by", default="repository-owner")
    approve.add_argument("--override-evaluation", action="store_true")
    approve.add_argument("--reason")
    reject = commands.add_parser("reject")
    reject.add_argument("voice_id")
    reject.add_argument("--candidate-hash", required=True)
    reject.add_argument("--rejected-by", required=True)
    reject.add_argument("--reason", required=True)
    deactivate = commands.add_parser("deactivate")
    deactivate.add_argument("voice_id")
    deactivate.add_argument("--reason", required=True)
    deactivate.add_argument("--deactivated-by", default="repository-owner")
    deactivate.add_argument("--clear-default", action="store_true")
    deactivate.add_argument("--replacement-voice")
    reactivate = commands.add_parser("reactivate")
    reactivate.add_argument("voice_id")
    reactivate.add_argument("--approved-by", default="repository-owner")
    reactivate.add_argument("--reason", default="author reactivation")
    _register_withdrawal_lifecycle(commands)
    add_sources = commands.add_parser("add-sources")
    add_sources.add_argument("voice_id")
    add_sources.add_argument("--sources")
    add_sources.add_argument("--documents", action="append", default=[])
    diff = commands.add_parser("diff")
    diff.add_argument("voice_id")
    diff.add_argument("--from", dest="from_version", default="active")
    diff.add_argument("--to", dest="to_version", default="candidate")
    consolidate = commands.add_parser("consolidate-learnings")
    consolidate.add_argument("voice_id")


def _register_withdrawal_lifecycle(commands: argparse._SubParsersAction) -> None:
    """Register retirement, restoration, verification, and legacy migration routes.

    Args:
        commands (argparse._SubParsersAction): Voice subcommand collection.

    Returns:
        None: Lifecycle routes are registered in place.
    """
    retirement_plan = commands.add_parser(
        "retirement-plan", help="Inventory retirement effects without mutation"
    )
    retirement_plan.add_argument("voice_id")
    retire = commands.add_parser("retire")
    retire.add_argument("voice_id")
    retire.add_argument("--retired-by", required=True)
    retire.add_argument("--reason", required=True)
    retire.add_argument("--plan-hash", required=True)
    retire.add_argument("--clear-default", action="store_true")
    retire.add_argument("--replacement-voice")
    retire.add_argument("--candidate-disposition", choices=["retain", "reject", "abandon"])
    retire.add_argument(
        "--perspective-candidate-disposition", choices=["retain", "reject", "abandon"]
    )
    retire.add_argument("--proposal-disposition", choices=["retain", "reject", "abandon"])
    retire.add_argument("--run-disposition", choices=["abandon", "retain-exception"])
    restore_plan = commands.add_parser("restore-plan")
    restore_plan.add_argument("voice_id")
    restore = commands.add_parser("restore")
    restore.add_argument("voice_id")
    restore.add_argument("--requested-by", required=True)
    restore.add_argument("--approved-by", required=True)
    restore.add_argument("--plan-hash", required=True)
    verify_lifecycle = commands.add_parser("verify-lifecycle")
    verify_lifecycle.add_argument("voice_id")
    migrate_lifecycle = commands.add_parser("migrate-lifecycle")
    migrate_lifecycle.add_argument("voice_id")
    migrate_lifecycle.add_argument("--migrated-by", required=True)


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register the voice parser workflow.

    Args:
        subparsers (argparse._SubParsersAction): The argparse subparser collection
            receiving the command.

    Returns:
        None: The callable updates register state and returns no value.
    """
    voice = subparsers.add_parser("voice", help=argparse.SUPPRESS)
    commands = voice.add_subparsers(dest="voice_command", required=True)
    _register_onboard(commands)
    _register_create(commands)
    _register_build_and_assessment(commands)
    _register_upgrade(commands)
    _register_training(commands)
    _register_lifecycle(commands)
