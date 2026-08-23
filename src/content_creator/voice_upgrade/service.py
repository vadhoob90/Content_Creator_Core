"""Coordinate planning and retry-safe construction of governed voice upgrades."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from ..storage import RunStore
from ..versioned_artifacts import ActivationLock, hash_file, hash_json
from ..voice_builder import VoiceBuilder
from ..voice_models import VoiceManifest, VoiceStrategy, VoiceWorkOrder
from ..voices import VoiceRegistry
from .epochs import active_learning_records, epoch_hash, load_epoch
from .evidence import (
    authorised_evidence,
    combined_evidence,
    evidence_delta,
    evidence_set_hash,
    load_evidence_baseline,
    retrieval_locators,
)
from .guidance import write_learning_change_set
from .models import (
    EvidenceSet,
    LearningClassification,
    LearningDispositionAction,
    LearningSelection,
    VoiceUpgradeBuildContext,
    VoiceUpgradeMode,
    VoiceUpgradePlan,
    VoiceUpgradeState,
)


class VoiceUpgradeError(RuntimeError):
    """Report invalid or stale governed voice-upgrade operations."""


class VoiceUpgradeService:
    """Provide the application boundary for voice upgrade planning and builds."""

    def __init__(self, root: Path, builder: VoiceBuilder):
        """Initialize voice-upgrade collaborators.

        Args:
            root (Path): Workspace root.
            builder (VoiceBuilder): Provider-neutral voice candidate builder.

        Returns:
            None: The service is initialized in place.
        """
        self.root = root.resolve()
        self.builder = builder
        self.registry = VoiceRegistry(self.root)

    def plan(
        self,
        voice_id: str,
        mode: VoiceUpgradeMode = VoiceUpgradeMode.INCREMENTAL,
        provider: Optional[str] = None,
        offline_analysis: bool = False,
    ) -> VoiceUpgradePlan:
        """Create a plan for immutable evidence and learning eligibility.

        Bind the plan to the exact active candidate, represented evidence, current
        content-hash delta, learning epoch, mode, and provider before any model work.

        Args:
            voice_id (str): Selected voice identifier.
            mode (VoiceUpgradeMode): Requested analysis mode. Defaults to
                ``VoiceUpgradeMode.INCREMENTAL``.
            provider (Optional[str]): Selected provider, when model analysis is intended.
                Defaults to ``None``.
            offline_analysis (bool): Avoid provider execution. Defaults to ``False``.

        Returns:
            VoiceUpgradePlan: Persisted, hash-bound author-facing plan.
        """
        active, directory, manifest = self._active(voice_id)
        order = self.builder.load_work_order(voice_id)
        baseline = load_evidence_baseline(self.root, voice_id, directory, manifest)
        current, duplicates = authorised_evidence(self.root, order)
        delta = evidence_delta(current, baseline)
        epoch = load_epoch(
            self.root,
            voice_id,
            manifest.version,
            migrate_legacy=True,
        )
        learning_records = active_learning_records(epoch)
        binding = self._binding(manifest, baseline, delta, epoch_hash(epoch), mode, provider)
        state = self._plan_state(mode, delta, learning_records, provider, offline_analysis)
        transition = (
            "starter-neutral-to-source-derived"
            if manifest.strategy in {VoiceStrategy.STARTER, VoiceStrategy.STARTER_NEUTRAL}
            else None
        )
        plan = VoiceUpgradePlan(
            voice_id=voice_id,
            mode=mode,
            state=state,
            generated_at=datetime.now(UTC).isoformat(),
            baseline_version=manifest.version,
            baseline_candidate_hash=manifest.candidate_hash,
            baseline_manifest_hash=hash_file(directory / "manifest.json"),
            baseline_strategy=(
                "starter-neutral"
                if manifest.strategy in {VoiceStrategy.STARTER, VoiceStrategy.STARTER_NEUTRAL}
                else manifest.strategy.value
            ),
            strategy_transition=transition,
            evidence_cutoff=current.evidence_cutoff,
            evidence_baseline_hash=evidence_set_hash(baseline),
            evidence_delta_hash=evidence_set_hash(delta),
            learning_epoch_hash=epoch_hash(epoch),
            binding_hash=binding,
            provider=provider,
            execution_mode="offline-deterministic" if offline_analysis else "provider-assisted",
            historical_private_corpus_transmitted=(
                mode == VoiceUpgradeMode.FULL_CORPUS and not offline_analysis
            ),
            evidence_baseline_count=len(baseline.records),
            evidence_delta_count=len(delta.records),
            learning_record_count=len(learning_records),
            proposed_learning_classifications=self._classification_proposals(learning_records),
            duplicates=duplicates,
            data_sharing=self._data_sharing(
                mode, baseline, delta, learning_records, provider, offline_analysis
            ),
            exact_commands=self._commands(
                voice_id,
                mode,
                bool(learning_records),
                provider,
                offline_analysis,
            ),
        )
        self._persist_plan(plan, baseline, current, delta, learning_records)
        return plan

    def build(
        self,
        voice_id: str,
        selection_path: Optional[Path],
        *,
        idempotency_key: Optional[str] = None,
        provider_sharing_approved: bool = False,
        explicit_change_set: Optional[Path] = None,
    ) -> VoiceManifest:
        """Build a candidate only from a fresh plan and reviewed dispositions.

        Recompute every plan binding, enforce provider-sharing approval, and hold the
        shared lifecycle lock across candidate construction and publication.

        Args:
            voice_id (str): Selected voice identifier.
            selection_path (Optional[Path]): Reviewed learning-selection JSON. Defaults to
                ``None`` when the epoch has no active records.
            idempotency_key (Optional[str]): Stable retry key. Defaults to ``None``.
            provider_sharing_approved (bool): Approve full-corpus provider sharing.
                Defaults to ``False``.
            explicit_change_set (Optional[Path]): Additional semantic rule changes.
                Defaults to ``None``.

        Returns:
            VoiceManifest: Built candidate manifest awaiting deterministic approval.

        Raises:
            VoiceUpgradeError: If the plan, evidence, selection, or approval is invalid.
        """
        upgrade_root = self._upgrade_root(voice_id)
        plan = VoiceUpgradePlan.model_validate_json(
            (upgrade_root / "voice-upgrade-plan.json").read_text(encoding="utf-8")
        )
        if plan.state in {
            VoiceUpgradeState.NO_MATERIAL_CHANGE,
            VoiceUpgradeState.INSUFFICIENT_DELTA,
        }:
            raise VoiceUpgradeError(
                "Voice upgrade cannot build from plan state {}".format(plan.state.value)
            )
        baseline = EvidenceSet.model_validate_json(
            (upgrade_root / "evidence-baseline.json").read_text(encoding="utf-8")
        )
        delta = EvidenceSet.model_validate_json(
            (upgrade_root / "evidence-delta.json").read_text(encoding="utf-8")
        )
        if plan.mode == VoiceUpgradeMode.FULL_CORPUS:
            if plan.execution_mode != "offline-deterministic" and not provider_sharing_approved:
                raise VoiceUpgradeError("Full-corpus provider sharing requires explicit approval")
        current = self._validate_fresh(plan, baseline, delta)
        selection, records = self._validated_selection(plan, selection_path)
        analysis_set = current if plan.mode == VoiceUpgradeMode.FULL_CORPUS else delta
        fingerprint = hash_json(
            {
                "binding_hash": plan.binding_hash,
                "selection": selection.model_dump(mode="json"),
                "mode": plan.mode.value,
                "change_set": hash_file(explicit_change_set) if explicit_change_set else None,
            }
        )
        prior = self._idempotent_result(voice_id, idempotency_key, fingerprint)
        if prior:
            return prior
        change_set = write_learning_change_set(
            upgrade_root / "combined-change-set.json",
            selection,
            records,
            explicit_change_set,
        )
        represented = combined_evidence(baseline, delta)
        context = VoiceUpgradeBuildContext(
            plan=plan,
            evidence_baseline=baseline,
            evidence_delta=delta,
            represented_evidence=represented,
            learning_selection=selection,
            selected_learning_records=records,
            build_fingerprint=fingerprint,
        )
        filtered, source_ids = self._filtered_order(voice_id, analysis_set)
        manifest = self._execute_build(plan, context, filtered, source_ids, change_set)
        plan.state = (
            VoiceUpgradeState.AWAITING_APPROVAL
            if manifest.status.value == "awaiting_approval"
            else VoiceUpgradeState.BUILT
        )
        plan.candidate_hash = manifest.candidate_hash
        self._write_plan(plan)
        self._record_idempotency(voice_id, idempotency_key, fingerprint, manifest)
        return manifest

    def _execute_build(
        self,
        plan: VoiceUpgradePlan,
        context: VoiceUpgradeBuildContext,
        order: VoiceWorkOrder,
        source_ids: dict[str, str],
        change_set: Path,
    ) -> VoiceManifest:
        """Run candidate construction while holding the complete lifecycle lock.

        Args:
            plan (VoiceUpgradePlan): Durable plan whose state is updated.
            context (VoiceUpgradeBuildContext): Validated candidate build context.
            order (VoiceWorkOrder): Filtered authorised analysis order.
            source_ids (dict[str, str]): Stable evidence IDs by locator.
            change_set (Path): Combined explicit semantic changes.

        Returns:
            VoiceManifest: Built candidate manifest.
        """
        voice_id = plan.voice_id
        lock = self.root / "profiles" / voice_id / ".lifecycle.lock"
        try:
            with ActivationLock(
                lock,
                "Voice upgrade build or activation is already in progress",
                VoiceUpgradeError,
            ):
                plan.state = VoiceUpgradeState.BUILDING
                self._write_plan(plan)
                manifest = self.builder.build(
                    voice_id,
                    change_set=change_set,
                    order_override=order,
                    upgrade_context=context,
                    source_ids=source_ids,
                    lifecycle_lock_held=True,
                )
        except Exception:
            plan.state = VoiceUpgradeState.FAILED
            self._write_plan(plan)
            raise
        return manifest

    def _filtered_order(
        self, voice_id: str, analysis_set: EvidenceSet
    ) -> tuple[VoiceWorkOrder, dict[str, str]]:
        """Return an analysis order containing only the selected evidence set.

        Args:
            voice_id (str): Selected voice identifier.
            analysis_set (EvidenceSet): Incremental delta or complete current corpus.

        Returns:
            tuple[VoiceWorkOrder, dict[str, str]]: Filtered order and stable source IDs.
        """
        order = self.builder.load_work_order(voice_id)
        locators = retrieval_locators(self.root, order)
        selected = [(item, locators[item.evidence_id]) for item in analysis_set.records]
        filtered = order.model_copy(deep=True)
        filtered.urls = [
            locator for _, locator in selected if locator.startswith(("http://", "https://"))
        ]
        filtered.documents = [
            locator for _, locator in selected if not locator.startswith(("http://", "https://"))
        ]
        return filtered, {locator: item.evidence_id for item, locator in selected}

    def _active(self, voice_id: str) -> tuple[dict, Path, VoiceManifest]:
        """Return the verified active registry record, directory, and manifest.

        Args:
            voice_id (str): Selected voice identifier.

        Returns:
            tuple[dict, Path, VoiceManifest]: Verified active voice values.
        """
        resolved = self.registry.resolve(voice_id)
        directory = self.root / resolved["path"]
        manifest = VoiceManifest.model_validate_json(
            (directory / "manifest.json").read_text(encoding="utf-8")
        )
        return resolved, directory, manifest

    def _validate_fresh(
        self, plan: VoiceUpgradePlan, baseline: EvidenceSet, expected_delta: EvidenceSet
    ) -> EvidenceSet:
        """Reject a build when any bound active evidence or learning state changed.

        Args:
            plan (VoiceUpgradePlan): Persisted upgrade plan.
            baseline (EvidenceSet): Bound evidence baseline.
            expected_delta (EvidenceSet): Bound evidence delta.

        Returns:
            EvidenceSet: Fresh current authorised evidence.

        Raises:
            VoiceUpgradeError: If a bound baseline changed after planning.
        """
        _, _, manifest = self._active(plan.voice_id)
        order = self.builder.load_work_order(plan.voice_id)
        current, _ = authorised_evidence(self.root, order)
        delta = evidence_delta(current, baseline)
        epoch = load_epoch(self.root, plan.voice_id, manifest.version)
        checks = {
            "active version": manifest.version == plan.baseline_version,
            "active candidate hash": manifest.candidate_hash == plan.baseline_candidate_hash,
            "evidence baseline": evidence_set_hash(baseline) == plan.evidence_baseline_hash,
            "evidence delta": evidence_set_hash(delta) == evidence_set_hash(expected_delta),
            "learning epoch": epoch_hash(epoch) == plan.learning_epoch_hash,
        }
        stale = [name for name, valid in checks.items() if not valid]
        if stale:
            raise VoiceUpgradeError("Voice upgrade plan is stale: {}".format(", ".join(stale)))
        return current

    def _validated_selection(
        self, plan: VoiceUpgradePlan, path: Optional[Path]
    ) -> tuple[LearningSelection, list[dict]]:
        """Validate complete explicit dispositions against the bound epoch.

        Args:
            plan (VoiceUpgradePlan): Persisted upgrade plan.
            path (Optional[Path]): Reviewed selection file.

        Returns:
            tuple[LearningSelection, list[dict]]: Validated selection and epoch records.

        Raises:
            VoiceUpgradeError: If dispositions are missing, stale, duplicated, or unknown.
        """
        epoch = load_epoch(self.root, plan.voice_id, plan.baseline_version)
        records = active_learning_records(epoch)
        if path is None and records:
            raise VoiceUpgradeError("Active prior-version learning requires a reviewed selection")
        selection = (
            LearningSelection.model_validate_json(path.read_text(encoding="utf-8"))
            if path
            else LearningSelection(
                voice_id=plan.voice_id,
                baseline_version=plan.baseline_version,
                learning_epoch_hash=plan.learning_epoch_hash,
                reviewed_by="no-active-learning",
                reviewed_at=plan.generated_at,
            )
        )
        expected = {str(record.get("id")) for record in records}
        supplied = [item.learning_id for item in selection.dispositions]
        if (
            selection.voice_id != plan.voice_id
            or selection.baseline_version != plan.baseline_version
        ):
            raise VoiceUpgradeError("Learning selection targets a different voice baseline")
        if selection.learning_epoch_hash != plan.learning_epoch_hash:
            raise VoiceUpgradeError("Learning selection targets a stale learning epoch")
        if len(supplied) != len(set(supplied)) or set(supplied) != expected:
            raise VoiceUpgradeError("Every active prior-version learning needs one disposition")
        return selection, records

    @staticmethod
    def _binding(
        manifest: VoiceManifest,
        baseline: EvidenceSet,
        delta: EvidenceSet,
        learning_hash: str,
        mode: VoiceUpgradeMode,
        provider: Optional[str],
    ) -> str:
        """Return the immutable input binding for a plan.

        Args:
            manifest (VoiceManifest): Active immutable manifest.
            baseline (EvidenceSet): Represented evidence baseline.
            delta (EvidenceSet): Current evidence delta.
            learning_hash (str): Exact active learning-epoch hash.
            mode (VoiceUpgradeMode): Selected analysis mode.
            provider (Optional[str]): Selected provider.

        Returns:
            str: Canonical plan binding hash.
        """
        return hash_json(
            {
                "version": manifest.version,
                "candidate_hash": manifest.candidate_hash,
                "baseline": evidence_set_hash(baseline),
                "delta": evidence_set_hash(delta),
                "learning_epoch": learning_hash,
                "mode": mode.value,
                "provider": provider,
            }
        )

    @staticmethod
    def _plan_state(
        mode: VoiceUpgradeMode,
        delta: EvidenceSet,
        learning_records: list[dict],
        provider: Optional[str],
        offline_analysis: bool,
    ) -> VoiceUpgradeState:
        """Return the safe next state for inventoried upgrade inputs.

        Args:
            mode (VoiceUpgradeMode): Requested incremental or full-corpus mode.
            delta (EvidenceSet): Newly authorised evidence not in the active baseline.
            learning_records (list[dict]): Active prior-version learning records.
            provider (Optional[str]): Selected model provider, when any.
            offline_analysis (bool): Whether provider execution is disabled.

        Returns:
            VoiceUpgradeState: Required review, approval, no-op, or build-ready state.
        """
        if mode == VoiceUpgradeMode.FULL_CORPUS and provider and not offline_analysis:
            return VoiceUpgradeState.AWAITING_PROVIDER_APPROVAL
        if learning_records:
            return VoiceUpgradeState.AWAITING_SELECTION
        if mode == VoiceUpgradeMode.INCREMENTAL and not delta.records:
            return VoiceUpgradeState.NO_MATERIAL_CHANGE
        if (
            mode == VoiceUpgradeMode.INCREMENTAL
            and sum(item.word_count for item in delta.records) < 500
        ):
            return VoiceUpgradeState.INSUFFICIENT_DELTA
        return VoiceUpgradeState.PLANNED

    @staticmethod
    def _classification_proposals(records: list[dict]) -> list[dict[str, object]]:
        """Return conservative non-promoting proposals for author review.

        Args:
            records (list[dict]): Active learning records requiring disposition.

        Returns:
            list[dict[str, object]]: Review proposals that never auto-promote learning.
        """
        return [
            {
                "learning_id": record.get("id"),
                "proposed_classification": LearningClassification.REMAIN_LEARNING.value,
                "proposed_disposition": LearningDispositionAction.CARRY_FORWARD.value,
                "reason": "Core does not promote active learning without explicit review.",
            }
            for record in records
        ]

    @staticmethod
    def _data_sharing(
        mode: VoiceUpgradeMode,
        baseline: EvidenceSet,
        delta: EvidenceSet,
        records: list[dict],
        provider: Optional[str],
        offline: bool,
    ) -> dict[str, object]:
        """Return privacy and provider disclosures for the plan.

        Args:
            mode (VoiceUpgradeMode): Requested analysis mode.
            baseline (EvidenceSet): Evidence represented by the active version.
            delta (EvidenceSet): Newly authorised evidence.
            records (list[dict]): Active prior-version learning records.
            provider (Optional[str]): Selected provider, when any.
            offline (bool): Whether analysis avoids provider execution.

        Returns:
            dict[str, object]: Counts and explicit historical-text sharing disclosures.
        """
        return {
            "mode": mode.value,
            "provider": provider,
            "execution_mode": "offline-deterministic" if offline else "provider-assisted",
            "source_count": len(baseline.records) + len(delta.records)
            if mode == VoiceUpgradeMode.FULL_CORPUS
            else len(delta.records),
            "learning_record_count": len(records),
            "historical_private_corpus_text_transmitted": mode == VoiceUpgradeMode.FULL_CORPUS
            and not offline,
            "cached_baseline_measurements_avoid_retransmission": mode
            == VoiceUpgradeMode.INCREMENTAL,
        }

    @staticmethod
    def _commands(
        voice_id: str,
        mode: VoiceUpgradeMode,
        has_learning: bool,
        provider: Optional[str],
        offline: bool,
    ) -> list[list[str]]:
        """Return exact calm author commands for the planned route.

        Args:
            voice_id (str): Selected voice identifier.
            mode (VoiceUpgradeMode): Requested analysis mode.
            has_learning (bool): Whether a reviewed selection file is required.
            provider (Optional[str]): Provider bound to the plan, when any.
            offline (bool): Whether the build must avoid provider execution.

        Returns:
            list[list[str]]: Tokenized build, diff, and approval commands.
        """
        build = ["voice", "upgrade", voice_id, "--mode", mode.value]
        if provider:
            build.extend(["--provider", provider])
        if offline:
            build.append("--offline-analysis")
        if has_learning:
            build.extend(
                [
                    "--learning-selection",
                    "profiles/{}/upgrade/learning-selection.json".format(voice_id),
                ]
            )
        return [
            build,
            ["voice", "diff", voice_id],
            ["voice", "approve", voice_id, "--approved-by", "<author>"],
        ]

    def _persist_plan(
        self,
        plan: VoiceUpgradePlan,
        baseline: EvidenceSet,
        current: EvidenceSet,
        delta: EvidenceSet,
        records: list[dict],
    ) -> None:
        """Persist independently verifiable plan inputs and a review template.

        Args:
            plan (VoiceUpgradePlan): Hash-bound upgrade plan.
            baseline (EvidenceSet): Evidence represented by the active version.
            current (EvidenceSet): Complete currently authorised evidence.
            delta (EvidenceSet): Content-hash set difference from the baseline.
            records (list[dict]): Active learning records awaiting disposition.

        Returns:
            None: Plan inputs and the selection template are stored durably.
        """
        root = self._upgrade_root(plan.voice_id)
        root.mkdir(parents=True, exist_ok=True)
        RunStore._atomic_text(root / "evidence-baseline.json", baseline.model_dump_json(indent=2))
        RunStore._atomic_text(
            root / "currently-authorised-evidence.json", current.model_dump_json(indent=2)
        )
        RunStore._atomic_text(root / "evidence-delta.json", delta.model_dump_json(indent=2))
        RunStore._atomic_text(root / "voice-upgrade-plan.json", plan.model_dump_json(indent=2))
        template = {
            "schema_version": "1.0",
            "voice_id": plan.voice_id,
            "baseline_version": plan.baseline_version,
            "learning_epoch_hash": plan.learning_epoch_hash,
            "reviewed_by": "REPLACE WITH REVIEWER",
            "reviewed_at": datetime.now(UTC).isoformat(),
            "dispositions": [
                {
                    "learning_id": record.get("id"),
                    "classification": "remain-learning",
                    "disposition": "carry-forward",
                    "rationale": "Review and replace this rationale.",
                    "confidence": record.get("confidence", 1.0),
                }
                for record in records
            ],
        }
        RunStore._atomic_text(
            root / "learning-selection.template.json", json.dumps(template, indent=2)
        )

    def _write_plan(self, plan: VoiceUpgradePlan) -> None:
        """Persist the current durable plan state.

        Args:
            plan (VoiceUpgradePlan): Upgrade plan with its latest lifecycle state.

        Returns:
            None: The durable plan file is replaced atomically.
        """
        RunStore._atomic_text(
            self._upgrade_root(plan.voice_id) / "voice-upgrade-plan.json",
            plan.model_dump_json(indent=2),
        )

    def _upgrade_root(self, voice_id: str) -> Path:
        """Return the durable upgrade workflow directory for one voice.

        Args:
            voice_id (str): Selected voice identifier.

        Returns:
            Path: Repository-private workflow directory.
        """
        return self.root / "profiles" / voice_id / "upgrade"

    def _idempotent_result(
        self, voice_id: str, key: Optional[str], fingerprint: str
    ) -> Optional[VoiceManifest]:
        """Return a prior equivalent candidate or reject key reuse.

        Args:
            voice_id (str): Selected voice identifier.
            key (Optional[str]): Caller-supplied retry key.
            fingerprint (str): Canonical build-input fingerprint.

        Returns:
            Optional[VoiceManifest]: Equivalent available candidate, if previously built.

        Raises:
            VoiceUpgradeError: If the key binds different inputs or a missing candidate.
        """
        if not key:
            return None
        path = self._idempotency_path(voice_id, key)
        if not path.is_file():
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("build_fingerprint") != fingerprint:
            raise VoiceUpgradeError("Voice upgrade idempotency key was reused for changed inputs")
        manifest_path = self.root / "profiles" / voice_id / "candidate" / "manifest.json"
        manifest = VoiceManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        if manifest.candidate_hash != record.get("candidate_hash"):
            raise VoiceUpgradeError("Idempotent candidate is no longer available")
        return manifest

    def _record_idempotency(
        self,
        voice_id: str,
        key: Optional[str],
        fingerprint: str,
        manifest: VoiceManifest,
    ) -> None:
        """Persist a stable build retry receipt when a key was supplied.

        Args:
            voice_id (str): Selected voice identifier.
            key (Optional[str]): Caller-supplied retry key.
            fingerprint (str): Canonical build-input fingerprint.
            manifest (VoiceManifest): Candidate produced by those exact inputs.

        Returns:
            None: A hashed-key receipt is written only when a key exists.
        """
        if not key:
            return
        RunStore._atomic_text(
            self._idempotency_path(voice_id, key),
            json.dumps(
                {"build_fingerprint": fingerprint, "candidate_hash": manifest.candidate_hash},
                indent=2,
            ),
        )

    def _idempotency_path(self, voice_id: str, key: str) -> Path:
        """Return the privacy-safe hashed idempotency receipt path.

        Args:
            voice_id (str): Selected voice identifier.
            key (str): Caller-supplied retry key to hash before persistence.

        Returns:
            Path: Receipt path that does not expose the raw key.
        """
        return (
            self._upgrade_root(voice_id)
            / "build-idempotency"
            / "{}.json".format(RunStore.idempotency_key_hash(key))
        )
