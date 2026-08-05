"""Stage and activate versioned perspective contexts."""

from __future__ import annotations

import json
import os
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
    next_major_version,
    verify_components,
)
from .voices import VoiceRegistry


def stage_context(
    registry_service: Any,
    context_id: str,
    entries: list[PerspectiveEntry],
    display_name: str | None,
) -> PerspectiveManifest:
    """Stage context."""
    VoiceRegistry(registry_service.root).resolve(registry_service.voice_id)
    context_root = registry_service.context_root(context_id)
    staging = context_root / ".candidate-staging"
    candidate = context_root / "candidate"
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
    _replace_candidate(context_root, staging, candidate)
    return manifest


def _validate_entries(entries: list[PerspectiveEntry]) -> None:
    """Validate entries."""
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
    """Write candidate files."""
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


def _replace_candidate(context_root: Any, staging: Any, candidate: Any) -> None:
    """Return the replace candidate."""
    previous = context_root / ".candidate-previous"
    if previous.exists():
        shutil.rmtree(previous)
    if candidate.exists():
        os.replace(candidate, previous)
    try:
        os.replace(staging, candidate)
    except Exception:
        if previous.exists():
            os.replace(previous, candidate)
        raise
    if previous.exists():
        shutil.rmtree(previous)


def activate_context(
    registry_service: Any, context_id: str, approved_by: str
) -> PerspectiveApprovalReceipt:
    """Activate context."""
    VoiceRegistry(registry_service.root).resolve(registry_service.voice_id)
    context_root = registry_service.context_root(context_id)
    candidate = context_root / "candidate"
    manifest = _validated_candidate(candidate)
    with ActivationLock(
        context_root / ".activation.lock",
        "Perspective activation is already in progress",
        PerspectiveError,
    ):
        registry = registry_service._read()
        existing = _existing_receipt(context_root, registry, context_id, manifest)
        if existing:
            return existing
        return _promote(registry_service, registry, candidate, manifest, approved_by)


def _validated_candidate(candidate: Any) -> PerspectiveManifest:
    """Return the validated candidate."""
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
    """Return the existing receipt."""
    existing = registry["contexts"].get(context_id, {})
    if existing.get("candidate_hash") != manifest.candidate_hash:
        return None
    if existing.get("status") != PerspectiveStatus.ACTIVE.value:
        return None
    path = context_root / "versions" / existing["active_version"] / "approval-receipt.json"
    return PerspectiveApprovalReceipt.model_validate_json(path.read_text(encoding="utf-8"))


def _promote(
    registry_service: Any,
    registry: dict,
    candidate: Any,
    manifest: PerspectiveManifest,
    approved_by: str,
) -> PerspectiveApprovalReceipt:
    """Return the promote."""
    context_root = registry_service.context_root(manifest.context_id)
    version = next_major_version(context_root / "versions")
    destination = context_root / "versions" / version
    shutil.copytree(candidate, destination)
    manifest.version = version
    manifest.status = PerspectiveStatus.ACTIVE
    RunStore._atomic_text(destination / "manifest.json", manifest.model_dump_json(indent=2))
    receipt = PerspectiveApprovalReceipt(
        owner_voice_id=registry_service.voice_id,
        context_id=manifest.context_id,
        activated_version=version,
        approved_by=approved_by,
        approved_at=datetime.now(UTC).isoformat(),
        candidate_hash=manifest.candidate_hash,
    )
    RunStore._atomic_text(destination / "approval-receipt.json", receipt.model_dump_json(indent=2))
    lock = {
        "owner_voice_id": registry_service.voice_id,
        "context_id": manifest.context_id,
        "version": version,
        "candidate_hash": manifest.candidate_hash,
        "component_hashes": manifest.component_hashes,
    }
    RunStore._atomic_text(destination / "perspective-lock.json", json.dumps(lock, indent=2))
    registry["contexts"][manifest.context_id] = {
        "display_name": manifest.display_name,
        "status": PerspectiveStatus.ACTIVE.value,
        "active_version": version,
        "candidate_hash": manifest.candidate_hash,
    }
    RunStore._atomic_text(registry_service.registry_path, json.dumps(registry, indent=2))
    return receipt
