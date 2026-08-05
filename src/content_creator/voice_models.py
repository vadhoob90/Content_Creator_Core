"""Provide voice models capabilities."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .storage import RunStore

STARTER_TEMPLATE_ID = "clear-professional"


class VoiceError(RuntimeError):
    """Report voice failures."""

    pass


class VoiceStrategy(str, Enum):
    """Enumerate supported voice strategy values."""

    SOURCE_DERIVED = "source-derived"
    STARTER = "starter"


class VoiceStatus(str, Enum):
    """Enumerate supported voice status values."""

    DRAFT = "draft"
    BUILT = "built"
    AWAITING_APPROVAL = "awaiting_approval"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    INACTIVE = "inactive"


class Authorisation(BaseModel):
    """Record authorisation to use a voice source."""

    confirmed: bool = False
    attested_by: Optional[str] = None
    intended_uses: List[str] = Field(default_factory=list)
    expires_at: Optional[str] = None
    revoked_at: Optional[str] = None


class VoiceWorkOrder(BaseModel):
    """Represent a voice work order."""

    display_name: str
    voice_id: str
    author_name: Optional[str] = None
    author_aliases: List[str] = Field(default_factory=list)
    authorisation: Authorisation
    urls: List[str] = Field(default_factory=list)
    documents: List[str] = Field(default_factory=list)
    target_audiences: List[str] = Field(default_factory=list)
    strategy: VoiceStrategy = VoiceStrategy.SOURCE_DERIVED
    template_id: Optional[str] = None

    @property
    def attribution_name(self) -> str:
        """Return the attribution name."""
        return self.author_name or self.display_name


class AttributionResult(BaseModel):
    """Record the result of source attribution."""

    classification: str
    confidence: float
    voice_weight: float
    evidence: List[str] = Field(default_factory=list)
    needs_human_review: bool = False


class SourceRecord(BaseModel):
    """Represent a source record."""

    id: str
    kind: str
    locator: str
    content_hash: str
    title: str
    word_count: int
    attribution: AttributionResult
    approved_for_analysis: bool
    cache_path: str
    analysis_word_count: Optional[int] = None
    analysis_scope: str = "full-source"
    error: Optional[str] = None


class VoicePattern(BaseModel):
    """Represent a voice pattern."""

    id: str
    name: str
    description: str
    status: str
    confidence: float
    supporting_source_ids: List[str]
    counterexample_source_ids: List[str] = Field(default_factory=list)
    mandatory: bool = False
    category: str = "uncategorised"
    observation: Optional[str] = None
    communicative_function: Optional[str] = None
    contexts: Dict[str, List[str]] = Field(default_factory=dict)
    generation_guidance: Optional[str] = None
    anti_pattern: Optional[str] = None
    linguistic_evidence: Dict[str, Any] = Field(default_factory=dict)


class VoiceManifest(BaseModel):
    """Represent a voice manifest."""

    schema_version: str = "1.0"
    id: str
    display_name: str
    author_name: Optional[str] = None
    author_aliases: List[str] = Field(default_factory=list)
    version: str
    status: VoiceStatus
    candidate_hash: str
    components: Dict[str, str]
    component_hashes: Dict[str, str]
    supported_packs: Dict[str, str]
    authorisation: Authorisation
    strategy: VoiceStrategy = VoiceStrategy.SOURCE_DERIVED
    evidence_status: str = "author-sources"
    perspectives_allowed: bool = True
    template_id: Optional[str] = None


class VoiceOnboardingRecord(BaseModel):
    """Represent a voice onboarding record."""

    schema_version: str = "1.0"
    voice_id: str
    display_name: str
    author_name: str
    status: str = "undecided"
    strategy: Optional[VoiceStrategy] = None
    template_id: Optional[str] = None
    selected_by: Optional[str] = None
    selected_at: Optional[str] = None
    perspective_mode: str = "pending"
    perspective_disabled_reason: Optional[str] = None


class VoiceApprovalReceipt(BaseModel):
    """Represent a voice approval receipt."""

    voice_id: str
    candidate_version: str
    activated_version: str
    approved_by: str
    approved_at: str
    candidate_hash: str
    evaluation_report_hash: str
    override_reason: Optional[str] = None


def onboarding_path(root: Path, voice_id: str) -> Path:
    """Return the onboarding path."""
    return root.resolve() / "profiles" / voice_id / "onboarding.json"


def load_voice_onboarding(root: Path, voice_id: str) -> Optional[VoiceOnboardingRecord]:
    """Load voice onboarding."""
    path = onboarding_path(root, voice_id)
    if not path.exists():
        return None
    return VoiceOnboardingRecord.model_validate_json(path.read_text(encoding="utf-8"))


def save_voice_onboarding(root: Path, record: VoiceOnboardingRecord) -> Path:
    """Save voice onboarding."""
    path = onboarding_path(root, record.voice_id)
    RunStore._atomic_text(path, record.model_dump_json(indent=2))
    return path
