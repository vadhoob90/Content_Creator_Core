"""Implement the experience commands command family."""

from __future__ import annotations

from ..coordinator import ContentCoordinator
from ..coordinator_models import WorkspaceSnapshot
from ..experience import render_overview, render_start
from ..intake import ClarificationRequired
from .context import CommandContext


def show_overview(context: CommandContext) -> int:
    """Show the overview.

    Args:
        context (CommandContext): The operation context and its resolved dependencies.

    Returns:
        int: The resulting numeric value for show overview.
    """
    snapshot = ContentCoordinator(context.root).snapshot(context.arguments.run_limit)
    context.emit(snapshot) if context.arguments.json else print(
        render_overview(snapshot, details=context.arguments.details)
    )
    return 0


def _clarification(
    context: CommandContext,
    snapshot: WorkspaceSnapshot,
    error: ClarificationRequired,
) -> int:
    """Return the clarification.

    Args:
        context (CommandContext): The operation context and its resolved dependencies.
        snapshot (WorkspaceSnapshot): The snapshot value passed to clarification.
        error (ClarificationRequired): The error value passed to clarification.

    Returns:
        int: The resulting numeric value for clarification.
    """
    if context.arguments.json:
        context.emit(
            {
                "needs_clarification": True,
                "questions": error.questions,
                "workspace": snapshot.model_dump(mode="json"),
            }
        )
    else:
        print(
            render_start(
                snapshot,
                questions=error.questions,
                details=context.arguments.details,
            )
        )
    return 3


def start(context: CommandContext) -> int:
    """Start the experience commands workflow.

    Keep request planning read-only and project the typed setup gate into both
    human and machine output so hosts never infer execution readiness.

    Args:
        context (CommandContext): The operation context and its resolved dependencies.

    Returns:
        int: The resulting numeric value for start.
    """
    coordinator = ContentCoordinator(context.root)
    snapshot = coordinator.snapshot()
    if not context.arguments.request or not snapshot.is_workspace:
        context.emit(snapshot) if context.arguments.json else print(
            render_start(snapshot, details=context.arguments.details)
        )
        return 0
    try:
        order = context.orchestrator.plan_request(
            context.arguments.request,
            provider=context.arguments.provider,
        )
    except ClarificationRequired as error:
        return _clarification(context, snapshot, error)
    if context.arguments.json:
        context.emit(
            {
                "workspace": snapshot.model_dump(mode="json"),
                "work_order": order.model_dump(mode="json"),
                "mutates_workspace": False,
                "ready_to_run": bool(snapshot.setup and snapshot.setup.ready_for_content),
                "next_action": (
                    {
                        "id": "run-content",
                        "command": ["run", order.request],
                        "mutates_workspace": True,
                    }
                    if snapshot.setup and snapshot.setup.ready_for_content
                    else snapshot.recommended_action.model_dump(mode="json")
                ),
                "approval_points": [
                    "research checkpoint when required",
                    "final author review",
                    "repository-local publication",
                ],
            }
        )
    else:
        print(render_start(snapshot, order=order, details=context.arguments.details))
    return 0


def plan(context: CommandContext) -> int:
    """Plan the experience commands workflow.

    Args:
        context (CommandContext): The operation context and its resolved dependencies.

    Returns:
        int: The planned numeric value for value.
    """
    try:
        context.emit(
            context.orchestrator.plan_request(
                context.arguments.request,
                provider=context.arguments.provider,
            )
        )
        return 0
    except ClarificationRequired as error:
        context.emit({"needs_clarification": True, "questions": error.questions})
        return 3
