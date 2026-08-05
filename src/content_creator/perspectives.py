"""Provide perspectives capabilities."""

from __future__ import annotations

import json
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
    hash_file,
    verify_components,
)


class PerspectiveRegistry:
    """Manage perspective records."""

    def __init__(self, root: Path, voice_id: str):
        """Initialize the perspective registry."""
        self.root = root.resolve()
        self.voice_id = slugify(voice_id)
        if self.voice_id != voice_id:
            raise PerspectiveError("Voice ids must use lowercase letters, digits, and hyphens")
        self.base = self.root / "profiles" / self.voice_id / "perspectives"
        self.registry_path = self.base / "registry.json"

    def _read(self) -> Dict:
        """Read perspective registry."""
        if not self.registry_path.exists():
            return {"schema_version": "1.0", "contexts": {}}
        data = json.loads(self.registry_path.read_text(encoding="utf-8"))
        data.setdefault("schema_version", "1.0")
        data.setdefault("contexts", {})
        return data

    def list(self) -> Dict:
        """List perspective registry."""
        return self._read()["contexts"]

    def context_root(self, context_id: str) -> Path:
        """Return the context root."""
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
        """Stage perspective registry."""
        from .perspective_lifecycle import stage_context

        return stage_context(self, context_id, entries, display_name)

    def resolve(
        self,
        context_id: str,
        version: Optional[str] = None,
        allow_inactive: bool = False,
    ) -> Dict:
        """Resolve perspective registry."""
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
        """Activate perspective registry."""
        from .perspective_lifecycle import activate_context

        return activate_context(self, context_id, approved_by)

    def deactivate(self, context_id: str, reason: str) -> Dict:
        """Deactivate perspective registry."""
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
        """Return the current entries."""
        resolved = self.resolve(context_id)
        path = self.root / resolved["path"] / "entries.json"
        return [
            PerspectiveEntry.model_validate(item)
            for item in json.loads(path.read_text(encoding="utf-8"))
        ]

    def stage_proposal(self, context_id: str, proposal_id: str) -> PerspectiveManifest:
        """Stage proposal."""
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
        """Retire entry."""
        entries = self.current_entries(context_id)
        target = next((entry for entry in entries if entry.id == entry_id), None)
        if not target:
            raise PerspectiveError("Unknown perspective entry: {}".format(entry_id))
        target.status = PerspectiveEntryStatus.RETIRED
        target.qualifications.append("Retired: {}".format(reason))
        return self.stage(context_id, entries)

    @staticmethod
    def render_profile(context_id: str, entries: List[PerspectiveEntry]) -> str:
        """Render profile."""
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
    """Manage perspective proposal records."""

    def __init__(self, root: Path, voice_id: str, context_id: str):
        """Initialize the perspective proposal store."""
        self.root = root.resolve()
        self.voice_id = voice_id
        self.context_id = context_id
        self.path = self.root / "profiles" / voice_id / "perspectives" / context_id / "proposals"

    def apply(self, run_id: str, extraction: PerspectiveExtraction) -> List[Path]:
        """Apply perspective proposal store."""
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
        """List perspective proposal store."""
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(self.path.glob("*.json"))
        ]
