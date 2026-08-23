"""Define semantic change contracts for immutable voice evolution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from .voice_models import VoicePattern


class VoiceEvolutionAction(str, Enum):
    """Enumerate supported semantic voice-change classifications."""

    RETAIN = "retain"
    ADD = "add"
    MODIFY = "modify"
    SUPERSEDE = "supersede"
    REMOVE = "remove"


class VoiceEvolutionProposal(BaseModel):
    """Represent one explicit evidence-backed voice change proposal."""

    action: VoiceEvolutionAction
    target_id: Optional[str] = None
    replacement: Optional[VoicePattern] = None
    evidence_source_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0, le=1)
    rationale: str


class VoiceEvolutionChangeSet(BaseModel):
    """Represent author-supplied proposals applied to an active baseline."""

    schema_version: str = "1.0"
    changes: list[VoiceEvolutionProposal] = Field(default_factory=list)


class VoiceEvolutionRecord(BaseModel):
    """Record one deterministic semantic difference from active guidance."""

    guidance_id: str
    replacement_id: Optional[str] = None
    provenance: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    rationale: str


class VoiceEvolutionDelta(BaseModel):
    """Persist a deterministic active-to-candidate semantic delta."""

    schema_version: str = "1.0"
    mode: str
    baseline_version: str
    baseline_candidate_hash: str
    baseline_manifest_hash: str
    generated_evidence_hash: str
    change_set_hash: Optional[str] = None
    retained: list[VoiceEvolutionRecord] = Field(default_factory=list)
    added: list[VoiceEvolutionRecord] = Field(default_factory=list)
    modified: list[VoiceEvolutionRecord] = Field(default_factory=list)
    superseded: list[VoiceEvolutionRecord] = Field(default_factory=list)
    removed: list[VoiceEvolutionRecord] = Field(default_factory=list)


@dataclass
class EvolutionResult:
    """Return merged artifacts needed by the remaining build pipeline."""

    profile: str
    constraints: dict[str, Any]
    rubric: dict[str, Any]
    patterns: list[VoicePattern]
