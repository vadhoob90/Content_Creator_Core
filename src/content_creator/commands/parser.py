"""Compose the command-line parser from stable command families."""

from __future__ import annotations

import argparse

from ..agent_resources import STANDARD_TEMPLATE
from ..workspace import DEFAULT_CORE_REF, DEFAULT_CORE_SOURCE, DEFAULT_CORE_URL
from . import operations as operations_commands
from . import perspective as perspective_commands
from . import provider as provider_commands
from . import schema as schema_commands
from . import visual as visual_commands
from . import voice as voice_commands
from .shared import PROVIDERS, AuthorHelpFormatter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="content-creator",
        formatter_class=AuthorHelpFormatter,
    )
    parser.add_argument(
        "--root",
        "--workspace",
        dest="root",
        help="Content workspace (default: current directory)",
    )
    sub = parser.add_subparsers(
        dest="command",
        required=True,
        metavar=(
            "{start,overview,workspace,doctor,run,status,submission,publish,diagnostics,advanced}"
        ),
    )
    schema_commands.register(sub)
    operations_commands.register(sub)
    initialise = sub.add_parser("init", help=argparse.SUPPRESS)
    initialise.add_argument(
        "--agent-template",
        default=STANDARD_TEMPLATE,
        help="Packaged agent template to scaffold (default: standard)",
    )

    workspace = sub.add_parser(
        "workspace",
        help="Create a complete thin repository that consumes Content Creator Core",
    )
    workspace_sub = workspace.add_subparsers(
        dest="workspace_command",
        required=True,
    )
    workspace_create = workspace_sub.add_parser(
        "create",
        help="Scaffold a new author-owned content repository",
    )
    workspace_create.add_argument(
        "directory",
        help="Destination directory; created when it does not exist",
    )
    workspace_create.add_argument(
        "--name",
        help="Repository display name (default: destination directory name)",
    )
    workspace_create.add_argument("--author-name", required=True)
    workspace_create.add_argument("--voice-id")
    workspace_create.add_argument("--voice-label")
    workspace_create.add_argument(
        "--pack",
        action="append",
        default=[],
        help="Content pack to enable; repeat for several (default: general-text)",
    )
    workspace_create.add_argument(
        "--agent-template",
        default=STANDARD_TEMPLATE,
        help="Packaged agent template to scaffold (default: standard)",
    )
    workspace_create.add_argument(
        "--core-source",
        choices=["registry", "git"],
        default=DEFAULT_CORE_SOURCE,
        help="Install Core from the package registry (default) or Git",
    )
    workspace_create.add_argument(
        "--core-url",
        default=DEFAULT_CORE_URL,
        help="Git URL for the Content Creator Core dependency",
    )
    workspace_create.add_argument(
        "--core-ref",
        default=DEFAULT_CORE_REF,
        help="Immutable Core tag or commit to pin (default: installed version tag)",
    )
    workspace_create.add_argument(
        "--perspective-mode",
        choices=["automatic", "explicit", "disabled"],
        default="automatic",
        help="Perspective selection policy for the new workspace",
    )
    workspace_upgrade = workspace_sub.add_parser(
        "upgrade",
        help="Preview or apply an immutable Core dependency upgrade",
    )
    workspace_upgrade.add_argument(
        "--to",
        required=True,
        help="Immutable semantic version tag or full reviewed commit SHA",
    )
    workspace_upgrade.add_argument(
        "--apply",
        action="store_true",
        help="Apply the previewed dependency and lockfile update",
    )

    agents = sub.add_parser("agents", help=argparse.SUPPRESS)
    agent_sub = agents.add_subparsers(dest="agent_command", required=True)
    for command in ("scaffold", "status", "diff-template"):
        item = agent_sub.add_parser(command)
        item.add_argument(
            "--template",
            default=STANDARD_TEMPLATE,
            help="Packaged agent template (default: standard)",
        )

    provider_commands.register(sub, PROVIDERS)

    plan = sub.add_parser("plan", help=argparse.SUPPRESS)
    plan.add_argument("request")
    plan.add_argument("--provider", choices=PROVIDERS)

    start = sub.add_parser(
        "start",
        help="Inspect the workspace and guide the author to the next task",
    )
    start.add_argument("request", nargs="?")
    start.add_argument("--provider", choices=PROVIDERS)
    start.add_argument("--json", action="store_true")
    overview = sub.add_parser(
        "overview",
        help="Show workspace health, incomplete work, and the next action",
    )
    overview.add_argument("--json", action="store_true")
    overview.add_argument("--run-limit", type=int, default=5)

    sub.add_parser("doctor", help="Validate offline configuration and assets")
    sub.add_parser("packs", help=argparse.SUPPRESS)

    coordinator = sub.add_parser(
        "coordinator",
        help=argparse.SUPPRESS,
    )
    coordinator_sub = coordinator.add_subparsers(
        dest="coordinator_command",
        required=True,
    )
    coordinator_sub.add_parser("capabilities")
    coordinator_context = coordinator_sub.add_parser("context")
    coordinator_context.add_argument("--run-limit", type=int, default=10)
    coordinator_runs = coordinator_sub.add_parser("runs")
    coordinator_runs.add_argument("--limit", type=int, default=20)
    coordinator_next = coordinator_sub.add_parser("next-actions")
    coordinator_next.add_argument("run_id")

    diagnostics = sub.add_parser(
        "diagnostics",
        help="Inspect deferred runtime diagnostics",
    )
    diagnostics_sub = diagnostics.add_subparsers(dest="diagnostics_command", required=True)
    for command in ("show", "preflight"):
        item = diagnostics_sub.add_parser(command)
        item.add_argument("run_id")
    diagnostics_link = diagnostics_sub.add_parser("link-issue")
    diagnostics_link.add_argument("run_id")
    diagnostics_link.add_argument("--issue-url", required=True)

    pack = sub.add_parser("pack", help=argparse.SUPPRESS)
    pack_sub = pack.add_subparsers(dest="pack_command", required=True)
    pack_sub.add_parser("list")
    pack_show = pack_sub.add_parser("show")
    pack_show.add_argument("pack_id")
    pack_show.add_argument("--resolved", action="store_true")
    pack_validate = pack_sub.add_parser("validate")
    pack_validate.add_argument("pack_id")
    pack_create = pack_sub.add_parser("create")
    pack_create.add_argument("pack_id")
    pack_create.add_argument("--extends", default="general-text")

    voice_commands.register(sub)
    perspective_commands.register(sub)

    run = sub.add_parser("run", help="Create a run and execute its route")
    _add_run_arguments(run)

    status = sub.add_parser("status", help="Show persisted run state")
    status.add_argument("run_id")

    submission = sub.add_parser(
        "submission",
        help="Resolve an idempotent submission without executing it",
    )
    submission_sub = submission.add_subparsers(
        dest="submission_command",
        required=True,
    )
    submission_status = submission_sub.add_parser("status")
    submission_status.add_argument("idempotency_key")

    resume = sub.add_parser("approve-research", help=argparse.SUPPRESS)
    resume.add_argument("run_id")
    resume.add_argument("--notes")

    reject = sub.add_parser("reject-research", help=argparse.SUPPRESS)
    reject.add_argument("run_id")
    reject.add_argument("--notes")

    publish = sub.add_parser("publish", help="Move the reviewed output into published/")
    publish.add_argument("run_id")
    publish.add_argument("--filename")
    publish.add_argument("--feedback")
    publish.add_argument(
        "--diagnostic-decision",
        choices=["publish-only", "prepare-issue"],
    )

    visual_commands.register(sub)

    evaluate = sub.add_parser("eval", help=argparse.SUPPRESS)
    evaluate.add_argument("--mode", choices=["replay", "live"], default="replay")
    evaluate.add_argument("--providers", nargs="+", default=["anthropic", "openai"])
    sub.add_parser(
        "advanced",
        help="Show lifecycle, automation, and administration command families",
        description=(
            "Advanced command families remain stable: init, agents, provider, "
            "plan, coordinator, pack, packs, voice, perspective, "
            "approve-research, reject-research, and eval. Use "
            "'content-creator <family> --help' for detailed help."
        ),
    )
    return parser


def _add_run_arguments(parser: argparse.ArgumentParser) -> None:
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
    parser.add_argument("--provider", choices=PROVIDERS)
    parser.add_argument("--objective")
    parser.add_argument("--audience")
    parser.add_argument("--language")
    parser.add_argument("--structure")
    parser.add_argument("--destination")
    parser.add_argument("--length", help="Word range such as 700:900")
    parser.add_argument(
        "--content-session",
        help="Stable lineage id shared by revisions of the same piece",
    )
    parser.add_argument(
        "--parent-run",
        help="Prior run whose content lineage this revision continues",
    )
    parser.add_argument(
        "--idempotency-key",
        help=(
            "Stable retry key; equivalent reuse returns the existing run and "
            "conflicting reuse fails"
        ),
    )
