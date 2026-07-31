from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .storage import RunStore, slugify

STARTER_TEMPLATE_ID = "clear-professional"


class VoiceError(RuntimeError):
    pass


class VoiceStrategy(str, Enum):
    SOURCE_DERIVED = "source-derived"
    STARTER = "starter"


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
    author_name: Optional[str] = None
    author_aliases: List[str] = Field(default_factory=list)
    authorisation: Authorisation
    urls: List[str] = Field(default_factory=list)
    documents: List[str] = Field(default_factory=list)
    target_audiences: List[str] = Field(default_factory=list)
    strategy: VoiceStrategy = VoiceStrategy.SOURCE_DERIVED
    template_id: Optional[str] = None

    @property
    def attribution_name(self) -> str:
        return self.author_name or self.display_name


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
    analysis_word_count: Optional[int] = None
    analysis_scope: str = "full-source"
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
    category: str = "uncategorised"
    observation: Optional[str] = None
    communicative_function: Optional[str] = None
    contexts: Dict[str, List[str]] = Field(default_factory=dict)
    generation_guidance: Optional[str] = None
    anti_pattern: Optional[str] = None
    linguistic_evidence: Dict[str, Any] = Field(default_factory=dict)


class VoiceManifest(BaseModel):
    schema_version: str = "1.0"
    id: str
    display_name: str
    author_name: Optional[str] = None
    author_aliases: List[str] = Field(default_factory=list)
    version: str
    status: VoiceStatus
    candidate_hash: str
    components: Dict[str, str]
    component_hashes: Dict[str, str]
    supported_packs: Dict[str, str]
    authorisation: Authorisation
    strategy: VoiceStrategy = VoiceStrategy.SOURCE_DERIVED
    evidence_status: str = "author-sources"
    perspectives_allowed: bool = True
    template_id: Optional[str] = None


class VoiceOnboardingRecord(BaseModel):
    schema_version: str = "1.0"
    voice_id: str
    display_name: str
    author_name: str
    status: str = "undecided"
    strategy: Optional[VoiceStrategy] = None
    template_id: Optional[str] = None
    selected_by: Optional[str] = None
    selected_at: Optional[str] = None
    perspective_mode: str = "pending"
    perspective_disabled_reason: Optional[str] = None


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


def onboarding_path(root: Path, voice_id: str) -> Path:
    return root.resolve() / "profiles" / voice_id / "onboarding.json"


def load_voice_onboarding(root: Path, voice_id: str) -> Optional[VoiceOnboardingRecord]:
    path = onboarding_path(root, voice_id)
    if not path.exists():
        return None
    return VoiceOnboardingRecord.model_validate_json(path.read_text(encoding="utf-8"))


def save_voice_onboarding(root: Path, record: VoiceOnboardingRecord) -> Path:
    path = onboarding_path(root, record.voice_id)
    RunStore._atomic_text(path, record.model_dump_json(indent=2))
    return path


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
            workspace_onboarding = sorted((self.root / "profiles").glob("*/onboarding.json"))
            if workspace_onboarding:
                intended = [
                    VoiceOnboardingRecord.model_validate_json(
                        path.read_text(encoding="utf-8")
                    ).voice_id
                    for path in workspace_onboarding
                ]
                raise VoiceError(
                    "The default test profile is unavailable in an author "
                    "workspace; complete onboarding and select: {}".format(", ".join(intended))
                )
            return {
                "id": "default",
                "version": "placeholder",
                "status": "active",
                "path": "profiles/default",
                "strategy": "legacy-placeholder",
                "evidence_status": "none",
                "perspectives_allowed": True,
            }
        onboarding = load_voice_onboarding(self.root, voice_id)
        if onboarding and onboarding.status == "undecided":
            raise VoiceError(
                "Voice onboarding decision required for {}: choose starter "
                "or source-derived".format(voice_id)
            )
        if onboarding and onboarding.status == "collecting-sources" and voice_id not in self.list():
            raise VoiceError(
                "Source-derived onboarding for {} is not complete; build, "
                "review, and approve the candidate voice".format(voice_id)
            )
        item = self.get(voice_id)
        resolved_version = version or item.get("active_version")
        if not resolved_version:
            raise VoiceError("Voice {} has no active version".format(voice_id))
        if item.get("status") != VoiceStatus.ACTIVE.value and not allow_inactive:
            raise VoiceError("Voice {} is not active".format(voice_id))
        path = self.root / "profiles" / voice_id / "versions" / resolved_version
        if not path.exists():
            raise VoiceError("Missing voice version {}@{}".format(voice_id, resolved_version))
        manifest_path = path / "manifest.json"
        manifest = VoiceManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        if item.get("status") == VoiceStatus.ACTIVE.value and manifest.status != VoiceStatus.ACTIVE:
            raise VoiceError(
                "Voice lifecycle mismatch: registry is active but version manifest is {}".format(
                    manifest.status.value
                )
            )
        for name, filename in manifest.components.items():
            component = path / filename
            if not component.exists() or hash_file(component) != manifest.component_hashes.get(
                name
            ):
                raise VoiceError("Active voice component hash mismatch: {}".format(name))
        return {
            "id": voice_id,
            "version": resolved_version,
            "status": item.get("status"),
            "version_status": manifest.status.value,
            "lifecycle_authority": "version_manifest",
            "path": str(path.relative_to(self.root)),
            "manifest_hash": hash_file(manifest_path),
            "strategy": manifest.strategy.value,
            "evidence_status": manifest.evidence_status,
            "perspectives_allowed": manifest.perspectives_allowed,
            "template_id": manifest.template_id,
        }

    def activate_starter(
        self,
        voice_id: str,
        display_name: str,
        author_name: str,
        selected_by: str,
        intended_uses: List[str],
        template_id: str = STARTER_TEMPLATE_ID,
    ) -> Dict[str, Any]:
        if template_id != STARTER_TEMPLATE_ID:
            raise VoiceError("Unknown starter voice template: {}".format(template_id))
        registry = self._read()
        existing = registry["profiles"].get(voice_id)
        if existing and existing.get("status") == VoiceStatus.ACTIVE.value:
            resolved = self.resolve(voice_id)
            if resolved["strategy"] != VoiceStrategy.STARTER.value:
                raise VoiceError(
                    "Voice {} already has an active source-derived version".format(voice_id)
                )
            save_voice_onboarding(
                self.root,
                VoiceOnboardingRecord(
                    voice_id=voice_id,
                    display_name=display_name,
                    author_name=author_name,
                    status="starter-active",
                    strategy=VoiceStrategy.STARTER,
                    template_id=template_id,
                    selected_by=selected_by,
                    selected_at=datetime.now(UTC).isoformat(),
                    perspective_mode="disabled",
                    perspective_disabled_reason=("starter-voice-without-author-evidence"),
                ),
            )
            return resolved

        voice_root = self.root / "profiles" / voice_id
        versions = [
            int(path.name.split(".")[0])
            for path in (voice_root / "versions").glob("*")
            if path.is_dir() and path.name.split(".")[0].isdigit()
        ]
        version = "{}.0.0".format(max(versions, default=0) + 1)
        destination = voice_root / "versions" / version
        destination.mkdir(parents=True, exist_ok=False)
        template = (
            Path(__file__).with_name("resources") / "profiles" / "starter" / "clear-professional.md"
        )
        profile = template.read_text(encoding="utf-8").replace(
            "{{author_name}}",
            author_name,
        )
        constraints = {
            "starter_voice": True,
            "never_claim_personalisation": True,
            "never_invent_personal_context": True,
            "never_invent_author_positions": True,
            "perspectives_allowed": False,
        }
        rubric = {
            "minimums": {
                "clarity": 8,
                "personal_integrity": 10,
                "non_imitation": 10,
            },
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
        for filename, content in artifacts.items():
            RunStore._atomic_text(destination / filename, content)
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
        candidate_hash = hash_json(component_hashes)
        authorisation = Authorisation(
            confirmed=True,
            attested_by=selected_by,
            intended_uses=intended_uses,
        )
        manifest = VoiceManifest(
            id=voice_id,
            display_name=display_name,
            author_name=author_name,
            version=version,
            status=VoiceStatus.ACTIVE,
            candidate_hash=candidate_hash,
            components=components,
            component_hashes=component_hashes,
            supported_packs={item: "starter" for item in intended_uses},
            authorisation=authorisation,
            strategy=VoiceStrategy.STARTER,
            evidence_status="none",
            perspectives_allowed=False,
            template_id=template_id,
        )
        RunStore._atomic_text(
            destination / "manifest.json",
            manifest.model_dump_json(indent=2),
        )
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
                    "candidate_hash": candidate_hash,
                    "component_hashes": component_hashes,
                    "strategy": VoiceStrategy.STARTER.value,
                    "template_id": template_id,
                },
                indent=2,
            ),
        )
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
        RunStore._atomic_text(self.path, json.dumps(registry, indent=2))
        save_voice_onboarding(
            self.root,
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
                perspective_disabled_reason=("starter-voice-without-author-evidence"),
            ),
        )
        memory = voice_root / "learnings" / "memory.json"
        if not memory.exists():
            RunStore._atomic_text(
                memory,
                json.dumps({"version": 1, "records": []}, indent=2),
            )
        return self.resolve(voice_id)

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
        manifest = VoiceManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        if not manifest.authorisation.confirmed:
            raise VoiceError("Voice authorisation has not been confirmed")
        for name, filename in manifest.components.items():
            component = candidate / filename
            if not component.exists() or hash_file(component) != manifest.component_hashes.get(
                name
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
                    voice_root / "versions" / existing["active_version"] / "approval-receipt.json"
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
            RunStore._atomic_text(destination / "manifest.json", manifest.model_dump_json(indent=2))
            receipt = VoiceApprovalReceipt(
                voice_id=voice_id,
                candidate_version="candidate",
                activated_version=version,
                approved_by=approved_by,
                approved_at=datetime.now(UTC).isoformat(),
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
                "strategy": manifest.strategy.value,
                "evidence_status": manifest.evidence_status,
                "perspectives_allowed": manifest.perspectives_allowed,
                "template_id": manifest.template_id,
            }
            RunStore._atomic_text(self.path, json.dumps(registry, indent=2))
            onboarding = load_voice_onboarding(self.root, voice_id)
            if onboarding:
                onboarding.status = "source-derived-active"
                onboarding.strategy = VoiceStrategy.SOURCE_DERIVED
                onboarding.template_id = None
                onboarding.perspective_mode = "workspace-policy"
                onboarding.perspective_disabled_reason = None
                save_voice_onboarding(self.root, onboarding)
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
        item["deactivated_at"] = datetime.now(UTC).isoformat()
        RunStore._atomic_text(self.path, json.dumps(registry, indent=2))
        return item


def voice_id_for(name: str) -> str:
    return slugify(name)
