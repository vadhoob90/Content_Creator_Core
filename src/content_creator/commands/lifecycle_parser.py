"""Register coordinator, pack, diagnostics, and lifecycle command arguments."""

from __future__ import annotations

import argparse

from .shared import PROVIDERS


def register_coordinator(subparsers: argparse._SubParsersAction) -> None:
    """Register the coordinator.

    Args:
        subparsers (argparse._SubParsersAction): The argparse subparser collection
            receiving the command.

    Returns:
        None: The callable updates register coordinator state and returns no value.
    """
    coordinator = subparsers.add_parser("coordinator", help=argparse.SUPPRESS)
    commands = coordinator.add_subparsers(dest="coordinator_command", required=True)
    commands.add_parser("capabilities")
    context = commands.add_parser("context")
    context.add_argument("--run-limit", type=int, default=10)
    runs = commands.add_parser("runs")
    runs.add_argument("--limit", type=int, default=20)
    next_actions = commands.add_parser("next-actions")
    next_actions.add_argument("run_id")


def register_diagnostics(subparsers: argparse._SubParsersAction) -> None:
    """Register the diagnostics.

    Args:
        subparsers (argparse._SubParsersAction): The argparse subparser collection
            receiving the command.

    Returns:
        None: The callable updates register diagnostics state and returns no value.
    """
    diagnostics = subparsers.add_parser("diagnostics", help="Inspect deferred diagnostics")
    commands = diagnostics.add_subparsers(dest="diagnostics_command", required=True)
    for command_name in ("show", "preflight"):
        command = commands.add_parser(command_name)
        command.add_argument("run_id")
    link_issue = commands.add_parser("link-issue")
    link_issue.add_argument("run_id")
    link_issue.add_argument("--issue-url", required=True)


def register_packs(subparsers: argparse._SubParsersAction) -> None:
    """Register the packs.

    Args:
        subparsers (argparse._SubParsersAction): The argparse subparser collection
            receiving the command.

    Returns:
        None: The callable updates register packs state and returns no value.
    """
    subparsers.add_parser("packs", help=argparse.SUPPRESS)
    pack = subparsers.add_parser("pack", help=argparse.SUPPRESS)
    commands = pack.add_subparsers(dest="pack_command", required=True)
    commands.add_parser("list")
    show = commands.add_parser("show")
    show.add_argument("pack_id")
    show.add_argument("--resolved", action="store_true")
    validate = commands.add_parser("validate")
    validate.add_argument("pack_id")
    create = commands.add_parser("create")
    create.add_argument("pack_id")
    create.add_argument("--extends", default="general-text")


def register_run(subparsers: argparse._SubParsersAction) -> None:
    """Register the run.

    Args:
        subparsers (argparse._SubParsersAction): The argparse subparser collection
            receiving the command.

    Returns:
        None: The callable updates register run state and returns no value.
    """
    run = subparsers.add_parser("run", help="Create a run and execute its route")
    _add_run_arguments(run)
    status = subparsers.add_parser("status", help="Show persisted run state")
    status.add_argument("run_id")
    submission = subparsers.add_parser("submission", help="Resolve an idempotent submission")
    submission_commands = submission.add_subparsers(dest="submission_command", required=True)
    submission_status = submission_commands.add_parser("status")
    submission_status.add_argument("idempotency_key")


def _add_run_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the run arguments.

    Args:
        parser (argparse.ArgumentParser): The parser value passed to add run arguments.

    Returns:
        None: The callable updates add run arguments state and returns no value.
    """
    parser.add_argument("request", nargs="?")
    parser.add_argument("--brief", help="JSON or YAML content brief")
    parser.add_argument("--topic")
    parser.add_argument("--pack")
    parser.add_argument("--voice", default="default")
    parser.add_argument("--voice-version")
    parser.add_argument("--perspective-context", action="append", default=[])
    parser.add_argument("--perspective-version")
    parser.add_argument("--no-perspective", action="store_true")
    parser.add_argument("--thesis")
    parser.add_argument("--intended-challenge")
    parser.add_argument("--personal-basis")
    parser.add_argument("--author-supplied", action="store_true")
    parser.add_argument("--perspective-entry", action="append", default=[])
    parser.add_argument("--format", choices=["text", "post", "article"])
    parser.add_argument("--research", choices=["none", "light", "deep"])
    parser.add_argument("--research-source", choices=["none", "supplied", "agent"])
    parser.add_argument("--research-file")
    parser.add_argument(
        "--citation-style",
        choices=["inline-links", "numbered-references"],
        help="Citation presentation for research-backed output",
    )
    parser.add_argument("--provider", choices=PROVIDERS)
    parser.add_argument("--objective")
    parser.add_argument("--audience")
    parser.add_argument("--language")
    parser.add_argument("--structure")
    parser.add_argument("--destination")
    parser.add_argument("--length", help="Word range such as 700:900")
    parser.add_argument("--content-session")
    parser.add_argument("--parent-run")
    parser.add_argument("--idempotency-key")
    parser.add_argument(
        "--show-context",
        action="store_true",
        help="Trace loaded and skipped context sources on stderr",
    )


def register_publication(subparsers: argparse._SubParsersAction) -> None:
    """Register publication, approval, learning, and verification commands.

    Keep the publication boundary options together so review and provenance controls
    remain visible alongside the destination-writing command.

    Args:
        subparsers (argparse._SubParsersAction): The argparse subparser collection
            receiving the command.

    Returns:
        None: The callable updates register publication state and returns no value.
    """
    for command_name in ("approve-research", "reject-research"):
        command = subparsers.add_parser(command_name, help=argparse.SUPPRESS)
        command.add_argument("run_id")
        command.add_argument("--notes")
    publish = subparsers.add_parser("publish", help="Move reviewed output into published/")
    publish.add_argument("run_id")
    publish.add_argument("--filename")
    publish.add_argument("--feedback")
    publish.add_argument("--diagnostic-decision", choices=["publish-only", "prepare-issue"])
    publish.add_argument(
        "--perspective-review-approved-by",
        help="Record the author reviewer resolving persisted semantic findings",
    )
    publish.add_argument("--perspective-review-notes")
    learn = subparsers.add_parser(
        "learn", help="Apply explicit author feedback without publishing content"
    )
    learn.add_argument("run_id")
    learn.add_argument("--feedback", required=True)
    learn.add_argument("--idempotency-key")
    verify = subparsers.add_parser(
        "verify-publications",
        help="Verify tracked publication provenance receipts",
    )
    verify.add_argument(
        "--write-baseline",
        action="store_true",
        help="Record current unreceipted publications as legacy content",
    )
    verify.add_argument(
        "--replace-baseline",
        action="store_true",
        help="Replace an existing legacy baseline",
    )
    revise = subparsers.add_parser(
        "revise", help="Revise a reviewed run in place and refresh its quality metadata"
    )
    revise.add_argument("run_id")
    revise.add_argument("--feedback", required=True)
    revise.add_argument(
        "--draft-file",
        help="Author-edited Markdown; omit to ask the configured writer to revise",
    )
    revise.add_argument("--idempotency-key")


def register_evaluation(subparsers: argparse._SubParsersAction) -> None:
    """Register the evaluation.

    Args:
        subparsers (argparse._SubParsersAction): The argparse subparser collection
            receiving the command.

    Returns:
        None: The callable updates register evaluation state and returns no value.
    """
    evaluate = subparsers.add_parser("eval", help=argparse.SUPPRESS)
    evaluate.add_argument("--mode", choices=["replay", "live"], default="replay")
    evaluate.add_argument("--providers", nargs="+", default=["anthropic", "openai"])
    subparsers.add_parser(
        "advanced",
        help="Show lifecycle, automation, and administration command families",
    )
