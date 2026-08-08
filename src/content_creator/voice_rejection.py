"""Classify and reject exact voice candidates without changing active versions."""

from __future__ import annotations

import os
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .storage import RunStore
from .versioned_artifacts import ActivationLock, hash_file, verify_components
from .voice_models import VoiceError, VoiceManifest, VoiceRejectionReceipt, VoiceStatus

if TYPE_CHECKING:
    from .voices import VoiceRegistry


def rejection_directory(root: Path, voice_id: str, candidate_hash: str) -> Path:
    """Return the immutable rejection snapshot directory.

    Args:
        root (Path): Workspace root directory.
        voice_id (str): Stable selected voice identifier.
        candidate_hash (str): Candidate content hash.

    Returns:
        Path: Rejection snapshot directory using a cross-platform hash name.

    Raises:
        VoiceError: If the supplied hash is not a complete lowercase SHA-256 value.
    """
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", candidate_hash):
        raise VoiceError("Candidate hash must be a complete lowercase SHA-256 value")
    digest = candidate_hash.removeprefix("sha256:")
    return root / "profiles" / voice_id / "rejections" / digest


def candidate_decision(root: Path, voice_id: str, active: dict | None = None) -> dict[str, Any]:
    """Describe whether the current candidate still requires a human decision.

    Verify the candidate before classifying it, then suppress false pending
    decisions when its hash is already active or has a rejection receipt.

    Args:
        root (Path): Workspace root directory.
        voice_id (str): Stable selected voice identifier.
        active (dict | None): Current voice registry entry when already loaded. Defaults
            to ``None``.

    Returns:
        dict[str, Any]: Candidate status, provenance, paths, and valid actions.
    """
    candidate = root / "profiles" / voice_id / "candidate"
    manifest_path = candidate / "manifest.json"
    if not manifest_path.is_file():
        return {"status": "none", "candidate_hash": None, "manifest_status": None, "actions": []}
    try:
        manifest = VoiceManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    except ValueError as error:
        return {
            "status": "invalid",
            "candidate_hash": None,
            "manifest_status": "invalid",
            "path": str(candidate.relative_to(root)),
            "problems": [str(error)],
            "actions": [],
        }
    problems = verify_components(candidate, manifest.components, manifest.component_hashes)
    result: dict[str, Any] = {
        "status": "pending",
        "candidate_hash": manifest.candidate_hash,
        "manifest_status": manifest.status.value,
        "path": str(candidate.relative_to(root)),
        "problems": [f"component hash mismatch: {name}" for name in problems],
        "actions": [],
    }
    if problems:
        result["status"] = "invalid"
        return result
    active = active or {}
    if active.get("candidate_hash") == manifest.candidate_hash:
        result["status"] = "already_active"
        return result
    archive = rejection_directory(root, voice_id, manifest.candidate_hash)
    receipt_path = archive / "rejection-receipt.json"
    if receipt_path.is_file():
        result.update(
            status="rejected",
            rejection_receipt=str(receipt_path.relative_to(root)),
            rejected_snapshot=str(archive.relative_to(root)),
        )
        return result
    if manifest.status not in {VoiceStatus.AWAITING_APPROVAL, VoiceStatus.BUILT}:
        result["status"] = manifest.status.value
        return result
    result["actions"] = [
        ["voice", "approve", voice_id],
        [
            "voice",
            "reject",
            voice_id,
            "--candidate-hash",
            manifest.candidate_hash,
            "--rejected-by",
            "<author>",
            "--reason",
            "<reason>",
        ],
    ]
    return result


def list_rejections(root: Path, voice_id: str) -> list[dict[str, Any]]:
    """Return valid rejection receipts for one voice.

    Args:
        root (Path): Workspace root directory.
        voice_id (str): Stable selected voice identifier.

    Returns:
        list[dict[str, Any]]: Rejections ordered by their recorded timestamp.
    """
    receipts = []
    for path in (root / "profiles" / voice_id / "rejections").glob("*/rejection-receipt.json"):
        receipt = VoiceRejectionReceipt.model_validate_json(path.read_text(encoding="utf-8"))
        item = receipt.model_dump(mode="json")
        item["receipt_path"] = str(path.relative_to(root))
        receipts.append(item)
    return sorted(receipts, key=lambda item: str(item["rejected_at"]))


def reject_candidate(
    registry_service: VoiceRegistry,
    voice_id: str,
    expected_hash: str,
    rejected_by: str,
    reason: str,
) -> VoiceRejectionReceipt:
    """Reject and archive the exact candidate reviewed by a human.

    Anchor the action to the reviewed hash, hold the shared lifecycle lock, and
    preserve both the active version and an immutable decision receipt.

    Args:
        registry_service (VoiceRegistry): Voice registry service.
        voice_id (str): Stable selected voice identifier.
        expected_hash (str): Candidate hash reviewed by the author.
        rejected_by (str): Human identity recorded with the rejection.
        reason (str): Human explanation for the decision.

    Returns:
        VoiceRejectionReceipt: Existing or newly persisted rejection evidence.

    Raises:
        VoiceError: If the candidate is missing, changed, invalid, or already active.
    """
    if not rejected_by.strip() or not reason.strip():
        raise VoiceError("Candidate rejection requires a non-empty actor and reason")
    voice_root = registry_service.root / "profiles" / voice_id
    archive = rejection_directory(registry_service.root, voice_id, expected_hash)
    receipt_path = archive / "rejection-receipt.json"
    if receipt_path.is_file():
        return VoiceRejectionReceipt.model_validate_json(receipt_path.read_text(encoding="utf-8"))
    with ActivationLock(
        voice_root / ".lifecycle.lock",
        "Voice candidate lifecycle operation is already in progress",
        VoiceError,
    ):
        if receipt_path.is_file():
            return VoiceRejectionReceipt.model_validate_json(
                receipt_path.read_text(encoding="utf-8")
            )
        candidate = voice_root / "candidate"
        manifest_path = candidate / "manifest.json"
        if not manifest_path.is_file():
            raise VoiceError("Voice candidate has not been built")
        manifest = VoiceManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        if manifest.candidate_hash != expected_hash:
            raise VoiceError("Voice candidate changed after review; inspect the new candidate")
        mismatches = verify_components(candidate, manifest.components, manifest.component_hashes)
        if mismatches:
            raise VoiceError(f"Voice component hash mismatch: {mismatches[0]}")
        if manifest.status not in {VoiceStatus.AWAITING_APPROVAL, VoiceStatus.BUILT}:
            raise VoiceError("Voice candidate is not awaiting a decision")
        registry = registry_service._read()
        active_entry = registry.get("profiles", {}).get(voice_id, {})
        if active_entry.get("candidate_hash") == expected_hash:
            raise VoiceError("The candidate hash is already the active voice version")
        active = None
        if active_entry.get("status") == VoiceStatus.ACTIVE.value:
            active = registry_service.resolve(voice_id)
            active["candidate_hash"] = active_entry.get("candidate_hash")
        return _archive_rejection(
            registry_service.root,
            voice_id,
            candidate,
            manifest,
            rejected_by.strip(),
            reason.strip(),
            active,
        )


def _archive_rejection(
    root: Path,
    voice_id: str,
    candidate: Path,
    manifest: VoiceManifest,
    rejected_by: str,
    reason: str,
    active: dict | None,
) -> VoiceRejectionReceipt:
    """Create and atomically publish one rejection snapshot.

    Args:
        root (Path): Workspace root directory.
        voice_id (str): Stable selected voice identifier.
        candidate (Path): Verified candidate directory.
        manifest (VoiceManifest): Verified candidate manifest.
        rejected_by (str): Human identity recorded with the rejection.
        reason (str): Human explanation for the decision.
        active (dict | None): Verified active voice snapshot, when present.

    Returns:
        VoiceRejectionReceipt: Newly persisted rejection evidence.
    """
    archive = rejection_directory(root, voice_id, manifest.candidate_hash)
    archive.parent.mkdir(parents=True, exist_ok=True)
    staging = archive.parent / f".{archive.name}.staging"
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(candidate, staging)
    original_manifest_hash = hash_file(candidate / "manifest.json")
    manifest.status = VoiceStatus.REJECTED
    RunStore._atomic_text(staging / "manifest.json", manifest.model_dump_json(indent=2))
    receipt = VoiceRejectionReceipt(
        voice_id=voice_id,
        candidate_hash=manifest.candidate_hash,
        candidate_manifest_hash=original_manifest_hash,
        rejected_by=rejected_by,
        rejected_at=datetime.now(UTC).isoformat(),
        reason=reason,
        active_version=active.get("version") if active else None,
        active_candidate_hash=(active or {}).get("candidate_hash"),
        snapshot_path=str(archive.relative_to(root)),
    )
    RunStore._atomic_text(staging / "rejection-receipt.json", receipt.model_dump_json(indent=2))
    os.replace(staging, archive)
    shutil.rmtree(candidate)
    return receipt
