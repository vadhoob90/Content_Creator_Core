"""Define persisted contracts for governed voice upgrades."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


class VoiceUpgradeMode(str, Enum):
    """Enumerate supported analysis modes for a voice upgrade."""

    INCREMENTAL = "incremental"
    FULL_CORPUS = "full-corpus"


class VoiceUpgradeState(str, Enum):
    """Enumerate durable states in the voice-upgrade lifecycle."""

    PLANNED = "planned"
    AWAITING_SELECTION = "awaiting_selection"
    AWAITING_PROVIDER_APPROVAL = "awaiting_provider_approval"
    BUILDING = "building"
    BUILT = "built"
    AWAITING_APPROVAL = "awaiting_approval"
    REJECTED = "rejected"
    ACTIVATED = "activated"
    FAILED = "failed"
    NO_MATERIAL_CHANGE = "no_material_change"
    INSUFFICIENT_DELTA = "insufficient_delta"


class LearningClassification(str, Enum):
    """Classify whether and where a learning record may be consolidated."""

    VOICE_PROFILE = "voice-profile"
    VOICE_CONSTRAINT = "voice-constraint"
    CRITIC_RUBRIC = "critic/rubric"
    REPOSITORY_AGENT_POLICY = "repository-agent-policy"
    REMAIN_LEARNING = "remain-learning"
    PERSPECTIVE = "perspective"
    RESEARCH_ONLY = "research-only"
    VISUAL_PREFERENCE = "visual-preference"
    REJECT = "reject/obsolete/conflicting"


class LearningDispositionAction(str, Enum):
    """Enumerate reviewed outcomes for a prior-version learning record."""

    INCORPORATE = "incorporate"
    CARRY_FORWARD = "carry-forward"
    PROMOTE_REPOSITORY_POLICY = "promote-repository-policy"
    ROUTE_PERSPECTIVE = "route-perspective"
    ROUTE_VISUAL = "route-visual"
    LEAVE_PRIOR = "leave-prior-version"
    REJECT = "reject-retire"


class EvidenceRecord(BaseModel):
    """Represent one canonical authorised item in a voice evidence set."""

    evidence_id: str
    kind: str
    locator: str
    content_hash: str
    title: str
    word_count: int = Field(default=0, ge=0)
    source_id: Optional[str] = None
    publication_receipt: Optional[str] = None
    publication_receipt_hash: Optional[str] = None
    authorisation_basis: str
    analysis_cache_path: Optional[str] = None


class EvidenceSet(BaseModel):
    """Persist the complete evidence represented by or offered to a voice."""

    schema_version: str = "1.0"
    voice_id: str
    voice_version: Optional[str] = None
    evidence_cutoff: str
    records: list[EvidenceRecord] = Field(default_factory=list)


class LearningDisposition(BaseModel):
    """Record an explicit author-reviewed outcome for one learning record."""

    learning_id: str
    classification: LearningClassification
    disposition: LearningDispositionAction
    rationale: str = Field(min_length=1)
    confidence: float = Field(default=1.0, ge=0, le=1)
    target_guidance_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_route(self) -> LearningDisposition:
        """Reject classification and disposition combinations that cross boundaries.

        Returns:
            LearningDisposition: The validated disposition.

        Raises:
            ValueError: If incorporation or a specialist route is inconsistent.
        """
        linguistic = {
            LearningClassification.VOICE_PROFILE,
            LearningClassification.VOICE_CONSTRAINT,
            LearningClassification.CRITIC_RUBRIC,
        }
        if self.disposition == LearningDispositionAction.INCORPORATE:
            if self.classification not in linguistic:
                raise ValueError("Only linguistic voice classifications may be incorporated")
        if self.classification == LearningClassification.VISUAL_PREFERENCE:
            if self.disposition != LearningDispositionAction.ROUTE_VISUAL:
                raise ValueError("Visual preferences must use the visual disposition route")
        if self.classification == LearningClassification.PERSPECTIVE:
            if self.disposition != LearningDispositionAction.ROUTE_PERSPECTIVE:
                raise ValueError("Perspectives must use the perspective disposition route")
        return self


class LearningSelection(BaseModel):
    """Bind explicit learning dispositions to one immutable learning epoch."""

    schema_version: str = "1.0"
    voice_id: str
    baseline_version: str
    learning_epoch_hash: str
    reviewed_by: str = Field(min_length=1)
    reviewed_at: str
    dispositions: list[LearningDisposition] = Field(default_factory=list)


class LearningEpoch(BaseModel):
    """Persist mutable learning records scoped to one immutable voice version."""

    schema_version: str = "2.0"
    voice_id: str
    voice_version: str
    epoch_id: Optional[str] = None
    status: str = "active"
    created_at: str
    frozen_at: Optional[str] = None
    frozen_by_candidate_hash: Optional[str] = None
    records: list[dict[str, Any]] = Field(default_factory=list)


class LearningEpochTransitionReceipt(BaseModel):
    """Record the atomic learning boundary crossed during voice activation."""

    schema_version: str = "1.0"
    voice_id: str
    baseline_version: Optional[str] = None
    resulting_version: str
    prior_epoch_hash: Optional[str] = None
    resulting_epoch_hash: str
    incorporated_learning_ids: list[str] = Field(default_factory=list)
    carried_forward_learning_ids: list[str] = Field(default_factory=list)
    dispositions_hash: Optional[str] = None
    activated_at: str


class VoiceUpgradePlan(BaseModel):
    """Persist a hash-bound plan for one active-to-candidate transition."""

    schema_version: str = "1.0"
    voice_id: str
    mode: VoiceUpgradeMode
    state: VoiceUpgradeState
    generated_at: str
    baseline_version: str
    baseline_candidate_hash: str
    baseline_manifest_hash: str
    baseline_strategy: str
    resulting_strategy: str = "source-derived"
    strategy_transition: Optional[str] = None
    evidence_cutoff: str
    evidence_baseline_hash: str
    evidence_delta_hash: str
    learning_epoch_hash: str
    binding_hash: str
    candidate_hash: Optional[str] = None
    decision_receipt: Optional[str] = None
    provider: Optional[str] = None
    execution_mode: str = "offline-deterministic"
    historical_private_corpus_transmitted: bool = False
    evidence_baseline_count: int = 0
    evidence_delta_count: int = 0
    learning_record_count: int = 0
    proposed_learning_classifications: list[dict[str, Any]] = Field(default_factory=list)
    duplicates: list[dict[str, str]] = Field(default_factory=list)
    data_sharing: dict[str, Any] = Field(default_factory=dict)
    exact_commands: list[list[str]] = Field(default_factory=list)
    problems: list[str] = Field(default_factory=list)


class VoiceUpgradeBuildContext(BaseModel):
    """Bind a validated persisted upgrade plan to candidate construction."""

    plan: VoiceUpgradePlan
    evidence_baseline: EvidenceSet
    evidence_delta: EvidenceSet
    represented_evidence: EvidenceSet
    learning_selection: LearningSelection
    selected_learning_records: list[dict[str, Any]] = Field(default_factory=list)
    build_fingerprint: str
