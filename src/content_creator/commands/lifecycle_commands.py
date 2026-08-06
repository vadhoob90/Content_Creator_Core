"""Implement the lifecycle commands command family."""

from __future__ import annotations

from pathlib import Path

from .context import CommandContext


def inspect_diagnostics(context: CommandContext) -> int:
    """Inspect the diagnostics.

    Args:
        context (CommandContext): The operation context and its resolved dependencies.

    Returns:
        int: The inspection numeric value for diagnostics.

    Raises:
        ValueError: If an input value violates the supported domain constraints.
    """
    arguments = context.arguments
    if arguments.diagnostics_command in {"show", "preflight"}:
        context.emit(context.orchestrator.diagnostic_preflight(arguments.run_id))
        return 0
    if not arguments.issue_url.startswith(("https://github.com/", "https://www.github.com/")):
        raise ValueError("--issue-url must be a GitHub HTTPS URL")
    context.emit(context.orchestrator.link_diagnostic_issue(arguments.run_id, arguments.issue_url))
    return 0


def show_status(context: CommandContext) -> int:
    """Show the status.

    Args:
        context (CommandContext): The operation context and its resolved dependencies.

    Returns:
        int: The resulting numeric value for show status.
    """
    context.emit(context.orchestrator.store.load(context.arguments.run_id))
    return 0


def show_submission(context: CommandContext) -> int:
    """Show the submission.

    Args:
        context (CommandContext): The operation context and its resolved dependencies.

    Returns:
        int: The resulting numeric value for show submission.

    Raises:
        ValueError: If an input value violates the supported domain constraints.
    """
    state = context.orchestrator.store.load_by_idempotency_key(context.arguments.idempotency_key)
    if state is None:
        raise ValueError("Unknown idempotency key")
    context.emit(state)
    return 0


def approve_research(context: CommandContext) -> int:
    """Approve the research.

    Args:
        context (CommandContext): The operation context and its resolved dependencies.

    Returns:
        int: The resulting numeric value for approve research.
    """
    context.emit(
        context.orchestrator.resume_research(
            context.arguments.run_id,
            True,
            notes=context.arguments.notes,
        )
    )
    return 0


def reject_research(context: CommandContext) -> int:
    """Reject the research.

    Args:
        context (CommandContext): The operation context and its resolved dependencies.

    Returns:
        int: The resulting numeric value for reject research.
    """
    context.emit(
        context.orchestrator.resume_research(
            context.arguments.run_id,
            False,
            notes=context.arguments.notes,
        )
    )
    return 0


def publish(context: CommandContext) -> int:
    """Publish the lifecycle commands workflow.

    Args:
        context (CommandContext): The operation context and its resolved dependencies.

    Returns:
        int: The resulting numeric value for publish.
    """
    arguments = context.arguments
    context.emit(
        context.orchestrator.publish(
            arguments.run_id,
            filename=arguments.filename,
            feedback=arguments.feedback,
            diagnostic_decision=arguments.diagnostic_decision,
        )
    )
    return 0


def revise(context: CommandContext) -> int:
    """Run a traceable revision against an existing reviewed draft.

    Args:
        context (CommandContext): The operation context and its resolved dependencies.

    Returns:
        int: The process exit status, where zero indicates a handled revision.

    Raises:
        ValueError: If the supplied author draft cannot be read.
    """
    arguments = context.arguments
    draft = None
    if arguments.draft_file:
        try:
            draft = Path(arguments.draft_file).read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError("--draft-file could not be read") from exc
    context.emit(
        context.orchestrator.revise(
            arguments.run_id,
            feedback=arguments.feedback,
            draft=draft,
            idempotency_key=arguments.idempotency_key,
        )
    )
    return 0
