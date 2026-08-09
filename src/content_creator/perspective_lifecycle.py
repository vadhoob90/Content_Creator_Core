"""Stage and activate versioned perspective contexts."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from typing import Any

from .perspective_support import (
    PerspectiveApprovalReceipt,
    PerspectiveEntry,
    PerspectiveEntryStatus,
    PerspectiveError,
    PerspectiveManifest,
    PerspectiveStatus,
)
from .storage import RunStore
from .versioned_artifacts import (
    ActivationLock,
    hash_file,
    hash_json,
    numeric_version_directories,
    publish_version_snapshot,
    replace_candidate,
    verify_components,
)
from .voices import VoiceRegistry


def stage_context(
    registry_service: Any,
    context_id: str,
    entries: list[PerspectiveEntry],
    display_name: str | None,
) -> PerspectiveManifest:
    """Stage the context.

    Args:
        registry_service (Any): The registry service used for domain lifecycle
            operations.
        context_id (str): The stable identifier for the context.
        entries (list[PerspectiveEntry]): The ordered domain records to process.
        display_name (str | None): The human-readable name shown to users.

    Returns:
        PerspectiveManifest: The resulting perspective manifest for stage context.
    """
    VoiceRegistry(registry_service.root).resolve(registry_service.voice_id)
    context_root = registry_service.context_root(context_id)
    staging = context_root / ".candidate-staging"
    candidate = context_root / "candidate"
    with ActivationLock(
        context_root / ".activation.lock",
        "Perspective lifecycle operation is already in progress",
        PerspectiveError,
    ):
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        _validate_entries(entries)
        components = _write_candidate_files(registry_service, staging, context_id, entries)
        component_hashes = {
            name: hash_file(staging / filename) for name, filename in components.items()
        }
        manifest = PerspectiveManifest(
            owner_voice_id=registry_service.voice_id,
            context_id=context_id,
            display_name=display_name or context_id.replace("-", " ").title(),
            status=PerspectiveStatus.AWAITING_APPROVAL,
            candidate_hash=hash_json(component_hashes),
            components=components,
            component_hashes=component_hashes,
        )
        RunStore._atomic_text(staging / "manifest.json", manifest.model_dump_json(indent=2))
        replace_candidate(staging, candidate)
    return manifest


def _validate_entries(entries: list[PerspectiveEntry]) -> None:
    """Validate the entries.

    Args:
        entries (list[PerspectiveEntry]): The ordered domain records to process.

    Returns:
        None: The callable updates entries state and returns no value.

    Raises:
        PerspectiveError: If the perspective operation cannot complete.
    """
    entry_ids = [entry.id for entry in entries]
    if len(entry_ids) != len(set(entry_ids)):
        raise PerspectiveError("Perspective entry ids must be unique")
    known = set(entry_ids)
    for entry in entries:
        if entry.status == PerspectiveEntryStatus.APPROVED and not entry.provenance:
            raise PerspectiveError(f"Approved perspective entries require provenance: {entry.id}")
        if entry.supersedes and entry.supersedes not in known:
            raise PerspectiveError(f"Perspective entry {entry.id} supersedes an unknown entry")


def _write_candidate_files(
    registry_service: Any, staging: Any, context_id: str, entries: list[PerspectiveEntry]
) -> dict[str, str]:
    """Write the candidate files.

    Args:
        registry_service (Any): The registry service used for domain lifecycle
            operations.
        staging (Any): The staging value passed to write candidate files.
        context_id (str): The stable identifier for the context.
        entries (list[PerspectiveEntry]): The ordered domain records to process.

    Returns:
        dict[str, str]: The structured resulting data for write candidate files.
    """
    RunStore._atomic_text(
        staging / "entries.json",
        json.dumps([entry.model_dump(mode="json") for entry in entries], indent=2),
    )
    RunStore._atomic_text(
        staging / "perspective.md", registry_service.render_profile(context_id, entries)
    )
    constraints = {
        "perspective_is_not_factual_authority": True,
        "never_extrapolate_unrecorded_positions": True,
        "preserve_qualifications": True,
        "do_not_use_retired_or_superseded_entries": True,
        "context_inheritance": "none",
    }
    RunStore._atomic_text(staging / "constraints.json", json.dumps(constraints, indent=2))
    active_entries = [entry for entry in entries if entry.status == PerspectiveEntryStatus.APPROVED]
    passed = all(entry.provenance for entry in active_entries)
    evaluation = {
        "schema_version": "1.0",
        "passed": passed,
        "checks": {
            "all_active_entries_have_provenance": passed,
            "entry_ids_unique": True,
            "cross_context_inheritance": False,
            "empty_context_permitted": True,
        },
        "hard_failures": [],
    }
    RunStore._atomic_text(staging / "evaluation-report.json", json.dumps(evaluation, indent=2))
    return {
        "profile": "perspective.md",
        "entries": "entries.json",
        "constraints": "constraints.json",
        "evaluation_report": "evaluation-report.json",
    }


def activate_context(
    registry_service: Any, context_id: str, approved_by: str
) -> PerspectiveApprovalReceipt:
    """Activate the context.

    Args:
        registry_service (Any): The registry service used for domain lifecycle
            operations.
        context_id (str): The stable identifier for the context.
        approved_by (str): The reviewer identity recorded with the approval.

    Returns:
        PerspectiveApprovalReceipt: The resulting perspective approval receipt for
            activate context.
    """
    VoiceRegistry(registry_service.root).resolve(registry_service.voice_id)
    context_root = registry_service.context_root(context_id)
    candidate = context_root / "candidate"
    with ActivationLock(
        context_root / ".activation.lock",
        "Perspective lifecycle operation is already in progress",
        PerspectiveError,
    ):
        manifest = _validated_candidate(candidate)
        registry = registry_service._read()
        existing = _existing_receipt(context_root, registry, context_id, manifest)
        if existing:
            return existing
        recovered = _recover_published_snapshot(registry_service, context_root, registry, manifest)
        if recovered:
            return recovered
        return _promote(registry_service, registry, candidate, manifest, approved_by)


def _validated_candidate(candidate: Any) -> PerspectiveManifest:
    """Return the validated candidate.

    Args:
        candidate (Any): The candidate artifact under evaluation.

    Returns:
        PerspectiveManifest: The resulting perspective manifest for validated candidate.

    Raises:
        PerspectiveError: If the perspective operation cannot complete.
    """
    manifest_path = candidate / "manifest.json"
    if not manifest_path.exists():
        raise PerspectiveError("Perspective candidate has not been created")
    manifest = PerspectiveManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    mismatches = verify_components(candidate, manifest.components, manifest.component_hashes)
    if mismatches:
        raise PerspectiveError(f"Perspective component hash mismatch: {mismatches[0]}")
    evaluation = json.loads((candidate / manifest.components["evaluation_report"]).read_text())
    if not evaluation.get("passed"):
        raise PerspectiveError("Perspective evaluation did not pass")
    return manifest


def _existing_receipt(
    context_root: Any, registry: dict, context_id: str, manifest: PerspectiveManifest
) -> PerspectiveApprovalReceipt | None:
    """Return the existing receipt.

    Args:
        context_root (Any): The context root value passed to existing receipt.
        registry (dict): The registry used to resolve and persist domain entries.
        context_id (str): The stable identifier for the context.
        manifest (PerspectiveManifest): The manifest that records the artifact contract.

    Returns:
        PerspectiveApprovalReceipt | None: The resulting existing receipt when
            available; otherwise ``None``.
    """
    existing = registry["contexts"].get(context_id, {})
    if existing.get("candidate_hash") != manifest.candidate_hash:
        return None
    if existing.get("status") != PerspectiveStatus.ACTIVE.value:
        return None
    path = context_root / "versions" / existing["active_version"] / "approval-receipt.json"
    return PerspectiveApprovalReceipt.model_validate_json(path.read_text(encoding="utf-8"))


def _recover_published_snapshot(
    registry_service: Any,
    context_root: Any,
    registry: dict,
    candidate_manifest: PerspectiveManifest,
) -> PerspectiveApprovalReceipt | None:
    """Restore a verified snapshot published before an interrupted registry write.

    Args:
        registry_service (Any): Perspective registry persistence service.
        context_root (Any): Filesystem root for the selected context.
        registry (dict): Current registry state.
        candidate_manifest (PerspectiveManifest): Validated candidate being retried.

    Returns:
        PerspectiveApprovalReceipt | None: Recovered receipt, or ``None`` when no
            matching published snapshot exists.

    Raises:
        PerspectiveError: If a matching published snapshot is not internally
            consistent.
    """
    existing = registry["contexts"].get(candidate_manifest.context_id, {})
    if existing.get("candidate_hash") == candidate_manifest.candidate_hash:
        return None
    for destination in numeric_version_directories(context_root / "versions"):
        stored = PerspectiveManifest.model_validate_json(
            (destination / "manifest.json").read_text(encoding="utf-8")
        )
        if stored.candidate_hash != candidate_manifest.candidate_hash:
            continue
        if stored.version != destination.name:
            raise PerspectiveError("Promoted perspective version metadata mismatch")
        _verify_promoted_snapshot(destination, candidate_manifest)
        receipt = PerspectiveApprovalReceipt.model_validate_json(
            (destination / "approval-receipt.json").read_text(encoding="utf-8")
        )
        _activate_registry(registry_service, registry, stored, destination.name)
        return receipt
    return None


def _promote(
    registry_service: Any,
    registry: dict,
    candidate: Any,
    manifest: PerspectiveManifest,
    approved_by: str,
) -> PerspectiveApprovalReceipt:
    """Return the promote.

    Build every immutable artifact under a hidden directory, verify the complete
    snapshot, publish it atomically, and only then expose it through the registry.

    Args:
        registry_service (Any): The registry service used for domain lifecycle
            operations.
        registry (dict): The registry used to resolve and persist domain entries.
        candidate (Any): The candidate artifact under evaluation.
        manifest (PerspectiveManifest): The manifest that records the artifact contract.
        approved_by (str): The reviewer identity recorded with the approval.

    Returns:
        PerspectiveApprovalReceipt: The resulting perspective approval receipt for
            promote.
    """
    context_root = registry_service.context_root(manifest.context_id)
    active_manifest = manifest.model_copy(deep=True)
    prepared: dict[str, PerspectiveApprovalReceipt] = {}

    def prepare(staging: Any, version: str) -> None:
        """Write complete active perspective metadata into the hidden snapshot.

        Args:
            staging (Any): Hidden snapshot directory being prepared.
            version (str): Allocated immutable perspective version.

        Returns:
            None: Active metadata is written in place.
        """
        active_manifest.version = version
        active_manifest.status = PerspectiveStatus.ACTIVE
        RunStore._atomic_text(staging / "manifest.json", active_manifest.model_dump_json(indent=2))
        receipt = PerspectiveApprovalReceipt(
            owner_voice_id=registry_service.voice_id,
            context_id=active_manifest.context_id,
            activated_version=version,
            approved_by=approved_by,
            approved_at=datetime.now(UTC).isoformat(),
            candidate_hash=active_manifest.candidate_hash,
        )
        RunStore._atomic_text(staging / "approval-receipt.json", receipt.model_dump_json(indent=2))
        lock = {
            "owner_voice_id": registry_service.voice_id,
            "context_id": active_manifest.context_id,
            "version": version,
            "candidate_hash": active_manifest.candidate_hash,
            "component_hashes": active_manifest.component_hashes,
        }
        RunStore._atomic_text(staging / "perspective-lock.json", json.dumps(lock, indent=2))
        prepared["receipt"] = receipt

    def verify(staging: Any) -> None:
        """Verify prepared perspective metadata before atomic publication.

        Args:
            staging (Any): Hidden snapshot directory to verify.

        Returns:
            None: Verification completes without mutation.
        """
        _verify_promoted_snapshot(staging, active_manifest)

    version, destination = publish_version_snapshot(
        candidate, context_root / "versions", prepare, verify
    )
    try:
        _activate_registry(registry_service, registry, active_manifest, version)
    except Exception:
        shutil.rmtree(destination)
        raise
    return prepared["receipt"]


def _activate_registry(
    registry_service: Any,
    registry: dict,
    manifest: PerspectiveManifest,
    version: str,
) -> None:
    """Persist the selected perspective snapshot as active.

    Args:
        registry_service (Any): Perspective registry persistence service.
        registry (dict): Current registry state.
        manifest (PerspectiveManifest): Verified active manifest.
        version (str): Immutable version directory name.

    Returns:
        None: Registry state is updated atomically.
    """
    registry["contexts"][manifest.context_id] = {
        "display_name": manifest.display_name,
        "status": PerspectiveStatus.ACTIVE.value,
        "active_version": version,
        "candidate_hash": manifest.candidate_hash,
    }
    RunStore._atomic_text(registry_service.registry_path, json.dumps(registry, indent=2))


def _verify_promoted_snapshot(destination: Any, manifest: PerspectiveManifest) -> None:
    """Verify that a prepared perspective version is internally consistent.

    Args:
        destination (Any): Hidden or published immutable version directory.
        manifest (PerspectiveManifest): Expected active manifest for the snapshot.

    Returns:
        None: Verification completes without mutation.

    Raises:
        PerspectiveError: If components or approval metadata do not match the candidate.
    """
    stored = PerspectiveManifest.model_validate_json(
        (destination / "manifest.json").read_text(encoding="utf-8")
    )
    mismatches = verify_components(destination, stored.components, stored.component_hashes)
    if mismatches:
        raise PerspectiveError(f"Promoted perspective component hash mismatch: {mismatches[0]}")
    receipt = PerspectiveApprovalReceipt.model_validate_json(
        (destination / "approval-receipt.json").read_text(encoding="utf-8")
    )
    lock = json.loads((destination / "perspective-lock.json").read_text(encoding="utf-8"))
    if stored.candidate_hash != manifest.candidate_hash:
        raise PerspectiveError("Promoted perspective candidate hash mismatch")
    if stored.status != PerspectiveStatus.ACTIVE:
        raise PerspectiveError("Promoted perspective version metadata mismatch")
    if receipt.candidate_hash != manifest.candidate_hash:
        raise PerspectiveError("Perspective approval receipt candidate hash mismatch")
    if receipt.activated_version != stored.version:
        raise PerspectiveError("Perspective approval receipt version mismatch")
    if lock.get("candidate_hash") != manifest.candidate_hash:
        raise PerspectiveError("Perspective lock candidate hash mismatch")
    if lock.get("version") != stored.version:
        raise PerspectiveError("Perspective lock version mismatch")
    if lock.get("component_hashes") != manifest.component_hashes:
        raise PerspectiveError("Perspective lock component hashes do not match the manifest")
