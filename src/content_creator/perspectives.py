from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, List, Optional

from .perspective_support import (
    PerspectiveApprovalReceipt as PerspectiveApprovalReceipt,
)
from .perspective_support import (
    PerspectiveCatalogue as PerspectiveCatalogue,
)
from .perspective_support import (
    PerspectiveCatalogueEntry as PerspectiveCatalogueEntry,
)
from .perspective_support import (
    PerspectiveCatalogueStore as PerspectiveCatalogueStore,
)
from .perspective_support import (
    PerspectiveChangeType as PerspectiveChangeType,
)
from .perspective_support import (
    PerspectiveEntry as PerspectiveEntry,
)
from .perspective_support import (
    PerspectiveEntryStatus as PerspectiveEntryStatus,
)
from .perspective_support import (
    PerspectiveError as PerspectiveError,
)
from .perspective_support import (
    PerspectiveExtraction as PerspectiveExtraction,
)
from .perspective_support import (
    PerspectiveManifest as PerspectiveManifest,
)
from .perspective_support import (
    PerspectiveProposal as PerspectiveProposal,
)
from .perspective_support import (
    PerspectiveProposalCandidate as PerspectiveProposalCandidate,
)
from .perspective_support import (
    PerspectiveProvenance as PerspectiveProvenance,
)
from .perspective_support import (
    PerspectiveResolution as PerspectiveResolution,
)
from .perspective_support import (
    PerspectiveResolver as PerspectiveResolver,
)
from .perspective_support import (
    PerspectiveRunner as PerspectiveRunner,
)
from .perspective_support import (
    PerspectiveStatus as PerspectiveStatus,
)
from .storage import RunStore, slugify
from .versioned_artifacts import (
    ActivationLock,
    hash_file,
    hash_json,
    next_major_version,
    verify_components,
)
from .voices import VoiceRegistry


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
        mismatches = verify_components(path, manifest.components, manifest.component_hashes)
        if mismatches:
            raise PerspectiveError(
                "Active perspective component hash mismatch: {}".format(mismatches[0])
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
        mismatches = verify_components(candidate, manifest.components, manifest.component_hashes)
        if mismatches:
            raise PerspectiveError("Perspective component hash mismatch: {}".format(mismatches[0]))
        evaluation = json.loads((candidate / manifest.components["evaluation_report"]).read_text())
        if not evaluation.get("passed"):
            raise PerspectiveError("Perspective evaluation did not pass")

        with ActivationLock(
            context_root / ".activation.lock",
            "Perspective activation is already in progress",
            PerspectiveError,
        ):
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
            version = next_major_version(context_root / "versions")
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
