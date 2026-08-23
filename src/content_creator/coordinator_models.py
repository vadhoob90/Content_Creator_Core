"""Provide coordinator models capabilities."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CoordinatorAction(BaseModel):
    """Represent a coordinator action."""

    id: str
    label: str
    command: Optional[List[str]] = None
    artifact: Optional[str] = None
    mutates_workspace: bool = False
    requires_confirmation: bool = False


class ProviderStatus(BaseModel):
    """Enumerate supported provider status values."""

    name: Optional[str] = None
    status: str = "not-selected"
    detail: Optional[str] = None


class VoiceStatus(BaseModel):
    """Enumerate supported voice status values."""

    voice_id: str
    display_name: str
    active_status: Optional[str] = None
    active_version: Optional[str] = None
    candidate_status: Optional[str] = None
    candidate_decision: Optional[str] = None
    candidate_hash: Optional[str] = None
    onboarding_status: Optional[str] = None
    strategy: Optional[str] = None
    upgrade_eligible: bool = False
    new_voice_evidence_count: int = 0
    unconsolidated_learning_count: int = 0
    upgrade_plan_command: Optional[List[str]] = None


class RunSummary(BaseModel):
    """Represent a run summary."""

    run_id: str
    status: str
    topic: str
    content_pack: str
    voice_id: str
    updated_at: str
    content_session_id: Optional[str] = None
    parent_run_id: Optional[str] = None
    authoritative: bool = True
    superseded_by_run_id: Optional[str] = None
    requires_human_input: bool = False
    incomplete: bool = False


class WorkspaceSnapshot(BaseModel):
    """Represent a workspace snapshot."""

    schema_version: str = "1.1"
    workspace: str
    is_workspace: bool
    coordinator: Dict[str, Any]
    provider: Optional[str] = None
    provider_status: ProviderStatus
    packs: List[str] = Field(default_factory=list)
    voices: List[VoiceStatus] = Field(default_factory=list)
    active_voice_ids: List[str] = Field(default_factory=list)
    suggested_voice_id: Optional[str] = None
    runs: List[RunSummary] = Field(default_factory=list)
    health: Dict[str, Any]
    warnings: List[str] = Field(default_factory=list)
    recommended_action: CoordinatorAction
    personalisation_action: CoordinatorAction = Field(
        default_factory=lambda: CoordinatorAction(
            id="inspect-personalisation",
            label="Understand agents, learnings, voice, and perspectives",
            command=["personalisation", "show"],
        )
    )


def operation(
    operation_id: str,
    command: List[str],
    *,
    mutates: bool = False,
    approval: bool = False,
) -> Dict[str, Any]:
    """Return the operation name represented by coordinator models.

    Args:
        operation_id (str): The stable identifier for the operation.
        command (List[str]): The command name or invocation to execute.
        mutates (bool): Whether mutates behavior is enabled. Defaults to ``False``.
        approval (bool): Whether approval behavior is enabled. Defaults to ``False``.

    Returns:
        Dict[str, Any]: The structured resulting data for operation.
    """
    return {
        "id": operation_id,
        "command": command,
        "mutates_workspace": mutates,
        "requires_explicit_approval": approval,
    }


def action(
    action_id: str,
    label: str,
    command: Optional[List[str]] = None,
    artifact: Optional[str] = None,
    mutates: bool = False,
    confirmation: bool = False,
) -> CoordinatorAction:
    """Return the remediation action represented by coordinator models.

    Args:
        action_id (str): The stable identifier for the action.
        label (str): The label text processed when action.
        command (Optional[List[str]]): The command name or invocation to execute.
            Defaults to ``None``.
        artifact (Optional[str]): The artifact text processed when action. Defaults to
            ``None``.
        mutates (bool): Whether mutates behavior is enabled. Defaults to ``False``.
        confirmation (bool): Whether confirmation behavior is enabled. Defaults to
            ``False``.

    Returns:
        CoordinatorAction: The resulting coordinator action for action.
    """
    return CoordinatorAction(
        id=action_id,
        label=label,
        command=command,
        artifact=artifact,
        mutates_workspace=mutates,
        requires_confirmation=confirmation,
    )
