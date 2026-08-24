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
    author_name: Optional[str] = None
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
    lifecycle_reason: Optional[str] = None
    lifecycle_decided_at: Optional[str] = None
    valid_actions: List[str] = Field(default_factory=list)
    retirement_plan_command: Optional[List[str]] = None


class SetupMilestone(BaseModel):
    """Represent one author-facing first-run milestone."""

    id: str
    label: str
    status: str
    summary: str


class FirstRunSetup(BaseModel):
    """Represent the derived journey from workspace creation to first draft."""

    schema_version: str = "1.0"
    completed_count: int
    total_count: int = 4
    ready_for_content: bool
    milestones: List[SetupMilestone]
    recommended_action: CoordinatorAction
    choices: List[CoordinatorAction] = Field(default_factory=list)


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
    setup: Optional[FirstRunSetup] = None
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


def voice_lifecycle_operations() -> list[Dict[str, Any]]:
    """Return coordinator contracts for graceful voice withdrawal and restoration.

    Returns:
        list[Dict[str, Any]]: Structured coordinator operation contracts.
    """
    return [
        operation("voice.retirement-plan", ["voice", "retirement-plan", "<voice-id>"]),
        operation(
            "voice.deactivate",
            ["voice", "deactivate", "<voice-id>"],
            mutates=True,
            approval=True,
        ),
        operation(
            "voice.reactivate",
            ["voice", "reactivate", "<voice-id>"],
            mutates=True,
            approval=True,
        ),
        operation(
            "voice.retire",
            ["voice", "retire", "<voice-id>", "--plan-hash", "<hash>"],
            mutates=True,
            approval=True,
        ),
        operation(
            "voice.restore",
            ["voice", "restore", "<voice-id>", "--plan-hash", "<hash>"],
            mutates=True,
            approval=True,
        ),
    ]


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
