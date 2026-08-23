"""Provide perspectives capabilities."""

from __future__ import annotations

import json
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
        """Initialize the perspective registry with its required state and collaborators.

        Args:
            root (Path): The workspace root directory.
            voice_id (str): The stable identifier for the selected voice.

        Returns:
            None: The instance is initialized in place and no value is returned.

        Raises:
            PerspectiveError: If the perspective operation cannot complete.
        """
        self.root = root.resolve()
        self.voice_id = slugify(voice_id)
        if self.voice_id != voice_id:
            raise PerspectiveError("Voice ids must use lowercase letters, digits, and hyphens")
        self.base = self.root / "profiles" / self.voice_id / "perspectives"
        self.registry_path = self.base / "registry.json"

    def _read(self) -> Dict:
        """Read the perspective registry workflow.

        Returns:
            Dict: The structured loaded data for value.
        """
        if not self.registry_path.exists():
            return {"schema_version": "1.0", "contexts": {}}
        data = json.loads(self.registry_path.read_text(encoding="utf-8"))
        data.setdefault("schema_version", "1.0")
        data.setdefault("contexts", {})
        return data

    def list(self) -> Dict:
        """List the perspective registry workflow.

        Returns:
            Dict: The structured available data for value.
        """
        return self._read()["contexts"]

    def context_root(self, context_id: str) -> Path:
        """Return the context root.

        Args:
            context_id (str): The stable identifier for the context.

        Returns:
            Path: The resolved filesystem path for context root.

        Raises:
            PerspectiveError: If the perspective operation cannot complete.
        """
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
        """Stage the perspective registry workflow.

        Args:
            context_id (str): The stable identifier for the context.
            entries (List[PerspectiveEntry]): The ordered domain records to process.
            display_name (Optional[str]): The human-readable name shown to users. Defaults
                to ``None``.

        Returns:
            PerspectiveManifest: The resulting perspective manifest for stage.
        """
        from .perspective_lifecycle import stage_context

        return stage_context(self, context_id, entries, display_name)

    def resolve(
        self,
        context_id: str,
        version: Optional[str] = None,
        allow_inactive: bool = False,
    ) -> Dict:
        """Resolve the perspective registry workflow.

        Resolve a perspective entry and immutable version, verify its hashes, and enforce
        active-state requirements.

        Args:
            context_id (str): The stable identifier for the context.
            version (Optional[str]): The immutable artifact or schema version identifier.
                Defaults to ``None``.
            allow_inactive (bool): Whether allow inactive behavior is enabled. Defaults to
                ``False``.

        Returns:
            Dict: The structured resolved data for value.

        Raises:
            PerspectiveError: If the perspective operation cannot complete.
        """
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
        """Activate the perspective registry workflow.

        Args:
            context_id (str): The stable identifier for the context.
            approved_by (str): The reviewer identity recorded with the approval.

        Returns:
            PerspectiveApprovalReceipt: The resulting perspective approval receipt for
                activate.
        """
        from .perspective_lifecycle import activate_context

        return activate_context(self, context_id, approved_by)

    def deactivate(
        self,
        context_id: str,
        reason: str,
        deactivated_by: str = "repository-owner",
    ) -> Dict:
        """Deactivate the perspective registry workflow.

        Args:
            context_id (str): The stable identifier for the context.
            reason (str): The human-readable reason recorded for the decision.
            deactivated_by (str): Human identity recorded with the pause decision. Defaults to
                ``"repository-owner"``.

        Returns:
            Dict: The structured resulting data for deactivate.

        """
        from .perspective_context_lifecycle import PerspectiveContextLifecycleService

        return (
            PerspectiveContextLifecycleService(self)
            .deactivate(context_id, deactivated_by, reason)
            .model_dump(mode="json")
        )

    def reactivate(
        self, context_id: str, approved_by: str, reason: str = "author reactivation"
    ) -> Dict:
        """Restore an unchanged perspective context with a receipt.

        Args:
            context_id (str): Stable perspective context identifier.
            approved_by (str): Human identity approving reactivation.
            reason (str): Human-readable explanation. Defaults to ``"author reactivation"``.

        Returns:
            Dict: Structured immutable reactivation receipt.
        """
        from .perspective_context_lifecycle import PerspectiveContextLifecycleService

        return (
            PerspectiveContextLifecycleService(self)
            .reactivate(context_id, approved_by, reason)
            .model_dump(mode="json")
        )

    def retirement_plan(self, context_id: str) -> Dict:
        """Return the hash-bound context retirement preflight.

        Args:
            context_id (str): Stable perspective context identifier.

        Returns:
            Dict: Persisted-state retirement inventory and binding hash.
        """
        from .perspective_context_lifecycle import PerspectiveContextLifecycleService

        return PerspectiveContextLifecycleService(self).plan(context_id).model_dump(mode="json")

    def retire_context(
        self, context_id: str, retired_by: str, reason: str, **decisions: object
    ) -> Dict:
        """Retire a whole context without changing any immutable entry.

        Args:
            context_id (str): Stable perspective context identifier.
            retired_by (str): Human identity responsible for retirement.
            reason (str): Human-readable retirement explanation.
            **decisions (dict[str, object]): Reviewed plan and pending-artifact dispositions.

        Returns:
            Dict: Structured immutable retirement receipt.

        Raises:
            PerspectiveError: If the reviewed retirement plan hash is missing.
        """
        from .perspective_context_lifecycle import PerspectiveContextLifecycleService

        plan_hash = decisions.get("plan_hash")
        if not isinstance(plan_hash, str) or not plan_hash:
            raise PerspectiveError("Context retirement requires a reviewed plan hash")
        candidate_disposition = decisions.get("candidate_disposition")
        proposal_disposition = decisions.get("proposal_disposition")
        return (
            PerspectiveContextLifecycleService(self)
            .retire(
                context_id,
                retired_by,
                reason,
                plan_hash=plan_hash,
                candidate_disposition=(
                    str(candidate_disposition) if candidate_disposition is not None else None
                ),
                proposal_disposition=(
                    str(proposal_disposition) if proposal_disposition is not None else None
                ),
            )
            .model_dump(mode="json")
        )

    def restore_context(
        self, context_id: str, requested_by: str, approved_by: str, plan_hash: str
    ) -> Dict:
        """Restore a retired context through explicit request and review.

        Args:
            context_id (str): Stable perspective context identifier.
            requested_by (str): Human identity requesting restoration.
            approved_by (str): Human identity approving restoration.
            plan_hash (str): Exact reviewed restoration plan hash.

        Returns:
            Dict: Structured immutable restoration receipt.
        """
        from .perspective_context_lifecycle import PerspectiveContextLifecycleService

        return (
            PerspectiveContextLifecycleService(self)
            .restore(context_id, requested_by, approved_by, plan_hash)
            .model_dump(mode="json")
        )

    def decide_candidate(
        self,
        context_id: str,
        candidate_hash: str,
        actor: str,
        reason: str,
        action: str = "reject",
    ) -> Dict:
        """Reject or abandon one exact pending context candidate hash.

        Args:
            context_id (str): Stable perspective context identifier.
            candidate_hash (str): Exact pending candidate content hash.
            actor (str): Human identity responsible for the decision.
            reason (str): Human-readable decision explanation.
            action (str): Reject or abandon. Defaults to ``"reject"``.

        Returns:
            Dict: Structured immutable exact-hash decision receipt.
        """
        from .perspective_context_lifecycle import PerspectiveContextLifecycleService

        return (
            PerspectiveContextLifecycleService(self)
            .decide_candidate(context_id, candidate_hash, actor, reason, action)
            .model_dump(mode="json")
        )

    def verify_lifecycle(self, context_id: str) -> Dict:
        """Verify context lifecycle receipts offline.

        Args:
            context_id (str): Stable perspective context identifier.

        Returns:
            Dict: Deterministic offline verification result.
        """
        from .perspective_context_lifecycle import PerspectiveContextLifecycleService

        return PerspectiveContextLifecycleService(self).verify(context_id)

    def migrate_legacy_lifecycle(self, context_id: str, migrated_by: str) -> Dict:
        """Record a legacy registry-only inactive context with a reviewed receipt.

        Args:
            context_id (str): Stable perspective context identifier.
            migrated_by (str): Human identity reviewing the legacy state.

        Returns:
            Dict: Structured immutable legacy migration receipt.
        """
        from .perspective_context_lifecycle import PerspectiveContextLifecycleService

        return (
            PerspectiveContextLifecycleService(self)
            .migrate_legacy(context_id, migrated_by)
            .model_dump(mode="json")
        )

    def current_entries(self, context_id: str) -> List[PerspectiveEntry]:
        """Return the current entries.

        Args:
            context_id (str): The stable identifier for the context.

        Returns:
            List[PerspectiveEntry]: The resulting current entries values in their documented
                order.
        """
        resolved = self.resolve(context_id)
        path = self.root / resolved["path"] / "entries.json"
        return [
            PerspectiveEntry.model_validate(item)
            for item in json.loads(path.read_text(encoding="utf-8"))
        ]

    def stage_proposal(self, context_id: str, proposal_id: str) -> PerspectiveManifest:
        """Stage the proposal.

        Args:
            context_id (str): The stable identifier for the context.
            proposal_id (str): The stable identifier for the proposal.

        Returns:
            PerspectiveManifest: The resulting perspective manifest for stage proposal.

        Raises:
            PerspectiveError: If the perspective operation cannot complete.
        """
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
        """Retire the entry.

        Args:
            context_id (str): The stable identifier for the context.
            entry_id (str): The stable identifier for the entry.
            reason (str): The human-readable reason recorded for the decision.

        Returns:
            PerspectiveManifest: The resulting perspective manifest for retire entry.

        Raises:
            PerspectiveError: If the perspective operation cannot complete.
        """
        entries = self.current_entries(context_id)
        target = next((entry for entry in entries if entry.id == entry_id), None)
        if not target:
            raise PerspectiveError("Unknown perspective entry: {}".format(entry_id))
        target.status = PerspectiveEntryStatus.RETIRED
        target.qualifications.append("Retired: {}".format(reason))
        return self.stage(context_id, entries)

    @staticmethod
    def render_profile(context_id: str, entries: List[PerspectiveEntry]) -> str:
        """Render the profile.

        Args:
            context_id (str): The stable identifier for the context.
            entries (List[PerspectiveEntry]): The ordered domain records to process.

        Returns:
            str: The rendered text for profile.
        """
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
        """Initialize the perspective proposal store.

        Args:
            root (Path): The workspace root directory.
            voice_id (str): The stable identifier for the selected voice.
            context_id (str): The stable identifier for the context.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        self.root = root.resolve()
        self.voice_id = voice_id
        self.context_id = context_id
        self.path = self.root / "profiles" / voice_id / "perspectives" / context_id / "proposals"

    def apply(self, run_id: str, extraction: PerspectiveExtraction) -> List[Path]:
        """Apply the perspective proposal store workflow.

        Args:
            run_id (str): The stable identifier for the content run.
            extraction (PerspectiveExtraction): The extraction value passed to apply.

        Returns:
            List[Path]: The resolved filesystem path for apply.
        """
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
        """List the perspective proposal store workflow.

        Returns:
            List[Dict]: The available value values in their documented order.
        """
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(self.path.glob("*.json"))
        ]
