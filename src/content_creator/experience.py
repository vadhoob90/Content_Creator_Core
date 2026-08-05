"""Provide experience capabilities."""

from __future__ import annotations

from typing import Iterable, Optional

from .coordinator import CoordinatorAction, WorkspaceSnapshot
from .domain import WorkOrder


def render_overview(snapshot: WorkspaceSnapshot) -> str:
    """Render the overview.

    Args:
        snapshot (WorkspaceSnapshot): The snapshot value passed to render overview.

    Returns:
        str: The rendered text for overview.
    """
    active = [
        "{} ({})".format(voice.display_name, voice.active_version or "unversioned")
        for voice in snapshot.voices
        if voice.active_status == "active"
    ]
    pending = [
        voice.display_name
        for voice in snapshot.voices
        if voice.onboarding_status == "undecided" or voice.candidate_status
    ]
    lines = [
        "Content Creator workspace",
        "Workspace: {}".format(snapshot.workspace),
        "Active voice: {}".format(", ".join(active) if active else "none"),
        "Pending voice decisions: {}".format(", ".join(pending) if pending else "none"),
        "Default pack: {}".format(snapshot.coordinator["default_pack"]),
        "Provider: {} ({})".format(
            snapshot.provider_status.name or "not selected",
            snapshot.provider_status.status,
        ),
        "Workspace health: {}".format(snapshot.health["status"]),
    ]
    if snapshot.runs:
        lines.append("Recent runs:")
        lines.extend(
            "  - {}: {} — {}".format(run.run_id, run.status, run.topic) for run in snapshot.runs
        )
    else:
        lines.append("Recent runs: none")
    if snapshot.warnings:
        lines.append("Warnings:")
        lines.extend("  - {}".format(warning) for warning in snapshot.warnings)
    lines.append("Recommended next action: {}".format(snapshot.recommended_action.label))
    command = _render_action_command(snapshot.recommended_action)
    if command:
        lines.append(command)
    return "\n".join(lines)


def render_start(
    snapshot: WorkspaceSnapshot,
    order: Optional[WorkOrder] = None,
    questions: Optional[Iterable[str]] = None,
) -> str:
    """Render the start.

    Args:
        snapshot (WorkspaceSnapshot): The snapshot value passed to render start.
        order (Optional[WorkOrder]): The work order that defines the requested content
            run. Defaults to ``None``.
        questions (Optional[Iterable[str]]): The questions value passed to render start.
            Defaults to ``None``.

    Returns:
        str: The rendered text for start.
    """
    if questions:
        return "\n".join(
            ["More information is needed:"] + ["  - {}".format(question) for question in questions]
        )
    if order is None:
        command = _render_action_command(snapshot.recommended_action)
        return "\n".join(line for line in [snapshot.recommended_action.label, command] if line)
    lines = [
        "Proposed content plan",
        "Topic: {}".format(order.topic),
        "Voice: {}".format(order.voice_id),
        "Format and pack: {} / {}".format(order.format, order.content_pack),
        "Research route: {} / {}".format(
            order.research_depth.value,
            order.research_source.value,
        ),
        "Perspective: {}".format(
            order.perspective_context or "Core will resolve from workspace policy"
        ),
        "Approval points: research checkpoint when required; final author review; "
        "repository-local publication",
        "Next command: content-creator run {!r}".format(order.request),
    ]
    if snapshot.warnings:
        lines.append("Warnings:")
        lines.extend("  - {}".format(warning) for warning in snapshot.warnings)
    return "\n".join(lines)


def _render_action_command(action: CoordinatorAction) -> str:
    """Render the action command.

    Args:
        action (CoordinatorAction): The action value passed to render action command.

    Returns:
        str: The rendered text for action command.
    """
    if not action.command:
        return ""
    return "Command: content-creator {}".format(" ".join(action.command))
