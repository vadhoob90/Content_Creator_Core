"""Define persisted publication provenance receipt contracts."""

from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel, Field

from .perspective_semantic_review import SemanticReviewReceipt


class PerspectiveReceipt(BaseModel):
    """Represent one pinned perspective and its approved entries."""

    context_id: str
    version: str
    status_at_publication: str
    manifest_hash: str
    entries_hash: str
    selected_entry_hashes: Dict[str, str] = Field(default_factory=dict)


class PerspectiveEvaluationReceipt(BaseModel):
    """Persist the privacy-safe deterministic evaluation result."""

    passed: bool
    artifact_hash: str
    errors: list[str] = Field(default_factory=list)
    position_marker_count: int = 0
    selected_entry_ids: list[str] = Field(default_factory=list)


class PublicationArtifactReceipt(BaseModel):
    """Record one content or media artifact in a publication package."""

    role: str
    path: str
    sha256: str
    mime_type: str
    source_path: Optional[str] = None
    width: Optional[int] = Field(default=None, gt=0)
    height: Optional[int] = Field(default=None, gt=0)
    alt_text: Optional[str] = None
    approval_state: Optional[str] = None
    asset_id: Optional[str] = None
    parent_asset_id: Optional[str] = None
    derivation_revision: Optional[int] = Field(default=None, ge=1)


class PublicationReceipt(BaseModel):
    """Represent repository-tracked evidence for one publication."""

    schema_version: str = "1.0"
    artifact_path: str
    artifact_hash: str
    revision: int = Field(default=1, ge=1)
    supersedes_receipt_hash: Optional[str] = None
    artifacts: list[PublicationArtifactReceipt] = Field(default_factory=list)
    run_id: str
    final_status: str
    content_pack_id: Optional[str] = None
    content_pack_version: Optional[str] = None
    voice_id: str
    voice_version: str
    voice_manifest_hash: Optional[str] = None
    author_contribution_provenance: str
    perspectives: list[PerspectiveReceipt] = Field(default_factory=list)
    perspective_evaluation: PerspectiveEvaluationReceipt
    semantic_review: SemanticReviewReceipt = Field(default_factory=SemanticReviewReceipt)
    published_at: str


class PublicationBaselineEntry(BaseModel):
    """Represent one legacy publication admitted by prospective enforcement."""

    artifact_path: str
    artifact_hash: str


class PublicationBaseline(BaseModel):
    """Record legacy publications that predate tracked receipts."""

    schema_version: str = "1.0"
    created_at: str
    artifacts: list[PublicationBaselineEntry] = Field(default_factory=list)
