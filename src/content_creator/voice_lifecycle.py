"""Plan and apply auditable voice pause, retirement, and restoration decisions."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .lifecycle_models import LifecycleDisposition, LifecyclePlan, LifecycleReceipt
from .lifecycle_support import (
    AtomicArtifactTransaction,
    append_catalogue_receipt,
    catalogue_text,
    epoch_updates,
    freeze_epoch,
    latest_receipt,
    open_epoch,
    receipt_path_for,
    receipt_relative_path,
    updated_default_configuration,
    utc_timestamp,
    validate_decision_text,
    verify_receipts,
    version_catalogue,
    voice_withdrawal_updates,
)
from .versioned_artifacts import ActivationLock, hash_file, hash_json, verify_components
from .voice_lifecycle_planning import retirement_plan
from .voice_models import VoiceError, VoiceManifest, VoiceStatus
from .voice_upgrade.epochs import epoch_hash, load_epoch


@dataclass
class VoiceRetirementDecisions:
    """Collect explicit aggregate retirement choices from the author."""

    clear_default: bool = False
    replacement_voice: Optional[str] = None
    candidate_disposition: Optional[str] = None
    perspective_candidate_disposition: Optional[str] = None
    proposal_disposition: Optional[str] = None
    run_disposition: Optional[str] = None


@dataclass
class VoiceTransition:
    """Collect one voice registry transition and its bound decisions."""

    expected: set[str]
    resulting: str
    action: str
    actor: str
    reason: str
    clear_default: bool = False
    replacement_voice: Optional[str] = None
    plan_hash: Optional[str] = None
    dispositions: list[LifecycleDisposition] = field(default_factory=list)
    affected_contexts: list[str] = field(default_factory=list)
    affected_runs: list[str] = field(default_factory=list)
    run_disposition: Optional[str] = None
    legacy_migration: bool = False


@dataclass
class VoiceTransitionEvidence:
    """Bind registry, version, and learning evidence for a voice transition."""

    prior_status: str
    before_hash: str
    after_hash: str
    version: str
    manifest_hash: str
    epoch: Any


class VoiceLifecycleService:
    """Apply lifecycle transitions behind the shared voice lifecycle lock."""

    def __init__(self, registry: Any):
        """Initialize the service for one voice registry.

        Args:
            registry (Any): Voice registry providing workspace persistence access.

        Returns:
            None: The service retains the registry and resolved workspace root.
        """
        self.registry = registry
        self.root = registry.root.resolve()

    def plan(self, voice_id: str) -> LifecyclePlan:
        """Return the current persisted-state lifecycle preflight.

        Args:
            voice_id (str): Stable selected voice identifier.

        Returns:
            LifecyclePlan: Hash-bound read-only retirement preflight.
        """
        return retirement_plan(self.registry, voice_id)

    def deactivate(
        self,
        voice_id: str,
        actor: str,
        reason: str,
        *,
        clear_default: bool = False,
        replacement_voice: Optional[str] = None,
    ) -> LifecycleReceipt:
        """Deactivate one active voice and freeze its current learning epoch.

        Args:
            voice_id (str): Stable selected voice identifier.
            actor (str): Human identity responsible for the pause.
            reason (str): Human-readable pause explanation.
            clear_default (bool): Whether to clear a matching default. Defaults to ``False``.
            replacement_voice (Optional[str]): Reviewed replacement. Defaults to ``None``.

        Returns:
            LifecycleReceipt: Immutable deactivation evidence.
        """
        actor, reason = validate_decision_text(actor, reason)
        return self._withdraw(
            voice_id,
            VoiceTransition(
                {VoiceStatus.ACTIVE.value},
                VoiceStatus.INACTIVE.value,
                "deactivate",
                actor,
                reason,
                clear_default,
                replacement_voice,
            ),
        )

    def reactivate(
        self, voice_id: str, actor: str, reason: str = "author reactivation"
    ) -> LifecycleReceipt:
        """Restore one paused voice without creating a voice version.

        Reopen learning in a new activation epoch while retaining the selected
        immutable version and its manifest hash.

        Args:
            voice_id (str): Stable selected voice identifier.
            actor (str): Human identity approving reactivation.
            reason (str): Human-readable explanation. Defaults to ``"author reactivation"``.

        Returns:
            LifecycleReceipt: Immutable reactivation evidence.

        Raises:
            VoiceError: If the voice is missing, active, or retired.
        """
        actor, reason = validate_decision_text(actor, reason)
        voice_root = self.root / "profiles" / voice_id
        with ActivationLock(
            voice_root / ".lifecycle.lock",
            "Voice lifecycle operation is already in progress",
            VoiceError,
        ):
            registry = self.registry._read()
            item = registry["profiles"].get(voice_id)
            if not item:
                raise VoiceError(f"Unknown voice: {voice_id}")
            if item.get("status") == VoiceStatus.RETIRED.value:
                raise VoiceError("Retired voices require the reviewed restore path")
            if item.get("status") != VoiceStatus.INACTIVE.value:
                raise VoiceError("Only an inactive voice can be reactivated")
            version, manifest_hash = self._verify_selected(voice_id, item)
            before_hash = hash_json(registry)
            epoch, path = open_epoch(self.root, voice_id, version)
            item["status"] = VoiceStatus.ACTIVE.value
            item["reactivated_at"] = utc_timestamp()
            item.pop("deactivation_reason", None)
            after_hash = hash_json(registry)
            transition = VoiceTransition(
                {VoiceStatus.INACTIVE.value},
                VoiceStatus.ACTIVE.value,
                "reactivate",
                actor,
                reason,
            )
            receipt = self._receipt(
                voice_id,
                transition,
                VoiceTransitionEvidence(
                    VoiceStatus.INACTIVE.value,
                    before_hash,
                    after_hash,
                    version,
                    manifest_hash,
                    epoch,
                ),
            )
            self._commit(voice_id, registry, receipt, epoch_updates(epoch, path), "selected")
            return receipt

    def retire(
        self,
        voice_id: str,
        actor: str,
        reason: str,
        plan_hash: str,
        decisions: Optional[VoiceRetirementDecisions] = None,
    ) -> LifecycleReceipt:
        """Retire one voice after validating its plan and explicit dispositions.

        Args:
            voice_id (str): Stable selected voice identifier.
            actor (str): Human identity responsible for retirement.
            reason (str): Human-readable retirement explanation.
            plan_hash (str): Exact reviewed preflight binding hash.
            decisions (Optional[VoiceRetirementDecisions]): Aggregate decisions. Defaults to
                ``None``.

        Returns:
            LifecycleReceipt: Immutable retirement evidence.

        Raises:
            VoiceError: If the supplied retirement plan is stale.
        """
        actor, reason = validate_decision_text(actor, reason)
        plan = self.plan(voice_id)
        if plan.binding_hash != plan_hash:
            raise VoiceError("Retirement plan is stale; generate and review a new plan")
        transition = self._retirement_transition(
            voice_id, actor, reason, plan_hash, plan, decisions or VoiceRetirementDecisions()
        )
        return self._withdraw(voice_id, transition)

    def _retirement_transition(
        self,
        voice_id: str,
        actor: str,
        reason: str,
        plan_hash: str,
        plan: LifecyclePlan,
        decisions: VoiceRetirementDecisions,
    ) -> VoiceTransition:
        """Validate retirement choices and bind their exact artifact hashes.

        Require explicit decisions only for pending artifacts observed by the
        reviewed plan, then carry their exact hashes into the receipt transition.

        Args:
            voice_id (str): Stable selected voice identifier.
            actor (str): Human identity responsible for retirement.
            reason (str): Human-readable retirement explanation.
            plan_hash (str): Exact reviewed preflight binding hash.
            plan (LifecyclePlan): Current persisted-state retirement preflight.
            decisions (VoiceRetirementDecisions): Explicit aggregate decisions.

        Returns:
            VoiceTransition: Fully validated retirement transition.

        Raises:
            VoiceError: If any pending aggregate lacks an explicit disposition.
        """
        pending_candidates = [
            candidate for candidate in plan.candidates if candidate.get("decision") == "pending"
        ]
        if pending_candidates and decisions.candidate_disposition not in {
            "retain",
            "reject",
            "abandon",
        }:
            raise VoiceError("Pending voice candidates require an explicit disposition")
        if plan.perspective_candidates and decisions.perspective_candidate_disposition not in {
            "retain",
            "reject",
            "abandon",
        }:
            raise VoiceError("Pending perspective candidates require an explicit disposition")
        if plan.perspective_proposals and decisions.proposal_disposition not in {
            "retain",
            "reject",
            "abandon",
        }:
            raise VoiceError("Pending perspective proposals require an explicit disposition")
        incomplete = [item for item in plan.runs if item["incomplete"]]
        if incomplete and decisions.run_disposition not in {"abandon", "retain-exception"}:
            raise VoiceError("Incomplete runs require an explicit disposition")
        dispositions = self._retirement_dispositions(voice_id, plan, pending_candidates, decisions)
        return VoiceTransition(
            {VoiceStatus.ACTIVE.value, VoiceStatus.INACTIVE.value},
            VoiceStatus.RETIRED.value,
            "retire",
            actor,
            reason,
            decisions.clear_default,
            decisions.replacement_voice,
            plan_hash,
            dispositions,
            [item["context_id"] for item in plan.perspective_contexts],
            [item["run_id"] for item in incomplete],
            decisions.run_disposition,
        )

    @staticmethod
    def _retirement_dispositions(
        voice_id: str,
        plan: LifecyclePlan,
        pending_candidates: list[dict[str, Any]],
        decisions: VoiceRetirementDecisions,
    ) -> list[LifecycleDisposition]:
        """Return exact-hash receipt dispositions for all pending aggregate work.

        Args:
            voice_id (str): Stable selected voice identifier.
            plan (LifecyclePlan): Current retirement preflight.
            pending_candidates (list[dict[str, Any]]): Pending voice candidate inventory.
            decisions (VoiceRetirementDecisions): Explicit aggregate decisions.

        Returns:
            list[LifecycleDisposition]: Exact-hash artifact dispositions.
        """
        inputs = [
            (
                "voice-candidate",
                voice_id,
                item["candidate_hash"],
                decisions.candidate_disposition,
            )
            for item in pending_candidates
        ]
        inputs.extend(
            (
                "perspective-candidate",
                item["context_id"],
                item["candidate_hash"],
                decisions.perspective_candidate_disposition,
            )
            for item in plan.perspective_candidates
        )
        inputs.extend(
            (
                "perspective-proposal",
                item["proposal_id"],
                item["hash"],
                decisions.proposal_disposition,
            )
            for item in plan.perspective_proposals
        )
        return [
            LifecycleDisposition(
                kind=kind, stable_id=stable_id, artifact_hash=digest, action=str(action)
            )
            for kind, stable_id, digest, action in inputs
        ]

    def restore(
        self, voice_id: str, requested_by: str, approved_by: str, plan_hash: str
    ) -> LifecycleReceipt:
        """Restore one retired voice through request, plan, and reviewer approval.

        Preserve the immutable selected version while reopening learning under a
        new epoch and binding both requester and reviewer into persisted evidence.

        Args:
            voice_id (str): Stable selected voice identifier.
            requested_by (str): Human identity requesting restoration.
            approved_by (str): Human identity approving restoration.
            plan_hash (str): Exact reviewed restoration plan binding hash.

        Returns:
            LifecycleReceipt: Immutable restoration evidence.

        Raises:
            VoiceError: If the plan is stale or the voice is not retired.
        """
        requested_by, _ = validate_decision_text(requested_by, "restoration requested")
        approved_by, reason = validate_decision_text(
            approved_by, f"reviewed restoration requested by {requested_by}"
        )
        plan = self.plan(voice_id)
        if plan.binding_hash != plan_hash:
            raise VoiceError("Restoration plan is stale; generate and review a new plan")
        if plan.current_status != VoiceStatus.RETIRED.value:
            raise VoiceError("Only a retired voice can be restored")
        voice_root = self.root / "profiles" / voice_id
        with ActivationLock(
            voice_root / ".lifecycle.lock",
            "Voice lifecycle operation is already in progress",
            VoiceError,
        ):
            registry = self.registry._read()
            item = registry["profiles"][voice_id]
            version, manifest_hash = self._verify_selected(voice_id, item)
            before_hash = hash_json(registry)
            epoch, path = open_epoch(self.root, voice_id, version)
            item["status"] = VoiceStatus.ACTIVE.value
            item["restored_at"] = utc_timestamp()
            after_hash = hash_json(registry)
            transition = VoiceTransition(
                {VoiceStatus.RETIRED.value},
                VoiceStatus.ACTIVE.value,
                "restore",
                approved_by,
                reason,
                plan_hash=plan_hash,
            )
            receipt = self._receipt(
                voice_id,
                transition,
                VoiceTransitionEvidence(
                    VoiceStatus.RETIRED.value,
                    before_hash,
                    after_hash,
                    version,
                    manifest_hash,
                    epoch,
                ),
            )
            self._commit(voice_id, registry, receipt, epoch_updates(epoch, path), "selected")
            return receipt

    def migrate_legacy(self, voice_id: str, actor: str) -> LifecycleReceipt:
        """Create a legacy-labelled receipt for a registry-only inactive voice.

        Args:
            voice_id (str): Stable selected voice identifier.
            actor (str): Human identity reviewing the legacy state.

        Returns:
            LifecycleReceipt: Immutable legacy migration evidence.

        Raises:
            VoiceError: If the voice is not legacy-inactive or already has receipts.
        """
        item = self.registry.get(voice_id)
        actor, reason = validate_decision_text(
            actor, str(item.get("deactivation_reason") or "not recorded in legacy state")
        )
        if item.get("status") != VoiceStatus.INACTIVE.value:
            raise VoiceError("Only a legacy inactive registry entry can be migrated")
        base = self.root / "profiles" / voice_id
        if list((base / "lifecycle" / "receipts").glob("*.json")):
            raise VoiceError("Lifecycle receipts already exist for this voice")
        registry = self.registry._read()
        version, manifest_hash = self._verify_selected(voice_id, item)
        digest = hash_json(registry)
        epoch = load_epoch(self.root, voice_id, version, migrate_legacy=True)
        transition = VoiceTransition(
            {VoiceStatus.INACTIVE.value},
            VoiceStatus.INACTIVE.value,
            "migrate-legacy-deactivation",
            actor,
            reason,
            legacy_migration=True,
        )
        receipt = self._receipt(
            voice_id,
            transition,
            VoiceTransitionEvidence(
                VoiceStatus.INACTIVE.value,
                digest,
                digest,
                version,
                manifest_hash,
                epoch,
            ),
        )
        self._commit(voice_id, registry, receipt, [], "deactivated-with-voice")
        return receipt

    def verify(self, voice_id: str) -> dict[str, Any]:
        """Verify one voice's lifecycle receipts and version catalogue offline.

        Args:
            voice_id (str): Stable selected voice identifier.

        Returns:
            dict[str, Any]: Receipt verification and deterministic catalogue data.
        """
        base = self.root / "profiles" / voice_id
        result = verify_receipts(self.root, [base]).model_dump(mode="json")
        catalogue = version_catalogue(
            self.root, voice_id, self.registry.get(voice_id).get("active_version")
        )
        result["catalogue"] = catalogue.model_dump(mode="json")
        return result

    def _withdraw(self, voice_id: str, transition: VoiceTransition) -> LifecycleReceipt:
        """Apply a validated pause or retirement as one compensated transaction.

        Hold the shared lifecycle lock across registry, epoch, default, candidate,
        run, receipt, and catalogue replacements so readers cannot see partial state.

        Args:
            voice_id (str): Stable selected voice identifier.
            transition (VoiceTransition): Validated withdrawal transition.

        Returns:
            LifecycleReceipt: Immutable transition evidence.

        Raises:
            VoiceError: If the voice state or replacement default is invalid.
        """
        voice_root = self.root / "profiles" / voice_id
        with ActivationLock(
            voice_root / ".lifecycle.lock",
            "Voice lifecycle operation is already in progress",
            VoiceError,
        ):
            registry = self.registry._read()
            item = registry["profiles"].get(voice_id)
            if not item:
                raise VoiceError(f"Unknown voice: {voice_id}")
            prior_status = str(item.get("status"))
            if prior_status not in transition.expected:
                raise VoiceError(f"Voice {voice_id} cannot {transition.action} from {prior_status}")
            config_text = updated_default_configuration(
                self.root,
                voice_id,
                transition.replacement_voice,
                transition.clear_default,
            )
            if transition.replacement_voice:
                replacement = registry["profiles"].get(transition.replacement_voice)
                if not replacement or replacement.get("status") != VoiceStatus.ACTIVE.value:
                    raise VoiceError("Replacement default voice must exist and be active")
            version, manifest_hash = self._verify_selected(voice_id, item)
            before_hash = hash_json(registry)
            epoch, archive = freeze_epoch(
                self.root, voice_id, version, transition.actor, transition.reason
            )
            item["status"] = transition.resulting
            timestamp_key = "retired_at" if transition.action == "retire" else "deactivated_at"
            reason_key = (
                "deactivation_reason"
                if transition.action == "deactivate"
                else f"{transition.action}_reason"
            )
            item[timestamp_key] = utc_timestamp()
            item[reason_key] = transition.reason
            item["lifecycle_actor"] = transition.actor
            after_hash = hash_json(registry)
            evidence = VoiceTransitionEvidence(
                prior_status, before_hash, after_hash, version, manifest_hash, epoch
            )
            receipt = self._receipt(voice_id, transition, evidence)
            updates = voice_withdrawal_updates(
                self.root,
                voice_root,
                receipt,
                transition,
                evidence,
                archive,
                config_text,
            )
            relationship = (
                "retired-with-voice"
                if transition.resulting == VoiceStatus.RETIRED.value
                else "deactivated-with-voice"
            )
            self._commit(voice_id, registry, receipt, updates, relationship)
            return receipt

    def _verify_selected(self, voice_id: str, item: dict) -> tuple[str, str]:
        """Verify and return the selected immutable version evidence.

        Args:
            voice_id (str): Stable selected voice identifier.
            item (dict): Current voice registry entry.

        Returns:
            tuple[str, str]: Selected version and manifest hash.

        Raises:
            VoiceError: If version evidence is absent or inconsistent.
        """
        version = item.get("active_version")
        if not version:
            raise VoiceError(f"Voice {voice_id} has no selected version")
        manifest_path = self.root / "profiles" / voice_id / "versions" / version / "manifest.json"
        if not manifest_path.exists():
            raise VoiceError(f"Missing voice version {voice_id}@{version}")
        manifest = VoiceManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        directory = manifest_path.parent
        mismatches = verify_components(directory, manifest.components, manifest.component_hashes)
        if mismatches:
            raise VoiceError(f"Selected voice component hash mismatch: {mismatches[0]}")
        return str(version), hash_file(manifest_path)

    def _receipt(
        self,
        voice_id: str,
        transition: VoiceTransition,
        evidence: VoiceTransitionEvidence,
    ) -> LifecycleReceipt:
        """Build an immutable voice transition receipt.

        Args:
            voice_id (str): Stable selected voice identifier.
            transition (VoiceTransition): Validated transition decisions.
            evidence (VoiceTransitionEvidence): Registry, version, and epoch evidence.

        Returns:
            LifecycleReceipt: Complete hash-bound lifecycle receipt.
        """
        predecessor_path = latest_receipt(self.root / "profiles" / voice_id)
        predecessor = (
            str(Path(predecessor_path).relative_to(self.root)) if predecessor_path else None
        )
        return LifecycleReceipt(
            object_type="voice",
            object_id=voice_id,
            action=transition.action,
            actor=transition.actor,
            reason=transition.reason,
            decided_at=utc_timestamp(),
            prior_status=evidence.prior_status,
            resulting_status=transition.resulting,
            prior_registry_hash=evidence.before_hash,
            resulting_registry_hash=evidence.after_hash,
            selected_version=evidence.version,
            selected_manifest_hash=evidence.manifest_hash,
            candidate_dispositions=transition.dispositions,
            learning_epoch_id=evidence.epoch.epoch_id,
            learning_epoch_hash=epoch_hash(evidence.epoch),
            affected_context_ids=transition.affected_contexts,
            affected_run_ids=transition.affected_runs,
            predecessor_receipt=predecessor,
            plan_hash=transition.plan_hash,
            legacy_migration=transition.legacy_migration,
        )

    def _commit(
        self,
        voice_id: str,
        registry: dict,
        receipt: LifecycleReceipt,
        extra_updates: list[tuple[Path, str]],
        relationship: str,
    ) -> None:
        """Persist registry, epoch, receipt, and catalogue replacements atomically.

        Args:
            voice_id (str): Stable selected voice identifier.
            registry (dict): Updated registry document.
            receipt (LifecycleReceipt): Immutable transition receipt.
            extra_updates (list[tuple[Path, str]]): Additional artifact replacements.
            relationship (str): Selected-version lifecycle relationship.

        Returns:
            None: All artifacts are committed or compensated together.
        """
        base = self.root / "profiles" / voice_id
        receipt_path = receipt_path_for(base, receipt)
        relative = receipt_relative_path(self.root, receipt_path)
        catalogue = version_catalogue(self.root, voice_id, receipt.selected_version)
        append_catalogue_receipt(
            catalogue,
            str(receipt.selected_version),
            relationship,
            relative,
            load_epoch(self.root, voice_id, str(receipt.selected_version), migrate_legacy=False),
        )
        for record in catalogue.records:
            if record.version == receipt.selected_version:
                record.learning_epoch_id = receipt.learning_epoch_id
                record.learning_epoch_hash = receipt.learning_epoch_hash
        updates = [
            (self.registry.path, json.dumps(registry, indent=2)),
            *extra_updates,
            (receipt_path, receipt.model_dump_json(indent=2)),
            (base / "lifecycle" / "catalogue.json", catalogue_text(catalogue)),
        ]
        AtomicArtifactTransaction(updates).commit()
