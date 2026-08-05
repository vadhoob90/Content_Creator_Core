"""Create immutable starter-voice versions from the packaged neutral template."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, List

from .storage import RunStore
from .versioned_artifacts import hash_file, hash_json, next_major_version
from .voice_models import (
    STARTER_TEMPLATE_ID,
    Authorisation,
    VoiceApprovalReceipt,
    VoiceError,
    VoiceManifest,
    VoiceOnboardingRecord,
    VoiceStatus,
    VoiceStrategy,
    save_voice_onboarding,
)


@dataclass(frozen=True)
class StarterVoiceRequest:
    """Represent a starter voice request."""

    voice_id: str
    display_name: str
    author_name: str
    selected_by: str
    intended_uses: List[str]
    template_id: str


def activate_starter(
    registry_service: Any,
    request: StarterVoiceRequest,
) -> dict[str, Any]:
    """Activate starter."""
    if request.template_id != STARTER_TEMPLATE_ID:
        raise VoiceError(f"Unknown starter voice template: {request.template_id}")
    registry = registry_service._read()
    existing = registry["profiles"].get(request.voice_id)
    if existing and existing.get("status") == VoiceStatus.ACTIVE.value:
        return _existing_starter(registry_service, request)
    voice_root = registry_service.root / "profiles" / request.voice_id
    version = next_major_version(voice_root / "versions")
    destination = voice_root / "versions" / version
    destination.mkdir(parents=True, exist_ok=False)
    components, component_hashes, candidate_hash = _write_artifacts(
        destination,
        request.author_name,
    )
    manifest = _write_manifest(
        destination,
        request,
        version,
        components,
        component_hashes,
        candidate_hash,
    )
    activated_at = _write_receipt(
        destination, request.voice_id, request.selected_by, version, candidate_hash
    )
    _update_registry(
        registry_service,
        registry,
        request.voice_id,
        request.display_name,
        version,
        candidate_hash,
        request.template_id,
    )
    _record_onboarding(
        registry_service.root,
        request.voice_id,
        request.display_name,
        request.author_name,
        request.selected_by,
        request.template_id,
        activated_at,
    )
    memory = voice_root / "learnings" / "memory.json"
    if not memory.exists():
        RunStore._atomic_text(memory, json.dumps({"version": 1, "records": []}, indent=2))
    return registry_service.resolve(manifest.id)


def _existing_starter(
    registry_service: Any,
    request: StarterVoiceRequest,
) -> dict[str, Any]:
    """Return the existing starter."""
    resolved = registry_service.resolve(request.voice_id)
    if resolved["strategy"] != VoiceStrategy.STARTER.value:
        raise VoiceError(f"Voice {request.voice_id} already has an active source-derived version")
    _record_onboarding(
        registry_service.root,
        request.voice_id,
        request.display_name,
        request.author_name,
        request.selected_by,
        request.template_id,
        datetime.now(UTC).isoformat(),
    )
    return resolved


def _write_artifacts(destination: Path, author_name: str) -> tuple[dict, dict, str]:
    """Write artifacts."""
    template = (
        Path(__file__).with_name("resources") / "profiles" / "starter" / "clear-professional.md"
    )
    profile = template.read_text(encoding="utf-8").replace("{{author_name}}", author_name)
    constraints = {
        "starter_voice": True,
        "never_claim_personalisation": True,
        "never_invent_personal_context": True,
        "never_invent_author_positions": True,
        "perspectives_allowed": False,
    }
    rubric = {
        "minimums": {"clarity": 8, "personal_integrity": 10, "non_imitation": 10},
        "hard_gates": [
            "unsupported_personal_context",
            "invented_author_position",
            "claimed_personalisation",
        ],
    }
    evaluation = {
        "schema_version": "1.0",
        "passed": True,
        "hard_failures": [],
        "checks": {
            "template_integrity": True,
            "author_evidence": "not_supplied",
            "personalisation_claim": False,
            "perspectives_allowed": False,
        },
    }
    artifacts = {
        "profile.md": profile,
        "constraints.json": json.dumps(constraints, indent=2),
        "voice-rubric.json": json.dumps(rubric, indent=2),
        "source-index.json": "[]",
        "patterns.json": "[]",
        "evaluation-report.json": json.dumps(evaluation, indent=2),
    }
    for filename, contents in artifacts.items():
        RunStore._atomic_text(destination / filename, contents)
    components = {
        "profile": "profile.md",
        "constraints": "constraints.json",
        "rubric": "voice-rubric.json",
        "sources": "source-index.json",
        "patterns": "patterns.json",
        "evaluation_report": "evaluation-report.json",
    }
    component_hashes = {
        name: hash_file(destination / filename) for name, filename in components.items()
    }
    return components, component_hashes, hash_json(component_hashes)


def _write_manifest(
    destination: Path,
    request: StarterVoiceRequest,
    version: str,
    components: dict,
    component_hashes: dict,
    candidate_hash: str,
) -> VoiceManifest:
    """Write manifest."""
    manifest = VoiceManifest(
        id=request.voice_id,
        display_name=request.display_name,
        author_name=request.author_name,
        version=version,
        status=VoiceStatus.ACTIVE,
        candidate_hash=candidate_hash,
        components=components,
        component_hashes=component_hashes,
        supported_packs={pack: "starter" for pack in request.intended_uses},
        authorisation=Authorisation(
            confirmed=True,
            attested_by=request.selected_by,
            intended_uses=request.intended_uses,
        ),
        strategy=VoiceStrategy.STARTER,
        evidence_status="none",
        perspectives_allowed=False,
        template_id=request.template_id,
    )
    RunStore._atomic_text(destination / "manifest.json", manifest.model_dump_json(indent=2))
    return manifest


def _write_receipt(
    destination: Path,
    voice_id: str,
    selected_by: str,
    version: str,
    candidate_hash: str,
) -> str:
    """Write receipt."""
    activated_at = datetime.now(UTC).isoformat()
    receipt = VoiceApprovalReceipt(
        voice_id=voice_id,
        candidate_version="starter-template",
        activated_version=version,
        approved_by=selected_by,
        approved_at=activated_at,
        candidate_hash=candidate_hash,
        evaluation_report_hash=hash_file(destination / "evaluation-report.json"),
    )
    RunStore._atomic_text(destination / "approval-receipt.json", receipt.model_dump_json(indent=2))
    lock = {
        "voice_id": voice_id,
        "version": version,
        "candidate_hash": candidate_hash,
        "component_hashes": VoiceManifest.model_validate_json(
            (destination / "manifest.json").read_text()
        ).component_hashes,
        "strategy": VoiceStrategy.STARTER.value,
        "template_id": STARTER_TEMPLATE_ID,
    }
    RunStore._atomic_text(destination / "voice-lock.json", json.dumps(lock, indent=2))
    return activated_at


def _update_registry(
    registry_service: Any,
    registry: dict,
    voice_id: str,
    display_name: str,
    version: str,
    candidate_hash: str,
    template_id: str,
) -> None:
    """Update registry."""
    registry["profiles"][voice_id] = {
        "display_name": display_name,
        "status": VoiceStatus.ACTIVE.value,
        "active_version": version,
        "candidate_hash": candidate_hash,
        "strategy": VoiceStrategy.STARTER.value,
        "evidence_status": "none",
        "perspectives_allowed": False,
        "template_id": template_id,
    }
    RunStore._atomic_text(registry_service.path, json.dumps(registry, indent=2))


def _record_onboarding(
    root: Path,
    voice_id: str,
    display_name: str,
    author_name: str,
    selected_by: str,
    template_id: str,
    activated_at: str,
) -> None:
    """Record onboarding."""
    save_voice_onboarding(
        root,
        VoiceOnboardingRecord(
            voice_id=voice_id,
            display_name=display_name,
            author_name=author_name,
            status="starter-active",
            strategy=VoiceStrategy.STARTER,
            template_id=template_id,
            selected_by=selected_by,
            selected_at=activated_at,
            perspective_mode="disabled",
            perspective_disabled_reason="starter-voice-without-author-evidence",
        ),
    )
