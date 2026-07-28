from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ResearchDepth(str, Enum):
    NONE = "none"
    LIGHT = "light"
    DEEP = "deep"


class ResearchSource(str, Enum):
    NONE = "none"
    SUPPLIED = "supplied"
    AGENT = "agent"


class RunStatus(str, Enum):
    PLANNED = "planned"
    RESEARCHING = "researching"
    AWAITING_RESEARCH_APPROVAL = "awaiting_research_approval"
    DRAFTING = "drafting"
    REVIEWING = "reviewing"
    READY = "ready"
    NEEDS_AUTHOR = "needs_author"
    FAILED = "failed"
    PUBLISHED = "published"


class IssueSeverity(str, Enum):
    BLOCKING = "blocking"
    SUBSTANTIVE = "substantive"
    MINOR = "minor"


class LearningStatus(str, Enum):
    ACTIVE = "active"
    PROVISIONAL = "provisional"
    REJECTED = "rejected"


class AuthorContribution(BaseModel):
    thesis: Optional[str] = None
    intended_challenge: Optional[str] = None
    personal_basis: Optional[str] = None
    supplied_by_author: bool = False
    reusable_perspective_entry_ids: List[str] = Field(default_factory=list)
    provenance_notes: List[str] = Field(default_factory=list)


class WorkOrder(BaseModel):
    request: str
    topic: str
    content_pack: str = "general-text"
    voice_id: str = "default"
    voice_version: Optional[str] = None
    resolved_voice: bool = False
    perspective_context: Optional[str] = None
    perspective_version: Optional[str] = None
    resolved_perspective: bool = False
    author_contribution: Optional[AuthorContribution] = None
    format: str = "text"
    research_depth: ResearchDepth = ResearchDepth.NONE
    research_source: ResearchSource = ResearchSource.NONE
    audience: str = "professional audience"
    objective: str = "share a useful perspective"
    angle: Optional[str] = None
    constraints: List[str] = Field(default_factory=list)
    supplied_research_path: Optional[str] = None
    provider: Optional[str] = None
    pack_options: Dict[str, object] = Field(default_factory=dict)

    @field_validator("content_pack", "voice_id", "perspective_context")
    @classmethod
    def validate_repository_id(cls, value):
        if value is not None and not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", value):
            raise ValueError("Repository ids must use lowercase letters, digits, and hyphens")
        return value

    @model_validator(mode="after")
    def validate_perspective_selection(self):
        if self.perspective_version and not self.perspective_context:
            raise ValueError("perspective_version requires perspective_context")
        selected = (
            self.author_contribution.reusable_perspective_entry_ids
            if self.author_contribution
            else []
        )
        if selected and not self.perspective_context:
            raise ValueError(
                "reusable perspective entries require perspective_context"
            )
        return self

class PlanningDecision(BaseModel):
    needs_clarification: bool = False
    clarification_questions: List[str] = Field(default_factory=list)
    work_order: Optional[WorkOrder] = None
    rationale: str = ""


class RoutePlan(BaseModel):
    route: str
    stages: List[str]
    requires_research_checkpoint: bool = False
    model_profiles: Dict[str, str] = Field(default_factory=dict)


class Source(BaseModel):
    title: str
    url: str
    publisher: Optional[str] = None
    date: Optional[str] = None


class EvidenceItem(BaseModel):
    claim: str
    source_urls: List[str] = Field(default_factory=list)
    confidence: str = "medium"
    notes: Optional[str] = None


class ResearchBrief(BaseModel):
    summary: str
    evidence: List[EvidenceItem] = Field(default_factory=list)
    sources: List[Source] = Field(default_factory=list)
    tensions: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)


class CritiqueIssue(BaseModel):
    dimension: str
    severity: IssueSeverity
    description: str
    requested_change: str
    evidence: Optional[str] = None


class Critique(BaseModel):
    scores: Dict[str, float]
    weighted_score: float = 0.0
    issues: List[CritiqueIssue] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    prior_issue_status: Dict[str, str] = Field(default_factory=dict)
    summary: str = ""


class QualityDecision(BaseModel):
    passed: bool
    weighted_score: float
    minimum_score: float
    minor_issue_count: int
    reasons: List[str] = Field(default_factory=list)


class LearningCandidate(BaseModel):
    role: str
    scope: str = "general"
    principle: str
    evidence: str
    status: LearningStatus
    confidence: float = Field(ge=0, le=1)
    source_event: str = "publication"
    supersedes: Optional[str] = None
    conflicts_with: List[str] = Field(default_factory=list)


class LearningExtraction(BaseModel):
    candidates: List[LearningCandidate] = Field(default_factory=list)
    author_signal: str = "implicit_publication_approval"


class LearningRecord(LearningCandidate):
    id: str = Field(default_factory=lambda: uuid4().hex)
    run_id: str
    voice_id: str = "default"
    voice_version: Optional[str] = None
    content_pack: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)


class ModelSelection(BaseModel):
    provider: str
    profile: str
    model: str
    reasoning_effort: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)


class ModelRequest(BaseModel):
    role: str
    system: str
    user: str
    selection: ModelSelection
    max_output_tokens: int = 6000
    output_schema: Optional[Dict] = None
    tools: List[str] = Field(default_factory=list)


class ModelResponse(BaseModel):
    text: str
    provider: str
    model: str
    raw_id: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


class RunEvent(BaseModel):
    at: datetime = Field(default_factory=utc_now)
    name: str
    detail: str = ""


class RunState(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    status: RunStatus = RunStatus.PLANNED
    work_order: WorkOrder
    route_plan: RoutePlan
    revision: int = 0
    final_draft_path: Optional[str] = None
    published_path: Optional[str] = None
    last_error: Optional[str] = None
    events: List[RunEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
