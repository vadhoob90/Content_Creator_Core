"""Activate a validated source-derived voice candidate."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from .storage import RunStore
from .versioned_artifacts import ActivationLock, hash_file, next_major_version, verify_components
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
    root: Path
    path: Path

    def _read(self) -> dict:
        raise NotImplementedError


def activate_candidate(
    registry_service: VoiceRegistryAccess,
    voice_id: str,
    approved_by: str,
    override_reason: str | None,
) -> VoiceApprovalReceipt:
    voice_root = registry_service.root / "profiles" / voice_id
    candidate = voice_root / "candidate"
    manifest, evaluation_path = _validated_candidate(candidate, override_reason)
    with ActivationLock(
        voice_root / ".activation.lock",
        "Voice activation is already in progress",
        VoiceError,
    ):
        registry = registry_service._read()
        existing_receipt = _existing_receipt(voice_root, registry, voice_id, manifest)
        if existing_receipt:
            return existing_receipt
        version, destination = _promote_candidate(voice_root, candidate, manifest)
        receipt = _write_receipt(
            destination, evaluation_path, manifest, approved_by, override_reason, version
        )
        _activate_registry(registry_service, registry, manifest, version)
        _complete_onboarding(registry_service.root, voice_id)
        return receipt


def _validated_candidate(
    candidate: Path, override_reason: str | None
) -> tuple[VoiceManifest, Path]:
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
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    if not evaluation.get("passed"):
        if evaluation.get("hard_failures"):
            raise VoiceError("Voice evaluation has non-overridable integrity failures")
        if not override_reason:
            raise VoiceError("Voice evaluation did not pass")
    return manifest, evaluation_path


def _existing_receipt(
    voice_root: Path, registry: dict, voice_id: str, manifest: VoiceManifest
) -> VoiceApprovalReceipt | None:
    existing = registry["profiles"].get(voice_id, {})
    if existing.get("candidate_hash") != manifest.candidate_hash:
        return None
    if existing.get("status") != VoiceStatus.ACTIVE.value:
        return None
    receipt_path = voice_root / "versions" / existing["active_version"] / "approval-receipt.json"
    return VoiceApprovalReceipt.model_validate_json(receipt_path.read_text(encoding="utf-8"))


def _promote_candidate(
    voice_root: Path, candidate: Path, manifest: VoiceManifest
) -> tuple[str, Path]:
    version = next_major_version(voice_root / "versions")
    destination = voice_root / "versions" / version
    shutil.copytree(candidate, destination)
    manifest.version = version
    manifest.status = VoiceStatus.ACTIVE
    RunStore._atomic_text(destination / "manifest.json", manifest.model_dump_json(indent=2))
    return version, destination


def _write_receipt(
    destination: Path,
    evaluation_path: Path,
    manifest: VoiceManifest,
    approved_by: str,
    override_reason: str | None,
    version: str,
) -> VoiceApprovalReceipt:
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
    onboarding = load_voice_onboarding(root, voice_id)
    if not onboarding:
        return
    onboarding.status = "source-derived-active"
    onboarding.strategy = VoiceStrategy.SOURCE_DERIVED
    onboarding.template_id = None
    onboarding.perspective_mode = "workspace-policy"
    onboarding.perspective_disabled_reason = None
    save_voice_onboarding(root, onboarding)
