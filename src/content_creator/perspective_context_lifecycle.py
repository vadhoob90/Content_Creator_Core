"""Apply auditable pause, retirement, restoration, and candidate context decisions."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .lifecycle_models import LifecycleDisposition, LifecyclePlan, LifecycleReceipt
from .lifecycle_support import (
    AtomicArtifactTransaction,
    latest_receipt,
    receipt_path_for,
    utc_timestamp,
    validate_decision_text,
    verify_receipts,
)
from .perspective_support import PerspectiveError, PerspectiveManifest, PerspectiveStatus
from .versioned_artifacts import ActivationLock, hash_file, hash_json, verify_components


@dataclass
class ContextTransition:
    """Collect one context transition decision and its reviewed dispositions."""

    expected: set[str]
    resulting: str
    action: str
    actor: str
    reason: str
    plan_hash: Optional[str] = None
    dispositions: list[LifecycleDisposition] = field(default_factory=list)


@dataclass
class ContextTransitionEvidence:
    """Bind registry and immutable-version evidence for one context transition."""

    prior_status: str
    before_hash: str
    after_hash: str
    version: str
    manifest_hash: str


class PerspectiveContextLifecycleService:
    """Apply context lifecycle decisions outside immutable perspective versions."""

    def __init__(self, registry: Any):
        """Initialize the service for one voice-scoped perspective registry.

        Args:
            registry (Any): Perspective registry providing persistence access.

        Returns:
            None: The service retains the registry and resolved workspace root.
        """
        self.registry = registry
        self.root = registry.root.resolve()

    def plan(self, context_id: str) -> LifecyclePlan:
        """Return a read-only, hash-bound context lifecycle plan.

        Args:
            context_id (str): Stable perspective context identifier.

        Returns:
            LifecyclePlan: Current persisted-state retirement preflight.

        Raises:
            PerspectiveError: If the context is unknown.
        """
        item = self.registry.list().get(context_id)
        if not item:
            raise PerspectiveError(f"Unknown perspective context: {context_id}")
        version, manifest_hash = self._verify_selected(context_id, item)
        context_root = self.registry.context_root(context_id)
        candidates = self._candidate_inventory(context_id, context_root, item)
        proposals = self._proposal_inventory(context_root)
        required = []
        if any(not candidate.get("decision") for candidate in candidates):
            required.append("choose an exact-hash disposition for the pending context candidate")
        if proposals:
            required.append("choose a disposition for each pending proposal")
        plan = LifecyclePlan(
            object_type="perspective-context",
            object_id=context_id,
            generated_at=utc_timestamp(),
            current_status=str(item.get("status")),
            selected_version=version,
            selected_manifest_hash=manifest_hash,
            candidates=candidates,
            perspective_proposals=proposals,
            effects=self._effects(),
            required_decisions=required,
            valid_next_actions=self._valid_actions(str(item.get("status"))),
        )
        plan.binding_hash = hash_json(
            plan.model_dump(mode="json", exclude={"generated_at", "binding_hash"})
        )
        return plan

    def _candidate_inventory(
        self, context_id: str, context_root: Path, item: dict
    ) -> list[dict[str, Any]]:
        """Return the selected context's candidate and exact-hash decision.

        Inspect both context-local and owning-voice aggregate receipts so a
        resolved candidate is never presented as pending again.

        Args:
            context_id (str): Stable perspective context identifier.
            context_root (Path): Context aggregate root.
            item (dict): Current perspective registry entry.

        Returns:
            list[dict[str, Any]]: Pending candidate inventory with decision evidence.
        """
        candidate_path = context_root / "candidate" / "manifest.json"
        candidates = []
        if candidate_path.exists():
            candidate = PerspectiveManifest.model_validate_json(
                candidate_path.read_text(encoding="utf-8")
            )
            if candidate.candidate_hash != item.get("candidate_hash"):
                decision_path = (
                    context_root
                    / "candidate-decisions"
                    / f"{candidate.candidate_hash.removeprefix('sha256:')}.json"
                )
                aggregate_decision_path = (
                    self.root
                    / "profiles"
                    / self.registry.voice_id
                    / "lifecycle"
                    / "candidate-decisions"
                    / "perspective-candidate-{}.json".format(
                        candidate.candidate_hash.removeprefix("sha256:")
                    )
                )
                if not decision_path.exists() and aggregate_decision_path.exists():
                    decision_path = aggregate_decision_path
                decision = None
                if decision_path.exists():
                    receipt = LifecycleReceipt.model_validate_json(
                        decision_path.read_text(encoding="utf-8")
                    )
                    matched = next(
                        (
                            item.action
                            for item in receipt.candidate_dispositions
                            if item.artifact_hash == candidate.candidate_hash
                        ),
                        None,
                    )
                    decision = matched or receipt.action
                candidates.append(
                    {
                        "context_id": context_id,
                        "candidate_hash": candidate.candidate_hash,
                        "manifest_hash": hash_file(candidate_path),
                        "status": candidate.status.value,
                        "decision": decision,
                    }
                )
        return candidates

    @staticmethod
    def _proposal_inventory(context_root: Path) -> list[dict[str, Any]]:
        """Return pending and staged proposals for one context.

        Args:
            context_root (Path): Context aggregate root.

        Returns:
            list[dict[str, Any]]: Exact-hash proposal inventory.
        """
        proposals = []
        for path in sorted((context_root / "proposals").glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("status") in {"candidate", "staged"}:
                proposals.append(
                    {
                        "proposal_id": data.get("id", path.stem),
                        "status": data.get("status"),
                        "hash": hash_file(path),
                    }
                )
        return proposals

    @staticmethod
    def _effects() -> dict[str, list[str]]:
        """Return stable author-facing effects for context lifecycle actions.

        Returns:
            dict[str, list[str]]: Action-to-effect descriptions.
        """
        return {
            "deactivate": [
                "block automatic and unpinned selection",
                "preserve the selected immutable context version and pending work",
            ],
            "retire": [
                "withdraw the context from normal future use without deleting entries",
                "block candidate activation until a reviewed restoration",
            ],
            "reactivate": ["verify and reselect the unchanged immutable version"],
            "restore": ["require a hash-bound plan and explicit reviewer approval"],
        }

    @staticmethod
    def _valid_actions(status: str) -> list[str]:
        """Return lifecycle actions valid for one persisted context state.

        Args:
            status (str): Persisted perspective context status.

        Returns:
            list[str]: Valid next lifecycle action identifiers.
        """
        if status == PerspectiveStatus.ACTIVE.value:
            return ["deactivate", "retire-context", "inspect-history"]
        if status == PerspectiveStatus.INACTIVE.value:
            return ["reactivate", "retire-context", "inspect-history"]
        if status == PerspectiveStatus.RETIRED.value:
            return ["restore-context-plan", "inspect-history", "verify-lifecycle"]
        return ["inspect-history", "verify-lifecycle"]

    def deactivate(self, context_id: str, actor: str, reason: str) -> LifecycleReceipt:
        """Deactivate an active context with an immutable receipt.

        Args:
            context_id (str): Stable perspective context identifier.
            actor (str): Human identity responsible for the pause.
            reason (str): Human-readable pause explanation.

        Returns:
            LifecycleReceipt: Immutable context deactivation evidence.
        """
        actor, reason = validate_decision_text(actor, reason)
        return self._transition(
            context_id,
            ContextTransition(
                {PerspectiveStatus.ACTIVE.value},
                PerspectiveStatus.INACTIVE.value,
                "deactivate",
                actor,
                reason,
            ),
        )

    def reactivate(self, context_id: str, actor: str, reason: str) -> LifecycleReceipt:
        """Restore an unchanged context version without creating a new version.

        Args:
            context_id (str): Stable perspective context identifier.
            actor (str): Human identity approving reactivation.
            reason (str): Human-readable reactivation explanation.

        Returns:
            LifecycleReceipt: Immutable context reactivation evidence.
        """
        actor, reason = validate_decision_text(actor, reason)
        return self._transition(
            context_id,
            ContextTransition(
                {PerspectiveStatus.INACTIVE.value},
                PerspectiveStatus.ACTIVE.value,
                "reactivate",
                actor,
                reason,
            ),
        )

    def retire(
        self,
        context_id: str,
        actor: str,
        reason: str,
        *,
        plan_hash: str,
        candidate_disposition: Optional[str] = None,
        proposal_disposition: Optional[str] = None,
    ) -> LifecycleReceipt:
        """Retire a context after resolving pending exact-hash decisions.

        Preserve entries and immutable versions while withdrawing the aggregate
        from future automatic resolution and candidate activation.

        Args:
            context_id (str): Stable perspective context identifier.
            actor (str): Human identity responsible for retirement.
            reason (str): Human-readable retirement explanation.
            plan_hash (str): Exact reviewed retirement plan hash.
            candidate_disposition (Optional[str]): Pending candidate decision. Defaults to
                ``None``.
            proposal_disposition (Optional[str]): Pending proposal decision. Defaults to
                ``None``.

        Returns:
            LifecycleReceipt: Immutable context retirement evidence.

        Raises:
            PerspectiveError: If the plan is stale or a pending decision is missing.
        """
        actor, reason = validate_decision_text(actor, reason)
        plan = self.plan(context_id)
        if plan.binding_hash != plan_hash:
            raise PerspectiveError("Context retirement plan is stale")
        dispositions = []
        pending_candidates = [
            candidate for candidate in plan.candidates if not candidate.get("decision")
        ]
        if pending_candidates:
            if candidate_disposition not in {"retain", "reject", "abandon"}:
                raise PerspectiveError("Pending context candidate requires a disposition")
            dispositions.append(
                LifecycleDisposition(
                    kind="perspective-candidate",
                    stable_id=context_id,
                    artifact_hash=pending_candidates[0]["candidate_hash"],
                    action=str(candidate_disposition),
                )
            )
        if plan.perspective_proposals:
            if proposal_disposition not in {"retain", "reject", "abandon"}:
                raise PerspectiveError("Pending perspective proposals require a disposition")
            dispositions.extend(
                LifecycleDisposition(
                    kind="perspective-proposal",
                    stable_id=item["proposal_id"],
                    artifact_hash=item["hash"],
                    action=str(proposal_disposition),
                )
                for item in plan.perspective_proposals
            )
        return self._transition(
            context_id,
            ContextTransition(
                {PerspectiveStatus.ACTIVE.value, PerspectiveStatus.INACTIVE.value},
                PerspectiveStatus.RETIRED.value,
                "retire-context",
                actor,
                reason,
                plan_hash,
                dispositions,
            ),
        )

    def restore(
        self, context_id: str, requested_by: str, approved_by: str, plan_hash: str
    ) -> LifecycleReceipt:
        """Restore a retired context through explicit request and approval.

        Args:
            context_id (str): Stable perspective context identifier.
            requested_by (str): Human identity requesting restoration.
            approved_by (str): Human identity approving restoration.
            plan_hash (str): Exact reviewed restoration plan hash.

        Returns:
            LifecycleReceipt: Immutable context restoration evidence.

        Raises:
            PerspectiveError: If the restoration plan is stale.
        """
        requested_by, _ = validate_decision_text(requested_by, "context restoration request")
        approved_by, reason = validate_decision_text(
            approved_by, f"reviewed context restoration requested by {requested_by}"
        )
        plan = self.plan(context_id)
        if plan.binding_hash != plan_hash:
            raise PerspectiveError("Context restoration plan is stale")
        return self._transition(
            context_id,
            ContextTransition(
                {PerspectiveStatus.RETIRED.value},
                PerspectiveStatus.ACTIVE.value,
                "restore-context",
                approved_by,
                reason,
                plan_hash,
            ),
        )

    def decide_candidate(
        self,
        context_id: str,
        candidate_hash: str,
        actor: str,
        reason: str,
        action: str = "reject",
    ) -> LifecycleReceipt:
        """Reject or abandon one exact candidate hash while preserving its evidence.

        Keep the candidate in place and persist a content-addressed decision so
        retries remain auditable and stale hashes cannot affect newer work.

        Args:
            context_id (str): Stable perspective context identifier.
            candidate_hash (str): Exact candidate content hash.
            actor (str): Human identity responsible for the decision.
            reason (str): Human-readable decision explanation.
            action (str): Either reject or abandon. Defaults to ``"reject"``.

        Returns:
            LifecycleReceipt: Immutable exact-hash candidate decision.

        Raises:
            PerspectiveError: If the action, candidate, or supplied hash is invalid.
        """
        actor, reason = validate_decision_text(actor, reason)
        if action not in {"reject", "abandon"}:
            raise PerspectiveError("Candidate decision must be reject or abandon")
        candidate_path = self.registry.context_root(context_id) / "candidate" / "manifest.json"
        if not candidate_path.exists():
            raise PerspectiveError("Perspective candidate has not been created")
        candidate = PerspectiveManifest.model_validate_json(
            candidate_path.read_text(encoding="utf-8")
        )
        if candidate.candidate_hash != candidate_hash:
            raise PerspectiveError("Perspective candidate hash is stale")
        item = self.registry.list().get(context_id) or {}
        version, manifest_hash = self._verify_selected(context_id, item)
        registry = self.registry._read()
        digest = hash_json(registry)
        status = str(item.get("status", "candidate"))
        transition = ContextTransition(
            {status},
            status,
            f"{action}-candidate",
            actor,
            reason,
            dispositions=[
                LifecycleDisposition(
                    kind="perspective-candidate",
                    stable_id=context_id,
                    artifact_hash=candidate_hash,
                    action=action,
                )
            ],
        )
        receipt = self._receipt(
            context_id,
            transition,
            ContextTransitionEvidence(status, digest, digest, version, manifest_hash),
        )
        base = self.registry.context_root(context_id)
        path = receipt_path_for(base, receipt)
        decision = base / "candidate-decisions" / f"{candidate_hash.removeprefix('sha256:')}.json"
        AtomicArtifactTransaction(
            [
                (path, receipt.model_dump_json(indent=2)),
                (decision, receipt.model_dump_json(indent=2)),
            ]
        ).commit()
        return receipt

    def verify(self, context_id: str) -> dict[str, Any]:
        """Verify every context lifecycle receipt offline.

        Args:
            context_id (str): Stable perspective context identifier.

        Returns:
            dict[str, Any]: Deterministic offline verification result.
        """
        return verify_receipts(self.root, [self.registry.context_root(context_id)]).model_dump(
            mode="json"
        )

    def migrate_legacy(self, context_id: str, actor: str) -> LifecycleReceipt:
        """Record a reviewed legacy label without inventing the original decision.

        Args:
            context_id (str): Stable perspective context identifier.
            actor (str): Human identity reviewing the legacy state.

        Returns:
            LifecycleReceipt: Immutable legacy migration evidence.

        Raises:
            PerspectiveError: If the state is not legacy-inactive or already has receipts.
        """
        item = self.registry.list().get(context_id)
        if not item:
            raise PerspectiveError(f"Unknown perspective context: {context_id}")
        if item.get("status") != PerspectiveStatus.INACTIVE.value:
            raise PerspectiveError("Only a legacy inactive context can be migrated")
        context_root = self.registry.context_root(context_id)
        if list((context_root / "lifecycle" / "receipts").glob("*.json")):
            raise PerspectiveError("Lifecycle receipts already exist for this context")
        actor, reason = validate_decision_text(
            actor, str(item.get("deactivation_reason") or "not recorded in legacy state")
        )
        version, manifest_hash = self._verify_selected(context_id, item)
        digest = hash_json(self.registry._read())
        receipt = LifecycleReceipt(
            object_type="perspective-context",
            object_id=context_id,
            action="migrate-legacy-deactivation",
            actor=actor,
            reason=reason,
            decided_at=utc_timestamp(),
            prior_status=PerspectiveStatus.INACTIVE.value,
            resulting_status=PerspectiveStatus.INACTIVE.value,
            prior_registry_hash=digest,
            resulting_registry_hash=digest,
            selected_version=version,
            selected_manifest_hash=manifest_hash,
            legacy_migration=True,
        )
        path = receipt_path_for(context_root, receipt)
        AtomicArtifactTransaction([(path, receipt.model_dump_json(indent=2))]).commit()
        return receipt

    def _transition(self, context_id: str, transition: ContextTransition) -> LifecycleReceipt:
        """Apply one validated context transition as an atomic transaction.

        Persist exact-hash reject and abandon dispositions beside the aggregate
        receipt so later candidate resolution cannot silently revive them.

        Args:
            context_id (str): Stable perspective context identifier.
            transition (ContextTransition): Validated lifecycle transition.

        Returns:
            LifecycleReceipt: Immutable transition evidence.

        Raises:
            PerspectiveError: If the context is unknown or in an invalid state.
        """
        context_root = self.registry.context_root(context_id)
        with ActivationLock(
            context_root / ".lifecycle.lock",
            "Perspective lifecycle operation is already in progress",
            PerspectiveError,
        ):
            registry = self.registry._read()
            item = registry["contexts"].get(context_id)
            if not item:
                raise PerspectiveError(f"Unknown perspective context: {context_id}")
            prior = str(item.get("status"))
            if prior not in transition.expected:
                if prior == PerspectiveStatus.RETIRED.value and transition.action == "reactivate":
                    raise PerspectiveError("Retired contexts require the reviewed restore path")
                raise PerspectiveError(
                    f"Perspective context cannot {transition.action} from {prior}"
                )
            version, manifest_hash = self._verify_selected(context_id, item)
            before_hash = hash_json(registry)
            item["status"] = transition.resulting
            item["lifecycle_actor"] = transition.actor
            item["lifecycle_reason"] = transition.reason
            item["lifecycle_decided_at"] = utc_timestamp()
            after_hash = hash_json(registry)
            receipt = self._receipt(
                context_id,
                transition,
                ContextTransitionEvidence(prior, before_hash, after_hash, version, manifest_hash),
            )
            receipt_path = receipt_path_for(context_root, receipt)
            updates = [
                (self.registry.registry_path, json.dumps(registry, indent=2)),
                (receipt_path, receipt.model_dump_json(indent=2)),
            ]
            for disposition in transition.dispositions:
                if disposition.action not in {"reject", "abandon"}:
                    continue
                decision_group = (
                    "candidate-decisions"
                    if disposition.kind == "perspective-candidate"
                    else "proposal-decisions"
                )
                decision_path = (
                    context_root
                    / decision_group
                    / f"{disposition.artifact_hash.removeprefix('sha256:')}.json"
                )
                updates.append((decision_path, receipt.model_dump_json(indent=2)))
            AtomicArtifactTransaction(updates).commit()
            return receipt

    def _verify_selected(self, context_id: str, item: dict) -> tuple[str, str]:
        """Verify and return selected immutable context-version evidence.

        Args:
            context_id (str): Stable perspective context identifier.
            item (dict): Current perspective registry entry.

        Returns:
            tuple[str, str]: Selected version and manifest hash.

        Raises:
            PerspectiveError: If version evidence is absent or inconsistent.
        """
        version = item.get("active_version")
        if not version:
            raise PerspectiveError(f"Perspective context {context_id} has no selected version")
        path = self.registry.context_root(context_id) / "versions" / version
        manifest_path = path / "manifest.json"
        if not manifest_path.exists():
            raise PerspectiveError(f"Missing perspective version {context_id}@{version}")
        manifest = PerspectiveManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        mismatches = verify_components(path, manifest.components, manifest.component_hashes)
        if mismatches:
            raise PerspectiveError(f"Selected perspective component hash mismatch: {mismatches[0]}")
        return str(version), hash_file(manifest_path)

    def _receipt(
        self,
        context_id: str,
        transition: ContextTransition,
        evidence: ContextTransitionEvidence,
    ) -> LifecycleReceipt:
        """Build an immutable perspective context transition receipt.

        Args:
            context_id (str): Stable perspective context identifier.
            transition (ContextTransition): Validated lifecycle transition.
            evidence (ContextTransitionEvidence): Registry and version evidence.

        Returns:
            LifecycleReceipt: Complete hash-bound context lifecycle receipt.
        """
        return LifecycleReceipt(
            object_type="perspective-context",
            object_id=context_id,
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
            predecessor_receipt=(
                str(Path(previous).relative_to(self.root))
                if (previous := latest_receipt(self.registry.context_root(context_id)))
                else None
            ),
            plan_hash=transition.plan_hash,
        )
