from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from .domain import PerspectiveMode, PerspectiveSelection, WorkOrder
from .storage import RunStore, slugify
from .voices import VoiceRegistry, hash_file, hash_json


class PerspectiveError(RuntimeError):
    pass


class PerspectiveStatus(str, Enum):
    CANDIDATE = "candidate"
    AWAITING_APPROVAL = "awaiting_approval"
    ACTIVE = "active"
    INACTIVE = "inactive"


class PerspectiveEntryStatus(str, Enum):
    APPROVED = "approved"
    SUPERSEDED = "superseded"
    RETIRED = "retired"


class PerspectiveChangeType(str, Enum):
    NEW = "new"
    QUALIFY = "qualify"
    REPLACE = "replace"
    SUPERSEDE = "supersede"


class PerspectiveProvenance(BaseModel):
    kind: str
    reference: str
    excerpt: Optional[str] = None


class PerspectiveEntry(BaseModel):
    id: str = Field(default_factory=lambda: "perspective-" + uuid4().hex[:12])
    type: str = "position"
    statement: str
    topics: List[str] = Field(default_factory=list)
    qualifications: List[str] = Field(default_factory=list)
    counterpositions: List[str] = Field(default_factory=list)
    provenance: List[PerspectiveProvenance] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0, le=1)
    status: PerspectiveEntryStatus = PerspectiveEntryStatus.APPROVED
    supersedes: Optional[str] = None


class PerspectiveManifest(BaseModel):
    schema_version: str = "1.0"
    owner_voice_id: str
    context_id: str
    display_name: str
    version: str = "candidate"
    status: PerspectiveStatus
    candidate_hash: str
    components: Dict[str, str]
    component_hashes: Dict[str, str]


class PerspectiveApprovalReceipt(BaseModel):
    owner_voice_id: str
    context_id: str
    activated_version: str
    approved_by: str
    approved_at: str
    candidate_hash: str


class PerspectiveProposalCandidate(BaseModel):
    change_type: PerspectiveChangeType = PerspectiveChangeType.NEW
    type: str = "position"
    statement: str
    topics: List[str] = Field(default_factory=list)
    qualifications: List[str] = Field(default_factory=list)
    counterpositions: List[str] = Field(default_factory=list)
    evidence: str
    confidence: float = Field(default=0.7, ge=0, le=1)
    target_entry_id: Optional[str] = None


class PerspectiveExtraction(BaseModel):
    candidates: List[PerspectiveProposalCandidate] = Field(default_factory=list)
    author_signal: str = "publication_approval"


class PerspectiveCatalogueEntry(BaseModel):
    context_id: str
    display_name: str
    summary: str
    use_when: List[str] = Field(default_factory=list)
    avoid_when: List[str] = Field(default_factory=list)
    related_contexts: List[str] = Field(default_factory=list)


class PerspectiveCatalogue(BaseModel):
    schema_version: str = "1.0"
    routing_only: bool = True
    contexts: List[PerspectiveCatalogueEntry] = Field(default_factory=list)


class PerspectiveResolution(BaseModel):
    mode: PerspectiveMode = PerspectiveMode.AUTOMATIC
    selected: List[PerspectiveSelection] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    disabled_reason: Optional[str] = None


class PerspectiveCatalogueStore:
    def __init__(self, root: Path, voice_id: str):
        self.root = root.resolve()
        self.voice_id = voice_id
        self.registry = PerspectiveRegistry(self.root, voice_id)
        self.path = self.registry.base / "catalogue.json"

    def load(self) -> PerspectiveCatalogue:
        if not self.path.exists():
            return PerspectiveCatalogue()
        catalogue = PerspectiveCatalogue.model_validate_json(self.path.read_text(encoding="utf-8"))
        context_ids = [item.context_id for item in catalogue.contexts]
        if len(context_ids) != len(set(context_ids)):
            raise PerspectiveError("Perspective catalogue context ids must be unique")
        invalid = sorted(
            context_id for context_id in context_ids if slugify(context_id) != context_id
        )
        if invalid:
            raise PerspectiveError(
                "Perspective catalogue contains invalid context ids: {}".format(", ".join(invalid))
            )
        return catalogue

    def routing_payload(self) -> Dict[str, Any]:
        catalogue = self.load()
        active = self.registry.list()
        contexts = [
            item.model_dump(mode="json")
            for item in catalogue.contexts
            if active.get(item.context_id, {}).get("status") == PerspectiveStatus.ACTIVE.value
        ]
        return {
            "schema_version": catalogue.schema_version,
            "routing_only": True,
            "contexts": contexts,
        }

    def verify(self) -> Dict[str, Any]:
        catalogue = self.load()
        registry = self.registry.list()
        unknown = sorted(
            item.context_id for item in catalogue.contexts if item.context_id not in registry
        )
        inactive = sorted(
            item.context_id
            for item in catalogue.contexts
            if item.context_id in registry
            and registry[item.context_id].get("status") != PerspectiveStatus.ACTIVE.value
        )
        return {
            "voice_id": self.voice_id,
            "valid": not unknown and not inactive,
            "unknown_contexts": unknown,
            "inactive_contexts": inactive,
            "context_count": len(catalogue.contexts),
        }


class PerspectiveResolver:
    def __init__(self, root: Path, runner):
        self.root = root.resolve()
        self.runner = runner

    def resolve(
        self,
        order: WorkOrder,
        policy: Dict[str, Any],
    ) -> PerspectiveResolution:
        forced_disabled_reason = policy.get("force_disabled_reason")
        mode = (
            PerspectiveMode.DISABLED
            if forced_disabled_reason
            else order.perspective_mode or PerspectiveMode(policy["mode"])
        )
        if mode == PerspectiveMode.DISABLED:
            if order.perspective_selections:
                raise PerspectiveError(
                    "Perspective contexts cannot be supplied when perspective use "
                    "is disabled{}".format(
                        ": {}".format(forced_disabled_reason) if forced_disabled_reason else ""
                    )
                )
            return PerspectiveResolution(
                mode=mode,
                disabled_reason=forced_disabled_reason,
            )
        if order.perspective_selections:
            return PerspectiveResolution(
                mode=PerspectiveMode.EXPLICIT,
                selected=order.perspective_selections,
            )
        if mode == PerspectiveMode.EXPLICIT:
            return PerspectiveResolution(mode=mode)
        catalogue = PerspectiveCatalogueStore(self.root, order.voice_id).routing_payload()
        if not catalogue["contexts"]:
            return PerspectiveResolution(mode=mode)
        resolution = self.runner.run(
            role="briefing-agent",
            role_key="briefing-agent",
            instruction=(
                "Select zero, one, or more relevant perspective contexts from the "
                "routing-only catalogue. Use only listed context ids. Catalogue "
                "summaries are routing metadata, not author positions. Select no "
                "context for neutral content. Ask one focused question only when "
                "ambiguity would materially change the argument."
            ),
            payload={
                "work_order": order.model_dump(mode="json"),
                "perspective_catalogue": catalogue,
                "allow_multiple": bool(policy.get("allow_multiple")),
                "ask_when_ambiguous": bool(policy.get("ask_when_ambiguous")),
            },
            order=order,
            output_model=PerspectiveResolution,
            provider=order.provider,
        )
        resolution.mode = mode
        allowed = {item["context_id"] for item in catalogue["contexts"]}
        selected_ids = [item.context_id for item in resolution.selected]
        if len(selected_ids) != len(set(selected_ids)):
            raise PerspectiveError("Perspective resolver selected duplicate contexts")
        invalid = sorted(
            item.context_id for item in resolution.selected if item.context_id not in allowed
        )
        if invalid:
            raise PerspectiveError(
                "Perspective resolver selected unavailable contexts: {}".format(", ".join(invalid))
            )
        if not policy.get("allow_multiple") and len(resolution.selected) > 1:
            raise PerspectiveError(
                "Perspective resolver selected multiple contexts but allow_multiple is false"
            )
        if resolution.needs_clarification and not policy.get("ask_when_ambiguous"):
            resolution.needs_clarification = False
            resolution.clarification_question = None
            resolution.selected = []
        return resolution


class PerspectiveProposal(PerspectiveProposalCandidate):
    id: str = Field(default_factory=lambda: "proposal-" + uuid4().hex[:12])
    owner_voice_id: str
    context_id: str
    run_id: str
    status: str = "candidate"
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class PerspectiveRegistry:
    def __init__(self, root: Path, voice_id: str):
        self.root = root.resolve()
        self.voice_id = slugify(voice_id)
        if self.voice_id != voice_id:
            raise PerspectiveError("Voice ids must use lowercase letters, digits, and hyphens")
        self.base = self.root / "profiles" / self.voice_id / "perspectives"
        self.registry_path = self.base / "registry.json"

    def _read(self) -> Dict:
        if not self.registry_path.exists():
            return {"schema_version": "1.0", "contexts": {}}
        data = json.loads(self.registry_path.read_text(encoding="utf-8"))
        data.setdefault("schema_version", "1.0")
        data.setdefault("contexts", {})
        return data

    def list(self) -> Dict:
        return self._read()["contexts"]

    def context_root(self, context_id: str) -> Path:
        context = slugify(context_id)
        if context != context_id:
            raise PerspectiveError(
                "Perspective context ids must use lowercase letters, digits, and hyphens"
            )
        return self.base / context

    def stage(
        self,
        context_id: str,
        entries: List[PerspectiveEntry],
        display_name: Optional[str] = None,
    ) -> PerspectiveManifest:
        VoiceRegistry(self.root).resolve(self.voice_id)
        context_root = self.context_root(context_id)
        staging = context_root / ".candidate-staging"
        candidate = context_root / "candidate"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)

        entry_ids = [entry.id for entry in entries]
        if len(entry_ids) != len(set(entry_ids)):
            raise PerspectiveError("Perspective entry ids must be unique")
        known = set(entry_ids)
        for entry in entries:
            if entry.status == PerspectiveEntryStatus.APPROVED and not entry.provenance:
                raise PerspectiveError(
                    "Approved perspective entries require provenance: {}".format(entry.id)
                )
            if entry.supersedes and entry.supersedes not in known:
                raise PerspectiveError(
                    "Perspective entry {} supersedes an unknown entry".format(entry.id)
                )

        RunStore._atomic_text(
            staging / "entries.json",
            json.dumps(
                [entry.model_dump(mode="json") for entry in entries],
                indent=2,
                ensure_ascii=False,
            ),
        )
        RunStore._atomic_text(
            staging / "perspective.md",
            self.render_profile(context_id, entries),
        )
        RunStore._atomic_text(
            staging / "constraints.json",
            json.dumps(
                {
                    "perspective_is_not_factual_authority": True,
                    "never_extrapolate_unrecorded_positions": True,
                    "preserve_qualifications": True,
                    "do_not_use_retired_or_superseded_entries": True,
                    "context_inheritance": "none",
                },
                indent=2,
            ),
        )
        active_entries = [
            entry for entry in entries if entry.status == PerspectiveEntryStatus.APPROVED
        ]
        evaluation = {
            "schema_version": "1.0",
            "passed": all(entry.provenance for entry in active_entries),
            "checks": {
                "all_active_entries_have_provenance": all(
                    entry.provenance for entry in active_entries
                ),
                "entry_ids_unique": len(entry_ids) == len(set(entry_ids)),
                "cross_context_inheritance": False,
                "empty_context_permitted": True,
            },
            "hard_failures": [],
        }
        RunStore._atomic_text(
            staging / "evaluation-report.json",
            json.dumps(evaluation, indent=2),
        )
        components = {
            "profile": "perspective.md",
            "entries": "entries.json",
            "constraints": "constraints.json",
            "evaluation_report": "evaluation-report.json",
        }
        component_hashes = {
            name: hash_file(staging / filename) for name, filename in components.items()
        }
        manifest = PerspectiveManifest(
            owner_voice_id=self.voice_id,
            context_id=context_id,
            display_name=display_name or context_id.replace("-", " ").title(),
            status=PerspectiveStatus.AWAITING_APPROVAL,
            candidate_hash=hash_json(component_hashes),
            components=components,
            component_hashes=component_hashes,
        )
        RunStore._atomic_text(
            staging / "manifest.json",
            manifest.model_dump_json(indent=2),
        )

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
        return manifest

    def resolve(
        self,
        context_id: str,
        version: Optional[str] = None,
        allow_inactive: bool = False,
    ) -> Dict:
        item = self.list().get(context_id)
        if not item:
            raise PerspectiveError(
                "Unknown perspective context {} for voice {}".format(context_id, self.voice_id)
            )
        resolved_version = version or item.get("active_version")
        if not resolved_version:
            raise PerspectiveError(
                "Perspective context {} has no active version".format(context_id)
            )
        if item.get("status") != PerspectiveStatus.ACTIVE.value and not allow_inactive:
            raise PerspectiveError("Perspective context {} is not active".format(context_id))
        path = self.context_root(context_id) / "versions" / resolved_version
        manifest_path = path / "manifest.json"
        if not manifest_path.exists():
            raise PerspectiveError(
                "Missing perspective version {}@{}".format(context_id, resolved_version)
            )
        manifest = PerspectiveManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        for name, filename in manifest.components.items():
            component = path / filename
            if not component.exists() or hash_file(component) != manifest.component_hashes.get(
                name
            ):
                raise PerspectiveError(
                    "Active perspective component hash mismatch: {}".format(name)
                )
        entries = json.loads((path / manifest.components["entries"]).read_text())
        return {
            "owner_voice_id": self.voice_id,
            "context_id": context_id,
            "version": resolved_version,
            "status": item.get("status"),
            "path": str(path.relative_to(self.root)),
            "manifest_hash": hash_file(manifest_path),
            "active_entry_ids": [
                entry["id"]
                for entry in entries
                if entry.get("status") == PerspectiveEntryStatus.APPROVED.value
            ],
        }

    def activate(
        self,
        context_id: str,
        approved_by: str,
    ) -> PerspectiveApprovalReceipt:
        VoiceRegistry(self.root).resolve(self.voice_id)
        context_root = self.context_root(context_id)
        candidate = context_root / "candidate"
        manifest_path = candidate / "manifest.json"
        if not manifest_path.exists():
            raise PerspectiveError("Perspective candidate has not been created")
        manifest = PerspectiveManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        for name, filename in manifest.components.items():
            component = candidate / filename
            if not component.exists() or hash_file(component) != manifest.component_hashes.get(
                name
            ):
                raise PerspectiveError("Perspective component hash mismatch: {}".format(name))
        evaluation = json.loads((candidate / manifest.components["evaluation_report"]).read_text())
        if not evaluation.get("passed"):
            raise PerspectiveError("Perspective evaluation did not pass")

        lock = context_root / ".activation.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(descriptor)
        except FileExistsError as exc:
            raise PerspectiveError("Perspective activation is already in progress") from exc
        try:
            registry = self._read()
            existing = registry["contexts"].get(context_id, {})
            if (
                existing.get("candidate_hash") == manifest.candidate_hash
                and existing.get("status") == PerspectiveStatus.ACTIVE.value
            ):
                receipt_path = (
                    context_root / "versions" / existing["active_version"] / "approval-receipt.json"
                )
                return PerspectiveApprovalReceipt.model_validate_json(
                    receipt_path.read_text(encoding="utf-8")
                )
            versions = [
                int(path.name.split(".")[0])
                for path in (context_root / "versions").glob("*")
                if path.is_dir() and path.name.split(".")[0].isdigit()
            ]
            version = "{}.0.0".format(max(versions, default=0) + 1)
            destination = context_root / "versions" / version
            shutil.copytree(candidate, destination)
            manifest.version = version
            manifest.status = PerspectiveStatus.ACTIVE
            RunStore._atomic_text(
                destination / "manifest.json",
                manifest.model_dump_json(indent=2),
            )
            receipt = PerspectiveApprovalReceipt(
                owner_voice_id=self.voice_id,
                context_id=context_id,
                activated_version=version,
                approved_by=approved_by,
                approved_at=datetime.now(UTC).isoformat(),
                candidate_hash=manifest.candidate_hash,
            )
            RunStore._atomic_text(
                destination / "approval-receipt.json",
                receipt.model_dump_json(indent=2),
            )
            RunStore._atomic_text(
                destination / "perspective-lock.json",
                json.dumps(
                    {
                        "owner_voice_id": self.voice_id,
                        "context_id": context_id,
                        "version": version,
                        "candidate_hash": manifest.candidate_hash,
                        "component_hashes": manifest.component_hashes,
                    },
                    indent=2,
                ),
            )
            registry["contexts"][context_id] = {
                "display_name": manifest.display_name,
                "status": PerspectiveStatus.ACTIVE.value,
                "active_version": version,
                "candidate_hash": manifest.candidate_hash,
            }
            RunStore._atomic_text(
                self.registry_path,
                json.dumps(registry, indent=2),
            )
            return receipt
        finally:
            lock.unlink(missing_ok=True)

    def deactivate(self, context_id: str, reason: str) -> Dict:
        registry = self._read()
        item = registry["contexts"].get(context_id)
        if not item:
            raise PerspectiveError("Unknown perspective context: {}".format(context_id))
        item["status"] = PerspectiveStatus.INACTIVE.value
        item["deactivation_reason"] = reason
        item["deactivated_at"] = datetime.now(UTC).isoformat()
        RunStore._atomic_text(
            self.registry_path,
            json.dumps(registry, indent=2),
        )
        return item

    def current_entries(self, context_id: str) -> List[PerspectiveEntry]:
        resolved = self.resolve(context_id)
        path = self.root / resolved["path"] / "entries.json"
        return [
            PerspectiveEntry.model_validate(item)
            for item in json.loads(path.read_text(encoding="utf-8"))
        ]

    def stage_proposal(self, context_id: str, proposal_id: str) -> PerspectiveManifest:
        proposal_path = self.context_root(context_id) / "proposals" / (proposal_id + ".json")
        if not proposal_path.exists():
            raise PerspectiveError("Unknown perspective proposal: {}".format(proposal_id))
        proposal = PerspectiveProposal.model_validate_json(
            proposal_path.read_text(encoding="utf-8")
        )
        if proposal.status != "candidate":
            raise PerspectiveError("Perspective proposal is not available")
        entries = self.current_entries(context_id)
        known = {entry.id: entry for entry in entries}
        if proposal.change_type in {"replace", "qualify", "supersede"}:
            if not proposal.target_entry_id or proposal.target_entry_id not in known:
                raise PerspectiveError("Perspective proposal requires a valid target entry")
            known[proposal.target_entry_id].status = PerspectiveEntryStatus.SUPERSEDED
        entry = PerspectiveEntry(
            id="perspective-" + proposal.id.removeprefix("proposal-"),
            type=proposal.type,
            statement=proposal.statement,
            topics=proposal.topics,
            qualifications=proposal.qualifications,
            counterpositions=proposal.counterpositions,
            provenance=[
                PerspectiveProvenance(
                    kind="published_run",
                    reference=proposal.run_id,
                    excerpt=proposal.evidence,
                )
            ],
            confidence=proposal.confidence,
            supersedes=proposal.target_entry_id,
        )
        entries.append(entry)
        proposal.status = "staged"
        RunStore._atomic_text(
            proposal_path,
            proposal.model_dump_json(indent=2),
        )
        return self.stage(context_id, entries)

    def retire_entry(
        self,
        context_id: str,
        entry_id: str,
        reason: str,
    ) -> PerspectiveManifest:
        entries = self.current_entries(context_id)
        target = next((entry for entry in entries if entry.id == entry_id), None)
        if not target:
            raise PerspectiveError("Unknown perspective entry: {}".format(entry_id))
        target.status = PerspectiveEntryStatus.RETIRED
        target.qualifications.append("Retired: {}".format(reason))
        return self.stage(context_id, entries)

    @staticmethod
    def render_profile(context_id: str, entries: List[PerspectiveEntry]) -> str:
        lines = [
            "# Perspective Context: {}".format(context_id),
            "",
            "These are approved author positions, not factual authorities.",
            "Use only entries relevant to the current brief. Preserve qualifications,",
            "surface research conflicts, and never extrapolate an unrecorded position.",
            "",
            "## Approved entries",
        ]
        active = [entry for entry in entries if entry.status == PerspectiveEntryStatus.APPROVED]
        if not active:
            lines.append("- No reusable perspective has been approved for this context.")
        for entry in active:
            lines.extend(
                [
                    "- **{} [{}]**: {}".format(entry.id, entry.type, entry.statement),
                    "  - Topics: {}".format(
                        ", ".join(entry.topics) if entry.topics else "context-wide"
                    ),
                    "  - Qualifications: {}".format(
                        "; ".join(entry.qualifications) if entry.qualifications else "none"
                    ),
                    "  - Counterpositions: {}".format(
                        "; ".join(entry.counterpositions)
                        if entry.counterpositions
                        else "none recorded"
                    ),
                ]
            )
        return "\n".join(lines)


class PerspectiveProposalStore:
    def __init__(self, root: Path, voice_id: str, context_id: str):
        self.root = root.resolve()
        self.voice_id = voice_id
        self.context_id = context_id
        self.path = self.root / "profiles" / voice_id / "perspectives" / context_id / "proposals"

    def apply(self, run_id: str, extraction: PerspectiveExtraction) -> List[Path]:
        paths = []
        existing_statements = {
            json.loads(path.read_text()).get("statement", "").strip().lower()
            for path in self.path.glob("*.json")
        }
        for candidate in extraction.candidates:
            key = candidate.statement.strip().lower()
            if not key or key in existing_statements:
                continue
            proposal = PerspectiveProposal(
                **candidate.model_dump(),
                owner_voice_id=self.voice_id,
                context_id=self.context_id,
                run_id=run_id,
            )
            path = self.path / "{}.json".format(proposal.id)
            RunStore._atomic_text(path, proposal.model_dump_json(indent=2))
            paths.append(path)
            existing_statements.add(key)
        return paths

    def list(self) -> List[Dict]:
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(self.path.glob("*.json"))
        ]
