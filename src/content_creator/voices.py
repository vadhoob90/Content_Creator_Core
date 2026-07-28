from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .storage import RunStore, slugify


class VoiceError(RuntimeError):
    pass


class VoiceStatus(str, Enum):
    DRAFT = "draft"
    BUILT = "built"
    AWAITING_APPROVAL = "awaiting_approval"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    INACTIVE = "inactive"


class Authorisation(BaseModel):
    confirmed: bool = False
    attested_by: Optional[str] = None
    intended_uses: List[str] = Field(default_factory=list)
    expires_at: Optional[str] = None
    revoked_at: Optional[str] = None


class VoiceWorkOrder(BaseModel):
    display_name: str
    voice_id: str
    authorisation: Authorisation
    urls: List[str] = Field(default_factory=list)
    documents: List[str] = Field(default_factory=list)
    target_audiences: List[str] = Field(default_factory=list)


class AttributionResult(BaseModel):
    classification: str
    confidence: float
    voice_weight: float
    evidence: List[str] = Field(default_factory=list)
    needs_human_review: bool = False


class SourceRecord(BaseModel):
    id: str
    kind: str
    locator: str
    content_hash: str
    title: str
    word_count: int
    attribution: AttributionResult
    approved_for_analysis: bool
    cache_path: str
    error: Optional[str] = None


class VoicePattern(BaseModel):
    id: str
    name: str
    description: str
    status: str
    confidence: float
    supporting_source_ids: List[str]
    counterexample_source_ids: List[str] = Field(default_factory=list)
    mandatory: bool = False


class VoiceManifest(BaseModel):
    schema_version: str = "1.0"
    id: str
    display_name: str
    version: str
    status: VoiceStatus
    candidate_hash: str
    components: Dict[str, str]
    component_hashes: Dict[str, str]
    supported_packs: Dict[str, str]
    authorisation: Authorisation


class VoiceApprovalReceipt(BaseModel):
    voice_id: str
    candidate_version: str
    activated_version: str
    approved_by: str
    approved_at: str
    candidate_hash: str
    evaluation_report_hash: str
    override_reason: Optional[str] = None


def hash_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def hash_json(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


class VoiceRegistry:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.path = self.root / "profiles" / "registry.json"

    def _read(self) -> Dict:
        if not self.path.exists():
            return {"schema_version": "1.0", "profiles": {}}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data.setdefault("schema_version", "1.0")
        data.setdefault("profiles", {})
        return data

    def list(self) -> Dict:
        return self._read()["profiles"]

    def get(self, voice_id: str) -> Dict:
        item = self.list().get(voice_id)
        if not item:
            raise VoiceError("Unknown voice: {}".format(voice_id))
        return item

    def resolve(
        self,
        voice_id: str,
        version: Optional[str] = None,
        allow_inactive: bool = False,
    ) -> Dict:
        if voice_id == "default" and voice_id not in self.list():
            return {
                "id": "default",
                "version": "placeholder",
                "status": "active",
                "path": "profiles/default",
            }
        item = self.get(voice_id)
        resolved_version = version or item.get("active_version")
        if not resolved_version:
            raise VoiceError("Voice {} has no active version".format(voice_id))
        if (
            item.get("status") != VoiceStatus.ACTIVE.value
            and not allow_inactive
        ):
            raise VoiceError("Voice {} is not active".format(voice_id))
        path = self.root / "profiles" / voice_id / "versions" / resolved_version
        if not path.exists():
            raise VoiceError("Missing voice version {}@{}".format(voice_id, resolved_version))
        manifest_path = path / "manifest.json"
        manifest = VoiceManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        for name, filename in manifest.components.items():
            component = path / filename
            if (
                not component.exists()
                or hash_file(component) != manifest.component_hashes.get(name)
            ):
                raise VoiceError(
                    "Active voice component hash mismatch: {}".format(name)
                )
        return {
            "id": voice_id,
            "version": resolved_version,
            "status": item.get("status"),
            "path": str(path.relative_to(self.root)),
            "manifest_hash": hash_file(manifest_path),
        }

    def activate(
        self,
        voice_id: str,
        approved_by: str,
        override_reason: Optional[str] = None,
    ) -> VoiceApprovalReceipt:
        voice_root = self.root / "profiles" / voice_id
        candidate = voice_root / "candidate"
        manifest_path = candidate / "manifest.json"
        evaluation_path = candidate / "evaluation-report.json"
        if not manifest_path.exists():
            raise VoiceError("Voice candidate has not been built")
        manifest = VoiceManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        if not manifest.authorisation.confirmed:
            raise VoiceError("Voice authorisation has not been confirmed")
        for name, filename in manifest.components.items():
            component = candidate / filename
            if (
                not component.exists()
                or hash_file(component) != manifest.component_hashes.get(name)
            ):
                raise VoiceError("Voice component hash mismatch: {}".format(name))
        if manifest.status not in {
            VoiceStatus.AWAITING_APPROVAL,
            VoiceStatus.BUILT,
        }:
            raise VoiceError("Voice candidate is not awaiting approval")
        evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
        if not evaluation.get("passed"):
            if evaluation.get("hard_failures"):
                raise VoiceError("Voice evaluation has non-overridable integrity failures")
            if not override_reason:
                raise VoiceError("Voice evaluation did not pass")

        lock = voice_root / ".activation.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(descriptor)
        except FileExistsError as exc:
            raise VoiceError("Voice activation is already in progress") from exc
        try:
            registry = self._read()
            existing = registry["profiles"].get(voice_id, {})
            if (
                existing.get("candidate_hash") == manifest.candidate_hash
                and existing.get("status") == VoiceStatus.ACTIVE.value
            ):
                receipt_path = (
                    voice_root
                    / "versions"
                    / existing["active_version"]
                    / "approval-receipt.json"
                )
                return VoiceApprovalReceipt.model_validate_json(
                    receipt_path.read_text(encoding="utf-8")
                )
            versions = [
                int(path.name.split(".")[0])
                for path in (voice_root / "versions").glob("*")
                if path.is_dir() and path.name.split(".")[0].isdigit()
            ]
            version = "{}.0.0".format(max(versions, default=0) + 1)
            destination = voice_root / "versions" / version
            shutil.copytree(candidate, destination)
            manifest.version = version
            manifest.status = VoiceStatus.ACTIVE
            RunStore._atomic_text(
                destination / "manifest.json", manifest.model_dump_json(indent=2)
            )
            receipt = VoiceApprovalReceipt(
                voice_id=voice_id,
                candidate_version="candidate",
                activated_version=version,
                approved_by=approved_by,
                approved_at=datetime.now(timezone.utc).isoformat(),
                candidate_hash=manifest.candidate_hash,
                evaluation_report_hash=hash_file(evaluation_path),
                override_reason=override_reason,
            )
            RunStore._atomic_text(
                destination / "approval-receipt.json",
                receipt.model_dump_json(indent=2),
            )
            RunStore._atomic_text(
                destination / "voice-lock.json",
                json.dumps(
                    {
                        "voice_id": voice_id,
                        "version": version,
                        "candidate_hash": manifest.candidate_hash,
                        "component_hashes": manifest.component_hashes,
                    },
                    indent=2,
                ),
            )
            registry["profiles"][voice_id] = {
                "display_name": manifest.display_name,
                "status": VoiceStatus.ACTIVE.value,
                "active_version": version,
                "candidate_hash": manifest.candidate_hash,
            }
            RunStore._atomic_text(self.path, json.dumps(registry, indent=2))
            return receipt
        finally:
            lock.unlink(missing_ok=True)

    def deactivate(self, voice_id: str, reason: str) -> Dict:
        registry = self._read()
        item = registry["profiles"].get(voice_id)
        if not item:
            raise VoiceError("Unknown voice: {}".format(voice_id))
        item["status"] = VoiceStatus.INACTIVE.value
        item["deactivation_reason"] = reason
        item["deactivated_at"] = datetime.now(timezone.utc).isoformat()
        RunStore._atomic_text(self.path, json.dumps(registry, indent=2))
        return item


def voice_id_for(name: str) -> str:
    return slugify(name)
