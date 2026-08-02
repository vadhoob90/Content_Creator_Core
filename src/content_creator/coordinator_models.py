from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CoordinatorAction(BaseModel):
    id: str
    label: str
    command: Optional[List[str]] = None
    artifact: Optional[str] = None
    mutates_workspace: bool = False
    requires_confirmation: bool = False


class ProviderStatus(BaseModel):
    name: Optional[str] = None
    status: str = "not-selected"
    detail: Optional[str] = None


class VoiceStatus(BaseModel):
    voice_id: str
    display_name: str
    active_status: Optional[str] = None
    active_version: Optional[str] = None
    candidate_status: Optional[str] = None
    onboarding_status: Optional[str] = None
    strategy: Optional[str] = None


class RunSummary(BaseModel):
    run_id: str
    status: str
    topic: str
    content_pack: str
    voice_id: str
    updated_at: str
    requires_human_input: bool = False
    incomplete: bool = False


class WorkspaceSnapshot(BaseModel):
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


def operation(
    operation_id: str,
    command: List[str],
    *,
    mutates: bool = False,
    approval: bool = False,
) -> Dict[str, Any]:
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
    return CoordinatorAction(
        id=action_id,
        label=label,
        command=command,
        artifact=artifact,
        mutates_workspace=mutates,
        requires_confirmation=confirmation,
    )
