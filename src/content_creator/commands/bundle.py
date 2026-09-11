"""Register and execute provider-free draft bundle operations."""

from typing import Any

from ..draft_bundles.service import DraftBundleWorkflow
from ..storage import StorageError
from .context import CommandContext


def register(subparsers: Any) -> None:
    """Register pinned membership and non-publishing draft export commands.

    Args:
        subparsers (Any): Top-level CLI command collection.

    Returns:
        None: Parsers are registered.
    """
    bundle = subparsers.add_parser("bundle", help="Manage pinned drafts for review")
    actions = bundle.add_subparsers(dest="bundle_action", required=True)
    for action in ("create", "add", "update", "remove", "show", "review", "export"):
        parser = actions.add_parser(action)
        parser.add_argument("bundle_id")
        if action == "create":
            parser.add_argument("--title", required=True)
        if action in {"add", "update", "remove"}:
            parser.add_argument("name")
        if action == "add":
            parser.add_argument("run_id")
        if action == "update":
            parser.add_argument("--run-id")
        if action == "export":
            parser.add_argument("destination")
            parser.add_argument("--preview", action="store_true")
    export = subparsers.add_parser("export-draft", help="Export one run for draft review")
    export.add_argument("run_id")
    export.add_argument("destination")
    export.add_argument("--preview", action="store_true")


def run(context: CommandContext) -> int:
    """Execute the draft bundle application boundary and render its result.

    Args:
        context (CommandContext): Parsed command and workspace.

    Returns:
        int: Zero after a successful operation.

    Raises:
        StorageError: If the supplied operation has invalid input or cannot write output.
    """
    args = context.arguments
    workflow = DraftBundleWorkflow(context.root)
    try:
        if args.command == "export-draft":
            result = workflow.export_run(args.run_id, args.destination, args.preview)
        elif args.bundle_action == "create":
            result = workflow.create(args.bundle_id, args.title)
        elif args.bundle_action == "add":
            result = workflow.add(args.bundle_id, args.name, args.run_id)
        elif args.bundle_action == "update":
            result = workflow.update(args.bundle_id, args.name, args.run_id)
        elif args.bundle_action == "remove":
            result = workflow.remove(args.bundle_id, args.name)
        elif args.bundle_action == "show":
            result = workflow.show(args.bundle_id)
        elif args.bundle_action == "review":
            result = workflow.review(args.bundle_id)
        else:
            result = workflow.export(args.bundle_id, args.destination, args.preview)
    except (OSError, ValueError) as exc:
        raise StorageError(f"Invalid draft bundle operation: {exc}") from exc
    context.emit(result)
    return 0
