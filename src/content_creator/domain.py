from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class ResearchDepth(str, Enum):
    NONE = "none"
    LIGHT = "light"
    DEEP = "deep"


class ResearchSource(str, Enum):
    NONE = "none"
    SUPPLIED = "supplied"
    AGENT = "agent"


class PerspectiveMode(str, Enum):
    EXPLICIT = "explicit"
    AUTOMATIC = "automatic"
    DISABLED = "disabled"


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


class PriorIssueDisposition(str, Enum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    AUTHOR_REJECTED = "author_rejected"


class LearningStatus(str, Enum):
    ACTIVE = "active"
    PROVISIONAL = "provisional"
    REJECTED = "rejected"


class LearningRole(str, Enum):
    RESEARCHER = "researcher"
    WRITER = "writer"
    CRITIC = "critic"


class AuthorContribution(BaseModel):
    thesis: Optional[str] = None
    intended_challenge: Optional[str] = None
    personal_basis: Optional[str] = None
    supplied_by_author: bool = False
    reusable_perspective_entry_ids: List[str] = Field(default_factory=list)
    provenance_notes: List[str] = Field(default_factory=list)


class PerspectiveSelection(BaseModel):
    context_id: str
    version: Optional[str] = None
    reason: str = "explicitly selected"
    confidence: float = Field(default=1.0, ge=0, le=1)

    @field_validator("context_id")
    @classmethod
    def validate_context_id(cls, value):
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", value):
            raise ValueError(
                "Perspective context ids must use lowercase letters, digits, and hyphens"
            )
        return value


class WorkOrder(BaseModel):
    request: str
    topic: str
    content_session_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    parent_run_id: Optional[str] = None
    content_pack: str = "general-text"
    voice_id: str = "default"
    voice_version: Optional[str] = None
    resolved_voice: bool = False
    perspective_context: Optional[str] = None
    perspective_version: Optional[str] = None
    resolved_perspective: bool = False
    perspective_mode: Optional[PerspectiveMode] = None
    perspective_selections: List[PerspectiveSelection] = Field(default_factory=list)
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

    @field_validator("content_session_id", "parent_run_id")
    @classmethod
    def validate_run_reference(cls, value):
        if value is not None and not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", value):
            raise ValueError(
                "Run and content session ids must use letters, digits, underscores, and hyphens"
            )
        return value

    @model_validator(mode="after")
    def validate_perspective_selection(self):
        if self.perspective_context and not self.perspective_selections:
            self.perspective_selections = [
                PerspectiveSelection(
                    context_id=self.perspective_context,
                    version=self.perspective_version,
                )
            ]
        elif self.perspective_selections and not self.perspective_context:
            self.perspective_context = self.perspective_selections[0].context_id
            self.perspective_version = self.perspective_selections[0].version
        if self.perspective_version and not self.perspective_context:
            raise ValueError("perspective_version requires perspective_context")
        selected = (
            self.author_contribution.reusable_perspective_entry_ids
            if self.author_contribution
            else []
        )
        if selected and not self.perspective_context:
            raise ValueError("reusable perspective entries require perspective_context")
        if selected and len(self.perspective_selections) > 1:
            raise ValueError("explicit perspective entry selection supports one context")
        context_ids = [selection.context_id for selection in self.perspective_selections]
        if len(context_ids) != len(set(context_ids)):
            raise ValueError("Perspective contexts must be unique")
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


class PriorIssueStatus(BaseModel):
    status: PriorIssueDisposition
    note: Optional[str] = None


class Critique(BaseModel):
    scores: Dict[str, float]
    weighted_score: float = 0.0
    issues: List[CritiqueIssue] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    prior_issue_status: Dict[str, PriorIssueStatus] = Field(default_factory=dict)
    summary: str = ""

    @field_validator("prior_issue_status", mode="before")
    @classmethod
    def normalise_legacy_prior_issue_status(cls, value):
        if value is None:
            return {}
        if not isinstance(value, dict):
            return value
        return {key: cls._normalise_legacy_disposition(status) for key, status in value.items()}

    @staticmethod
    def _normalise_legacy_disposition(value):
        if not isinstance(value, str):
            return value
        note = value.strip()
        if re.match(r"^resolved(?:\W|$)", note, flags=re.IGNORECASE):
            status = PriorIssueDisposition.RESOLVED
        elif re.match(
            r"^author(?:_|\s+|-)rejected(?:\W|$)",
            note,
            flags=re.IGNORECASE,
        ):
            status = PriorIssueDisposition.AUTHOR_REJECTED
        else:
            status = PriorIssueDisposition.UNRESOLVED
        return {"status": status.value, "note": note or None}


class QualityDecision(BaseModel):
    passed: bool
    weighted_score: float
    minimum_score: float
    minor_issue_count: int
    reasons: List[str] = Field(default_factory=list)


class LearningCandidate(BaseModel):
    role: LearningRole
    scope: str = "general"
    principle: str
    evidence: str
    status: LearningStatus
    confidence: float = Field(ge=0, le=1)
    source_event: str = "publication"
    supersedes: Optional[str] = None
    conflicts_with: List[str] = Field(default_factory=list)

    @field_validator("role", mode="before")
    @classmethod
    def validate_learning_role(cls, value):
        supported = ", ".join(role.value for role in LearningRole)
        if value not in {role.value for role in LearningRole}:
            raise ValueError(
                "Unsupported learning role {!r}; supported roles are: {}".format(value, supported)
            )
        return value


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
    diagnostic_summary_path: Optional[str] = None
    support_candidate_path: Optional[str] = None
    pending_support_count: int = 0
    idempotency_key_hash: Optional[str] = None
    idempotency_reused: bool = False
    events: List[RunEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="before")
    @classmethod
    def preserve_legacy_content_session(cls, value):
        if not isinstance(value, dict):
            return value
        work_order = value.get("work_order")
        if isinstance(work_order, dict) and not work_order.get("content_session_id"):
            value = dict(value)
            work_order = dict(work_order)
            work_order["content_session_id"] = value.get("id") or uuid4().hex[:12]
            value["work_order"] = work_order
        return value
