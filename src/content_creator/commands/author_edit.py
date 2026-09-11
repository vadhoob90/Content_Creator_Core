"""Register and execute provider-free author-edit operations."""

from pathlib import Path
from typing import Any

from ..author_edits import AuthorEditWorkflow
from ..domain import ResearchBrief
from ..edit_contracts import AuthorEditRequest, ClaimReviewDecision
from ..storage import StorageError
from .context import CommandContext


def register(subparsers: Any) -> None:
    """Register adoption, exact-hash claim approval, and recovery commands.

    Args:
        subparsers (Any): Top-level CLI command collection.

    Returns:
        None: Command parsers are registered.
    """
    adopt = subparsers.add_parser("adopt-edit", help="Adopt author edits without model rewriting")
    adopt.add_argument("run_id")
    adopt.add_argument("--draft-file", required=True)
    adopt.add_argument("--expected-sha256", required=True)
    adopt.add_argument("--idempotency-key", required=True)
    adopt.add_argument("--baseline-file")
    adopt.add_argument("--research-file")
    review = subparsers.add_parser(
        "approve-edit-claims", help="Approve reviewed draft and research hashes"
    )
    review.add_argument("run_id")
    review.add_argument("--draft-sha256", required=True)
    review.add_argument("--research-sha256")
    review.add_argument("--approved-by", required=True)
    review.add_argument("--notes", required=True)
    recover = subparsers.add_parser("recover-edit", help="Restore the pre-edit recovery journal")
    recover.add_argument("run_id")


def run(context: CommandContext) -> int:
    """Execute the author-edit application boundary and render its structured state.

    Args:
        context (CommandContext): Parsed command and workspace.

    Returns:
        int: Zero after a handled adoption, review, or recovery.

    Raises:
        StorageError: If supplied files or typed arguments are invalid.
    """
    args = context.arguments
    workflow = AuthorEditWorkflow(context.root)
    try:
        if args.command == "adopt-edit":
            request = AuthorEditRequest(
                draft=_read(args.draft_file),
                expected_sha256=args.expected_sha256,
                idempotency_key=args.idempotency_key,
                baseline=_read(args.baseline_file) if args.baseline_file else None,
                research=ResearchBrief.model_validate_json(_read(args.research_file))
                if args.research_file
                else None,
            )
            result = workflow.adopt(args.run_id, request)
        elif args.command == "approve-edit-claims":
            result = workflow.approve_claims(
                args.run_id,
                ClaimReviewDecision(
                    draft_sha256=args.draft_sha256,
                    research_sha256=args.research_sha256,
                    approved_by=args.approved_by,
                    notes=args.notes,
                ),
            )
        else:
            result = workflow.recover(args.run_id)
    except (OSError, ValueError) as exc:
        raise StorageError(f"Invalid author-edit input: {exc}") from exc
    context.emit(result)
    return 0


def _read(filename: str) -> str:
    """Read exact UTF-8 input without translating newline sequences.

    Args:
        filename (str): Explicitly selected input path.

    Returns:
        str: Exact decoded author content.
    """
    return Path(filename).read_bytes().decode("utf-8")
