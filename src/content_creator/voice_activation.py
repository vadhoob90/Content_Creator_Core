"""Activate a validated source-derived voice candidate."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from .storage import RunStore
from .versioned_artifacts import (
    ActivationLock,
    hash_file,
    hash_json,
    numeric_version_directories,
    publish_version_snapshot,
    verify_components,
)
from .voice_models import (
    VoiceApprovalReceipt,
    VoiceError,
    VoiceManifest,
    VoiceStatus,
    VoiceStrategy,
    load_voice_onboarding,
    save_voice_onboarding,
)


class VoiceRegistryAccess(Protocol):
    """Provide registry operations needed during voice activation."""

    root: Path
    path: Path

    def _read(self) -> dict:
        """Read the voice registry access workflow.

        Returns:
            dict: The loaded dict for value.

        Raises:
            NotImplementedError: If the not implemented operation cannot complete.
        """
        raise NotImplementedError


def activate_candidate(
    registry_service: VoiceRegistryAccess,
    voice_id: str,
    approved_by: str,
    override_reason: str | None,
) -> VoiceApprovalReceipt:
    """Activate the candidate.

    Args:
        registry_service (VoiceRegistryAccess): The registry service used for domain
            lifecycle operations.
        voice_id (str): The stable identifier for the selected voice.
        approved_by (str): The reviewer identity recorded with the approval.
        override_reason (str | None): The override reason text processed when activate
            candidate.

    Returns:
        VoiceApprovalReceipt: The resulting voice approval receipt for activate
            candidate.
    """
    voice_root = registry_service.root / "profiles" / voice_id
    candidate = voice_root / "candidate"
    with ActivationLock(
        voice_root / ".lifecycle.lock",
        "Voice candidate lifecycle operation is already in progress",
        VoiceError,
    ):
        manifest, evaluation_path = _validated_candidate(candidate, override_reason)
        registry = registry_service._read()
        existing_receipt = _existing_receipt(voice_root, registry, voice_id, manifest)
        if existing_receipt:
            return existing_receipt
        _validate_active_baseline(voice_root, registry, voice_id, manifest)
        recovered_receipt = _recover_published_snapshot(
            registry_service, voice_root, registry, manifest
        )
        if recovered_receipt:
            _complete_onboarding(registry_service.root, voice_id)
            return recovered_receipt
        version, destination, active_manifest, receipt = _promote_candidate(
            voice_root,
            candidate,
            evaluation_path,
            manifest,
            approved_by,
            override_reason,
        )
        try:
            _activate_registry(registry_service, registry, active_manifest, version)
        except Exception:
            shutil.rmtree(destination)
            raise
        _complete_onboarding(registry_service.root, voice_id)
        return receipt


def _validated_candidate(
    candidate: Path, override_reason: str | None
) -> tuple[VoiceManifest, Path]:
    """Return the validated candidate.

    Args:
        candidate (Path): The candidate artifact under evaluation.
        override_reason (str | None): The override reason text processed when validated
            candidate.

    Returns:
        tuple[VoiceManifest, Path]: The resolved filesystem path for validated
            candidate.

    Raises:
        VoiceError: If the voice operation cannot complete.
    """
    manifest_path = candidate / "manifest.json"
    evaluation_path = candidate / "evaluation-report.json"
    if not manifest_path.exists():
        raise VoiceError("Voice candidate has not been built")
    manifest = VoiceManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if not manifest.authorisation.confirmed:
        raise VoiceError("Voice authorisation has not been confirmed")
    mismatches = verify_components(candidate, manifest.components, manifest.component_hashes)
    if mismatches:
        raise VoiceError(f"Voice component hash mismatch: {mismatches[0]}")
    if manifest.status not in {VoiceStatus.AWAITING_APPROVAL, VoiceStatus.BUILT}:
        raise VoiceError("Voice candidate is not awaiting approval")
    if manifest.evolution_delta_hash:
        delta = json.loads((candidate / "voice-evolution.json").read_text(encoding="utf-8"))
        if hash_json(delta) != manifest.evolution_delta_hash:
            raise VoiceError("Voice evolution delta hash mismatch")
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    if not evaluation.get("passed"):
        if evaluation.get("hard_failures"):
            raise VoiceError("Voice evaluation has non-overridable integrity failures")
        if not override_reason:
            raise VoiceError("Voice evaluation did not pass")
    return manifest, evaluation_path


def _validate_active_baseline(
    voice_root: Path,
    registry: dict,
    voice_id: str,
    manifest: VoiceManifest,
) -> None:
    """Reject approval when the active baseline changed after candidate creation.

    Args:
        voice_root (Path): Filesystem root for the selected voice.
        registry (dict): Current voice registry mapping.
        voice_id (str): Stable selected voice identifier.
        manifest (VoiceManifest): Candidate manifest containing baseline evidence.

    Returns:
        None: Baseline consistency is validated without mutation.

    Raises:
        VoiceError: If an evolution candidate no longer matches the active baseline.
    """
    if manifest.evolution_mode not in {"evolve", "full-regenerate"}:
        return
    current = registry["profiles"].get(voice_id, {})
    if current.get("active_version") != manifest.baseline_version:
        raise VoiceError("Voice evolution candidate has a stale active baseline version")
    if current.get("candidate_hash") != manifest.baseline_candidate_hash:
        raise VoiceError("Voice evolution candidate has a stale registry baseline hash")
    baseline_manifest_path = (
        voice_root / "versions" / str(manifest.baseline_version) / "manifest.json"
    )
    baseline = VoiceManifest.model_validate_json(baseline_manifest_path.read_text(encoding="utf-8"))
    if baseline.candidate_hash != manifest.baseline_candidate_hash:
        raise VoiceError("Voice evolution candidate has a stale active baseline hash")
    mismatches = verify_components(
        baseline_manifest_path.parent, baseline.components, baseline.component_hashes
    )
    if mismatches:
        raise VoiceError(f"Active baseline component hash mismatch: {mismatches[0]}")


def _existing_receipt(
    voice_root: Path, registry: dict, voice_id: str, manifest: VoiceManifest
) -> VoiceApprovalReceipt | None:
    """Return the existing receipt.

    Args:
        voice_root (Path): The filesystem path containing the voice root.
        registry (dict): The registry used to resolve and persist domain entries.
        voice_id (str): The stable identifier for the selected voice.
        manifest (VoiceManifest): The manifest that records the artifact contract.

    Returns:
        VoiceApprovalReceipt | None: The resulting existing receipt when available;
            otherwise ``None``.
    """
    existing = registry["profiles"].get(voice_id, {})
    if existing.get("candidate_hash") != manifest.candidate_hash:
        return None
    if existing.get("status") != VoiceStatus.ACTIVE.value:
        return None
    receipt_path = voice_root / "versions" / existing["active_version"] / "approval-receipt.json"
    return VoiceApprovalReceipt.model_validate_json(receipt_path.read_text(encoding="utf-8"))


def _recover_published_snapshot(
    registry_service: VoiceRegistryAccess,
    voice_root: Path,
    registry: dict,
    candidate_manifest: VoiceManifest,
) -> VoiceApprovalReceipt | None:
    """Restore a verified snapshot published before an interrupted registry write.

    Args:
        registry_service (VoiceRegistryAccess): Registry persistence service.
        voice_root (Path): Filesystem root for the selected voice.
        registry (dict): Current registry state.
        candidate_manifest (VoiceManifest): Validated candidate being retried.

    Returns:
        VoiceApprovalReceipt | None: Recovered receipt, or ``None`` when no matching
            published snapshot exists.

    Raises:
        VoiceError: If a matching published snapshot is not internally consistent.
    """
    existing = registry["profiles"].get(candidate_manifest.id, {})
    if existing.get("candidate_hash") == candidate_manifest.candidate_hash:
        return None
    for destination in numeric_version_directories(voice_root / "versions"):
        stored = VoiceManifest.model_validate_json(
            (destination / "manifest.json").read_text(encoding="utf-8")
        )
        if stored.candidate_hash != candidate_manifest.candidate_hash:
            continue
        if stored.version != destination.name:
            raise VoiceError("Promoted voice version metadata mismatch")
        _verify_promoted_snapshot(destination, candidate_manifest)
        receipt = VoiceApprovalReceipt.model_validate_json(
            (destination / "approval-receipt.json").read_text(encoding="utf-8")
        )
        _activate_registry(registry_service, registry, stored, destination.name)
        return receipt
    return None


def _promote_candidate(
    voice_root: Path,
    candidate: Path,
    evaluation_path: Path,
    manifest: VoiceManifest,
    approved_by: str,
    override_reason: str | None,
) -> tuple[str, Path, VoiceManifest, VoiceApprovalReceipt]:
    """Prepare and atomically publish a complete immutable voice version.

    Build every immutable artifact under a hidden directory, verify the complete
    snapshot, and expose the numeric version only after all metadata agrees.

    Args:
        voice_root (Path): The filesystem path containing the voice root.
        candidate (Path): The candidate artifact under evaluation.
        evaluation_path (Path): Validated candidate evaluation report.
        manifest (VoiceManifest): The manifest that records the artifact contract.
        approved_by (str): Reviewer identity recorded in the approval receipt.
        override_reason (str | None): Accepted quality-risk reason, when present.

    Returns:
        tuple[str, Path, VoiceManifest, VoiceApprovalReceipt]: Published version,
            destination, active manifest, and approval receipt.
    """
    active_manifest = manifest.model_copy(deep=True)
    prepared: dict[str, VoiceApprovalReceipt] = {}

    def prepare(staging: Path, version: str) -> None:
        """Write complete active voice metadata into the hidden snapshot.

        Args:
            staging (Path): Hidden snapshot directory being prepared.
            version (str): Allocated immutable voice version.

        Returns:
            None: Active metadata is written in place.
        """
        active_manifest.version = version
        active_manifest.status = VoiceStatus.ACTIVE
        RunStore._atomic_text(staging / "manifest.json", active_manifest.model_dump_json(indent=2))
        prepared["receipt"] = _write_receipt(
            staging,
            evaluation_path,
            active_manifest,
            approved_by,
            override_reason,
            version,
        )

    def verify(staging: Path) -> None:
        """Verify prepared voice metadata before atomic publication.

        Args:
            staging (Path): Hidden snapshot directory to verify.

        Returns:
            None: Verification completes without mutation.
        """
        _verify_promoted_snapshot(staging, active_manifest)

    version, destination = publish_version_snapshot(
        candidate, voice_root / "versions", prepare, verify
    )
    return version, destination, active_manifest, prepared["receipt"]


def _verify_promoted_snapshot(destination: Path, manifest: VoiceManifest) -> None:
    """Verify that a prepared voice version is internally consistent.

    Args:
        destination (Path): Hidden or published immutable version directory.
        manifest (VoiceManifest): Expected active manifest for the snapshot.

    Returns:
        None: Verification completes without mutation.

    Raises:
        VoiceError: If components or approval metadata do not match the candidate.
    """
    stored = VoiceManifest.model_validate_json(
        (destination / "manifest.json").read_text(encoding="utf-8")
    )
    mismatches = verify_components(destination, stored.components, stored.component_hashes)
    if mismatches:
        raise VoiceError(f"Promoted voice component hash mismatch: {mismatches[0]}")
    receipt = VoiceApprovalReceipt.model_validate_json(
        (destination / "approval-receipt.json").read_text(encoding="utf-8")
    )
    lock = json.loads((destination / "voice-lock.json").read_text(encoding="utf-8"))
    if stored.candidate_hash != manifest.candidate_hash:
        raise VoiceError("Promoted voice candidate hash mismatch")
    if stored.status != VoiceStatus.ACTIVE:
        raise VoiceError("Promoted voice version metadata mismatch")
    if receipt.candidate_hash != manifest.candidate_hash:
        raise VoiceError("Voice approval receipt candidate hash mismatch")
    if receipt.activated_version != stored.version:
        raise VoiceError("Voice approval receipt version mismatch")
    if lock.get("candidate_hash") != manifest.candidate_hash:
        raise VoiceError("Voice lock candidate hash mismatch")
    if lock.get("version") != stored.version:
        raise VoiceError("Voice lock version mismatch")
    if lock.get("component_hashes") != manifest.component_hashes:
        raise VoiceError("Voice lock component hashes do not match the manifest")


def _write_receipt(
    destination: Path,
    evaluation_path: Path,
    manifest: VoiceManifest,
    approved_by: str,
    override_reason: str | None,
    version: str,
) -> VoiceApprovalReceipt:
    """Write the receipt.

    Args:
        destination (Path): The destination filesystem path.
        evaluation_path (Path): The filesystem path for the evaluation path.
        manifest (VoiceManifest): The manifest that records the artifact contract.
        approved_by (str): The reviewer identity recorded with the approval.
        override_reason (str | None): The override reason text processed when write
            receipt.
        version (str): The immutable artifact or schema version identifier.

    Returns:
        VoiceApprovalReceipt: The resulting voice approval receipt for write receipt.
    """
    receipt = VoiceApprovalReceipt(
        voice_id=manifest.id,
        candidate_version="candidate",
        activated_version=version,
        approved_by=approved_by,
        approved_at=datetime.now(UTC).isoformat(),
        candidate_hash=manifest.candidate_hash,
        evaluation_report_hash=hash_file(evaluation_path),
        override_reason=override_reason,
    )
    RunStore._atomic_text(destination / "approval-receipt.json", receipt.model_dump_json(indent=2))
    lock = {
        "voice_id": manifest.id,
        "version": version,
        "candidate_hash": manifest.candidate_hash,
        "component_hashes": manifest.component_hashes,
    }
    RunStore._atomic_text(destination / "voice-lock.json", json.dumps(lock, indent=2))
    return receipt


def _activate_registry(
    registry_service: VoiceRegistryAccess, registry: dict, manifest: VoiceManifest, version: str
) -> None:
    """Activate the registry.

    Args:
        registry_service (VoiceRegistryAccess): The registry service used for domain
            lifecycle operations.
        registry (dict): The registry used to resolve and persist domain entries.
        manifest (VoiceManifest): The manifest that records the artifact contract.
        version (str): The immutable artifact or schema version identifier.

    Returns:
        None: The callable updates activate registry state and returns no value.
    """
    registry["profiles"][manifest.id] = {
        "display_name": manifest.display_name,
        "status": VoiceStatus.ACTIVE.value,
        "active_version": version,
        "candidate_hash": manifest.candidate_hash,
        "strategy": manifest.strategy.value,
        "evidence_status": manifest.evidence_status,
        "perspectives_allowed": manifest.perspectives_allowed,
        "template_id": manifest.template_id,
    }
    RunStore._atomic_text(registry_service.path, json.dumps(registry, indent=2))


def _complete_onboarding(root: Path, voice_id: str) -> None:
    """Return the complete onboarding.

    Args:
        root (Path): The workspace root directory.
        voice_id (str): The stable identifier for the selected voice.

    Returns:
        None: The callable updates complete onboarding state and returns no value.
    """
    onboarding = load_voice_onboarding(root, voice_id)
    if not onboarding:
        return
    onboarding.status = "source-derived-active"
    onboarding.strategy = VoiceStrategy.SOURCE_DERIVED
    onboarding.template_id = None
    onboarding.perspective_mode = "workspace-policy"
    onboarding.perspective_disabled_reason = None
    save_voice_onboarding(root, onboarding)
