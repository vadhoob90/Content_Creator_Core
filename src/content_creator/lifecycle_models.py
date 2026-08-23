"""Define typed contracts for auditable aggregate lifecycle decisions."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class LifecycleDisposition(BaseModel):
    """Bind a pending artifact to an explicit exact-hash decision."""

    kind: str
    stable_id: str
    artifact_hash: str
    action: str


class LifecyclePlan(BaseModel):
    """Represent a read-only, hash-bound lifecycle preflight."""

    schema_version: str = "1.0"
    object_type: str
    object_id: str
    generated_at: str
    current_status: str
    selected_version: Optional[str] = None
    selected_manifest_hash: Optional[str] = None
    strategy: Optional[str] = None
    is_default: bool = False
    learning_epoch: dict[str, Any] = Field(default_factory=dict)
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    perspective_contexts: list[dict[str, Any]] = Field(default_factory=list)
    perspective_candidates: list[dict[str, Any]] = Field(default_factory=list)
    perspective_proposals: list[dict[str, Any]] = Field(default_factory=list)
    runs: list[dict[str, Any]] = Field(default_factory=list)
    publications: dict[str, Any] = Field(default_factory=dict)
    associated_artifacts: list[str] = Field(default_factory=list)
    effects: dict[str, list[str]] = Field(default_factory=dict)
    required_decisions: list[str] = Field(default_factory=list)
    valid_next_actions: list[str] = Field(default_factory=list)
    binding_hash: str = ""


class LifecycleReceipt(BaseModel):
    """Record one immutable and independently verifiable lifecycle transition."""

    schema_version: str = "1.0"
    object_type: str
    object_id: str
    action: str
    actor: str
    reason: str
    decided_at: str
    prior_status: str
    resulting_status: str
    prior_registry_hash: str
    resulting_registry_hash: str
    selected_version: Optional[str] = None
    selected_manifest_hash: Optional[str] = None
    candidate_dispositions: list[LifecycleDisposition] = Field(default_factory=list)
    learning_epoch_id: Optional[str] = None
    learning_epoch_hash: Optional[str] = None
    affected_context_ids: list[str] = Field(default_factory=list)
    affected_run_ids: list[str] = Field(default_factory=list)
    predecessor_receipt: Optional[str] = None
    successor_receipt: Optional[str] = None
    plan_hash: Optional[str] = None
    legacy_migration: bool = False


class VersionLifecycleRecord(BaseModel):
    """Record lifecycle metadata separately from immutable version manifests."""

    version: str
    manifest_hash: str
    strategy: Optional[str] = None
    evidence_baseline_hash: Optional[str] = None
    approval_receipt: Optional[str] = None
    approved_at: Optional[str] = None
    learning_epoch_id: Optional[str] = None
    learning_epoch_hash: Optional[str] = None
    relationship: str = "historical"
    successor_version: Optional[str] = None
    lifecycle_receipts: list[str] = Field(default_factory=list)
    historical_resolution_permitted: bool = True
    reconstructed: bool = False


class VersionLifecycleCatalogue(BaseModel):
    """Describe lifecycle relationships for all immutable versions of one voice."""

    schema_version: str = "1.0"
    voice_id: str
    records: list[VersionLifecycleRecord] = Field(default_factory=list)


class LifecycleVerification(BaseModel):
    """Return deterministic offline receipt and catalogue verification results."""

    valid: bool
    checked_receipts: int = 0
    failures: list[str] = Field(default_factory=list)
