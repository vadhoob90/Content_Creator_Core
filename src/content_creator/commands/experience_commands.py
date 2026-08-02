"""Author-facing workspace overview, start, and planning commands."""

from __future__ import annotations

from ..coordinator import ContentCoordinator
from ..coordinator_models import WorkspaceSnapshot
from ..experience import render_overview, render_start
from ..intake import ClarificationRequired
from .context import CommandContext


def show_overview(context: CommandContext) -> int:
    snapshot = ContentCoordinator(context.root).snapshot(context.arguments.run_limit)
    context.emit(snapshot) if context.arguments.json else print(render_overview(snapshot))
    return 0


def _clarification(
    context: CommandContext,
    snapshot: WorkspaceSnapshot,
    error: ClarificationRequired,
) -> int:
    if context.arguments.json:
        context.emit(
            {
                "needs_clarification": True,
                "questions": error.questions,
                "workspace": snapshot.model_dump(mode="json"),
            }
        )
    else:
        print(render_start(snapshot, questions=error.questions))
    return 3


def start(context: CommandContext) -> int:
    coordinator = ContentCoordinator(context.root)
    snapshot = coordinator.snapshot()
    if not context.arguments.request or not snapshot.is_workspace:
        context.emit(snapshot) if context.arguments.json else print(render_start(snapshot))
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
                "approval_points": [
                    "research checkpoint when required",
                    "final author review",
                    "repository-local publication",
                ],
            }
        )
    else:
        print(render_start(snapshot, order=order))
    return 0


def plan(context: CommandContext) -> int:
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
