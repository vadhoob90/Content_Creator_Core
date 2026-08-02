"""Run-state, diagnostics, research, submission, and publication handlers."""

from __future__ import annotations

from .context import CommandContext


def inspect_diagnostics(context: CommandContext) -> int:
    arguments = context.arguments
    if arguments.diagnostics_command in {"show", "preflight"}:
        context.emit(context.orchestrator.diagnostic_preflight(arguments.run_id))
        return 0
    if not arguments.issue_url.startswith(("https://github.com/", "https://www.github.com/")):
        raise ValueError("--issue-url must be a GitHub HTTPS URL")
    context.emit(context.orchestrator.link_diagnostic_issue(arguments.run_id, arguments.issue_url))
    return 0


def show_status(context: CommandContext) -> int:
    context.emit(context.orchestrator.store.load(context.arguments.run_id))
    return 0


def show_submission(context: CommandContext) -> int:
    state = context.orchestrator.store.load_by_idempotency_key(context.arguments.idempotency_key)
    if state is None:
        raise ValueError("Unknown idempotency key")
    context.emit(state)
    return 0


def approve_research(context: CommandContext) -> int:
    context.emit(
        context.orchestrator.resume_research(
            context.arguments.run_id,
            True,
            notes=context.arguments.notes,
        )
    )
    return 0


def reject_research(context: CommandContext) -> int:
    context.emit(
        context.orchestrator.resume_research(
            context.arguments.run_id,
            False,
            notes=context.arguments.notes,
        )
    )
    return 0


def publish(context: CommandContext) -> int:
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
