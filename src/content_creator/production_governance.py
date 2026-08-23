"""Capture privacy-safe generation-time governance for production artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from .domain import RunState
from .versioned_artifacts import hash_json


class ProductionLearningEpoch(BaseModel):
    """Represent one exact version-scoped learning epoch at generation time."""

    id: str
    status: str
    digest: str


class ProductionVoice(BaseModel):
    """Represent the generation-time governed voice snapshot used by a run."""

    id: str
    version: Optional[str] = None
    source_kind: Literal[
        "approved-version", "candidate-preview", "legacy-placeholder", "legacy"
    ] = "legacy"
    artifact_digest: Optional[str] = None
    lifecycle_status_at_generation: Optional[str] = None
    version_status_at_generation: Optional[str] = None
    evidence_baseline_digest: Optional[str] = None
    learning_epoch: Optional[ProductionLearningEpoch] = None
    provenance_status: Literal["complete", "partial", "unavailable"] = "unavailable"
    provenance_reason: Optional[str] = None


class ProductionPerspective(BaseModel):
    """Represent one pinned perspective selection used by a run."""

    context_id: str
    version: Optional[str] = None
    manifest_digest: Optional[str] = None
    lifecycle_status_at_generation: Optional[str] = None
    provenance_status: Literal["complete", "partial", "unavailable"] = "unavailable"
    provenance_reason: Optional[str] = None
    reason: str
    confidence: float


class ProductionGovernance(BaseModel):
    """Collect the stable governance fields bound to generation inputs."""

    core_version: Optional[str] = None
    core_version_status: Literal["captured", "unavailable"] = "unavailable"
    voice: ProductionVoice
    perspectives: list[ProductionPerspective] = Field(default_factory=list)


def production_governance(root: Path, state: RunState) -> ProductionGovernance:
    """Return generation-time governance from the immutable resolved context.

    Never resolve live registries here. A later voice upgrade, epoch transition, or
    lifecycle change must not rewrite the provenance of an existing run.

    Args:
        root (Path): Workspace root containing the run evidence.
        state (RunState): Run whose generation inputs are described.

    Returns:
        ProductionGovernance: Privacy-safe stable governance snapshot.
    """
    context = _resolved_context(root, state.id)
    order = state.work_order
    if context is None:
        return ProductionGovernance(
            voice=_voice_from_order(order),
            perspectives=_perspectives_from_context(state, None),
        )
    core_version = _optional_text(context.get("engine_version"))
    return ProductionGovernance(
        core_version=core_version,
        core_version_status="captured" if core_version else "unavailable",
        voice=_voice_from_context(order, context.get("voice")),
        perspectives=_perspectives_from_context(state, context),
    )


def governance_hash(governance: ProductionGovernance) -> str:
    """Return the canonical digest for stable production governance.

    Args:
        governance (ProductionGovernance): Snapshot to hash.

    Returns:
        str: Canonical SHA-256 digest.
    """
    return hash_json(governance.model_dump(mode="json"))


def _resolved_context(root: Path, run_id: str) -> Optional[dict[str, Any]]:
    """Return a persisted generation snapshot without inferring missing history.

    Args:
        root (Path): Workspace root containing run artifacts.
        run_id (str): Stable identifier for the run to inspect.

    Returns:
        Optional[dict[str, Any]]: Parsed context mapping, or ``None`` when unavailable
            or invalid.
    """
    path = root / "runs" / run_id / "resolved-context.json"
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _voice_from_order(order: Any) -> ProductionVoice:
    """Return explicit unavailable voice provenance for a pre-context run.

    Args:
        order (Any): Work order containing only the historically persisted selection.

    Returns:
        ProductionVoice: Unavailable snapshot without reconstructed hashes or versions.
    """
    version = _optional_text(order.voice_version)
    return ProductionVoice(
        id=order.voice_id,
        version=version,
        source_kind="legacy-placeholder" if version == "placeholder" else "legacy",
        provenance_status="unavailable",
        provenance_reason="resolved-context-unavailable",
    )


def _voice_from_context(order: Any, value: Any) -> ProductionVoice:
    """Return selected governed voice fields from persisted resolved context.

    Choose exactly one discriminated artifact digest and require all epoch fields
    before describing an epoch as available. Raw evidence and prompt data are ignored.

    Args:
        order (Any): Work order containing the pinned voice identity.
        value (Any): Voice section loaded from the generation snapshot.

    Returns:
        ProductionVoice: Privacy-safe voice governance snapshot.
    """
    voice = value if isinstance(value, dict) else {}
    version = _optional_text(voice.get("version")) or _optional_text(order.voice_version)
    manifest_digest = _optional_text(voice.get("manifest_hash"))
    candidate_digest = _optional_text(
        voice.get("candidate_manifest_hash") or voice.get("candidate_hash")
    )
    artifact_digest = manifest_digest or candidate_digest
    strategy = _optional_text(voice.get("strategy"))
    if manifest_digest:
        source_kind = "approved-version"
    elif candidate_digest:
        source_kind = "candidate-preview"
    elif strategy == "legacy-placeholder" or version == "placeholder":
        source_kind = "legacy-placeholder"
    else:
        source_kind = "legacy"
    epoch_id = _optional_text(voice.get("learning_epoch_id"))
    epoch_status = _optional_text(voice.get("learning_epoch_status"))
    epoch_digest = _optional_text(voice.get("learning_epoch_hash"))
    epoch = (
        ProductionLearningEpoch(id=epoch_id, status=epoch_status, digest=epoch_digest)
        if epoch_id and epoch_status and epoch_digest
        else None
    )
    if artifact_digest and epoch:
        status = "complete"
        reason = None
    elif voice:
        status = "partial"
        reason = (
            "voice-artifact-digest-unavailable"
            if not artifact_digest
            else "learning-epoch-unavailable"
        )
    else:
        status = "unavailable"
        reason = "voice-context-unavailable"
    return ProductionVoice(
        id=_optional_text(voice.get("id")) or order.voice_id,
        version=version,
        source_kind=source_kind,
        artifact_digest=artifact_digest,
        lifecycle_status_at_generation=_optional_text(voice.get("status")),
        version_status_at_generation=_optional_text(voice.get("version_status")),
        evidence_baseline_digest=_optional_text(voice.get("evidence_baseline_hash")),
        learning_epoch=epoch,
        provenance_status=status,
        provenance_reason=reason,
    )


def _perspectives_from_context(
    state: RunState, context: Optional[dict[str, Any]]
) -> list[ProductionPerspective]:
    """Return pinned perspective selections in work-order order.

    Args:
        state (RunState): Run containing resolved perspective selections.
        context (Optional[dict[str, Any]]): Persisted generation snapshot when available.

    Returns:
        list[ProductionPerspective]: Bounded identities, hashes, lifecycle state, and
            selection rationale.
    """
    resolved_values = context.get("perspectives", []) if context else []
    resolved = {
        item.get("context_id"): item
        for item in resolved_values
        if isinstance(item, dict) and item.get("context_id")
    }
    return [
        ProductionPerspective(
            context_id=item.context_id,
            version=_optional_text(resolved.get(item.context_id, {}).get("version"))
            or _optional_text(item.version),
            manifest_digest=_optional_text(resolved.get(item.context_id, {}).get("manifest_hash")),
            lifecycle_status_at_generation=_optional_text(
                resolved.get(item.context_id, {}).get("status")
            ),
            provenance_status=(
                "complete"
                if resolved.get(item.context_id, {}).get("manifest_hash")
                and (resolved.get(item.context_id, {}).get("version") or item.version)
                else ("partial" if item.version else "unavailable")
            ),
            provenance_reason=(
                None
                if resolved.get(item.context_id, {}).get("manifest_hash")
                and (resolved.get(item.context_id, {}).get("version") or item.version)
                else "perspective-manifest-digest-unavailable"
            ),
            reason=item.reason,
            confidence=item.confidence,
        )
        for item in state.work_order.perspective_selections
    ]


def _optional_text(value: Any) -> Optional[str]:
    """Return a non-empty string without inventing unavailable provenance.

    Args:
        value (Any): Optional persisted scalar to normalize.

    Returns:
        Optional[str]: Normalized text, or ``None`` for missing or empty values.
    """
    if value is None:
        return None
    text = str(value).strip()
    return text or None
