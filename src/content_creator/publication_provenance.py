"""Create and verify privacy-safe publication provenance receipts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .domain import RunState, RunStatus, utc_now
from .packs import PackRegistry
from .perspective_evaluation import evaluate_perspective_output
from .perspective_semantic_review import SemanticReviewReceipt
from .perspectives import PerspectiveEntryStatus, PerspectiveRegistry
from .production_governance import governance_hash, production_governance
from .publication_governance import verify_production_governance
from .publication_models import (
    PublicationFinding,
    PublicationPolicy,
    PublicationProvenanceError,
    provenance_source,
)
from .publication_package_receipts import PublicationPackageReceipts
from .publication_receipt_models import (
    PerspectiveEvaluationReceipt,
    PerspectiveReceipt,
    PublicationBaseline,
    PublicationBaselineEntry,
    PublicationReceipt,
)
from .storage import RunStore, StorageError
from .versioned_artifacts import hash_file, hash_json
from .voices import VoiceRegistry


class PublicationProvenance:
    """Manage publication gates and deterministic tracked evidence."""

    def __init__(self, root: Path, policy: Dict[str, Any]):
        """Initialize publication provenance for a workspace.

        Args:
            root (Path): Workspace root.
            policy (Dict[str, Any]): Validated publication-provenance policy.

        Returns:
            None: The service is initialized in place.
        """
        self.root = root.resolve()
        self.policy = policy
        self.receipts_root = self._within_root(str(policy["receipts_directory"]))
        self.baseline_path = self.receipts_root / "baseline.json"
        self.packages = PublicationPackageReceipts(self.root, self.receipts_root)

    def evaluate(self, state: RunState, draft: str) -> Dict[str, Any]:
        """Evaluate the exact bytes proposed for publication.

        Args:
            state (RunState): Reviewed run being published.
            draft (str): Exact publication content.

        Returns:
            Dict[str, Any]: Deterministic perspective evaluation.

        Raises:
            PublicationProvenanceError: If provenance is invalid.
        """
        order = state.work_order
        evaluation = evaluate_perspective_output(self.root, order, draft)
        failures = list(evaluation["errors"])
        try:
            VoiceRegistry(self.root).resolve(order.voice_id, order.voice_version)
            self._perspective_receipts(order, strict=True)
        except Exception as exc:
            failures.append(str(exc))
        if failures:
            raise PublicationProvenanceError("; ".join(dict.fromkeys(failures)))
        return evaluation

    def issue(
        self,
        state: RunState,
        target: Path,
        evaluation: Dict[str, Any],
        evaluation_artifact_hash: str,
        semantic_review: SemanticReviewReceipt,
    ) -> Path:
        """Write the tracked receipt for a successful publication.

        Pin the resolved pack, voice, perspectives, exact artifact, and review
        evidence without copying private run content into tracked provenance.

        Args:
            state (RunState): Published in-memory run state.
            target (Path): Published artifact path.
            evaluation (Dict[str, Any]): Exact-draft deterministic evaluation.
            evaluation_artifact_hash (str): Hash of the ignored run evaluation artifact.
            semantic_review (SemanticReviewReceipt): Privacy-safe semantic review summary.

        Returns:
            Path: Written receipt path.

        Raises:
            PublicationProvenanceError: If the receipt would overwrite existing evidence.
        """
        relative_target = self._relative(target)
        voice = VoiceRegistry(self.root).resolve(
            state.work_order.voice_id,
            state.work_order.voice_version,
        )
        pack = PackRegistry(self.root).resolve(
            state.work_order.content_pack,
            state.work_order.pack_options,
        )
        production_manifest_path = self.root / "runs" / state.id / "production-manifest.json"
        production_governance_hash = governance_hash(production_governance(self.root, state))
        receipt = PublicationReceipt(
            artifact_path=relative_target,
            artifact_hash=hash_file(target),
            artifacts=self.packages.artifacts(state, target),
            run_id=state.id,
            final_status=RunStatus.PUBLISHED.value,
            content_pack_id=pack.id,
            content_pack_version=pack.version,
            voice_id=state.work_order.voice_id,
            voice_version=str(state.work_order.voice_version),
            voice_manifest_hash=voice.get("manifest_hash"),
            production_manifest_path=(
                str(production_manifest_path.relative_to(self.root))
                if production_manifest_path.is_file()
                else None
            ),
            production_governance_hash=production_governance_hash,
            author_contribution_provenance=provenance_source(state),
            perspectives=self._perspective_receipts(state.work_order, strict=True),
            perspective_evaluation=PerspectiveEvaluationReceipt(
                passed=bool(evaluation["passed"]),
                artifact_hash=evaluation_artifact_hash,
                errors=list(evaluation["errors"]),
                position_marker_count=len(evaluation["position_markers"]),
                selected_entry_ids=list(evaluation["selected_entry_ids"]),
            ),
            semantic_review=semantic_review,
            published_at=utc_now().isoformat(),
        )
        receipt_path = self.receipt_path(relative_target)
        if receipt_path.exists():
            raise PublicationProvenanceError(f"Refusing to overwrite {receipt_path}")
        RunStore._atomic_text(receipt_path, receipt.model_dump_json(indent=2))
        return receipt_path

    def verify(
        self,
        *,
        run_id: Optional[str] = None,
        artifact_path: Optional[str] = None,
        receipt_path: Optional[str] = None,
        new_only: bool = False,
    ) -> Dict[str, Any]:
        """Verify all configured publication destinations and receipts.

        Apply at most one optional scope so a current package can be distinguished
        from unrelated legacy debt while the unscoped mode retains repository-wide CI.

        Args:
            run_id (Optional[str]): Originating run to verify. Defaults to ``None``.
            artifact_path (Optional[str]): Canonical artifact path. Defaults to ``None``.
            receipt_path (Optional[str]): Canonical receipt path. Defaults to ``None``.
            new_only (bool): Exclude unchanged baseline artifacts. Defaults to ``False``.

        Returns:
            Dict[str, Any]: Deterministic CI-ready verification report.

        Raises:
            PublicationProvenanceError: If an explicit run or receipt scope is unavailable.
        """
        policy = PublicationPolicy(self.policy["policy"])
        if policy == PublicationPolicy.OFF:
            return self._report(policy, [], 0, 0, "disabled")
        baseline = self._load_baseline()
        if receipt_path:
            if not (selected_receipt := self._within_root(receipt_path)).is_file():
                raise PublicationProvenanceError("Publication receipt does not exist")
            try:
                selected = PublicationReceipt.model_validate_json(
                    selected_receipt.read_text(encoding="utf-8")
                )
            except Exception as exc:
                finding = self._finding("invalid_receipt", None, str(exc))
                return self._report(policy, [finding], 0, 1, "failed")
            findings = self._verify_receipt(selected_receipt, selected.artifact_path)
            return self._report(policy, findings, 1, 1, "failed" if findings else "ok")
        try:
            artifacts = self.packages.select_primary(
                self._published_artifacts(),
                baseline,
                run_id,
                artifact_path,
                new_only,
            )
        except StorageError as exc:
            raise PublicationProvenanceError(str(exc)) from exc
        artifacts, missing = self.packages.existing_primary(artifacts)
        findings = [PublicationFinding.model_validate(item) for item in missing]
        receipt_count = 0
        for artifact in artifacts:
            relative = self._relative(artifact)
            canonical_receipt = self.receipt_path(relative)
            if not canonical_receipt.exists():
                if self._receipt_required(policy, artifact, relative, baseline):
                    findings.append(
                        self._finding("missing_receipt", relative, "Publication has no receipt")
                    )
                continue
            receipt_count += 1
            findings.extend(self._verify_receipt(canonical_receipt, expected_artifact=relative))
        known = {self.receipt_path(self._relative(path)).resolve() for path in artifacts}
        if not any((run_id, artifact_path, new_only)):
            receipt_files = self._receipt_files()
        else:
            receipt_files = []
        for candidate_receipt in receipt_files:
            if candidate_receipt.resolve() not in known:
                findings.append(
                    self._finding(
                        "orphan_receipt",
                        None,
                        f"Receipt has no published artifact: {self._relative(candidate_receipt)}",
                    )
                )
        failed_status = "advisory" if policy == PublicationPolicy.ADVISORY else "failed"
        status = failed_status if findings else "ok"
        return self._report(policy, findings, len(artifacts), receipt_count, status)

    def write_baseline(self, replace: bool = False) -> Dict[str, Any]:
        """Record current unreceipted publications as the prospective baseline.

        Args:
            replace (bool): Replace an existing baseline when true. Defaults to ``False``.

        Returns:
            Dict[str, Any]: Serialized baseline metadata.

        Raises:
            PublicationProvenanceError: If a baseline already exists.
        """
        if self.baseline_path.exists() and not replace:
            raise PublicationProvenanceError(
                "Publication baseline already exists; pass --replace-baseline to replace it"
            )
        entries = [
            PublicationBaselineEntry(
                artifact_path=self._relative(path),
                artifact_hash=hash_file(path),
            )
            for path in self._published_artifacts()
            if not self.receipt_path(self._relative(path)).exists()
        ]
        baseline = PublicationBaseline(created_at=utc_now().isoformat(), artifacts=entries)
        RunStore._atomic_text(self.baseline_path, baseline.model_dump_json(indent=2))
        return {
            "status": "ok",
            "baseline_path": self._relative(self.baseline_path),
            "artifact_count": len(entries),
        }

    def receipt_path(self, artifact_path: str) -> Path:
        """Return the deterministic sidecar path for a publication.

        Args:
            artifact_path (str): Workspace-relative published artifact path.

        Returns:
            Path: Workspace-local receipt sidecar path.

        Raises:
            PublicationProvenanceError: If the artifact path leaves the workspace.
        """
        relative = Path(artifact_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise PublicationProvenanceError("Publication artifact path must stay in workspace")
        return self.receipts_root / relative.parent / f"{relative.name}.receipt.json"

    def ensure_receipt_available(self, target: Path) -> None:
        """Validate receipt-path availability before publication writes.

        Args:
            target (Path): Proposed workspace publication target.

        Returns:
            None: Availability is validated without mutation.

        Raises:
            PublicationProvenanceError: If tracked evidence would be overwritten.
        """
        receipt_path = self.receipt_path(self._relative(target))
        if receipt_path.exists():
            raise PublicationProvenanceError(f"Refusing to overwrite {receipt_path}")

    def _perspective_receipts(self, order: Any, strict: bool) -> list[PerspectiveReceipt]:
        """Return immutable evidence for every selected perspective.

        Resolve the exact versions and hash both the complete entries component and
        every approved entry used by the run.

        Args:
            order (Any): Work order containing pinned perspective selections.
            strict (bool): Require the selected context to remain active when true.

        Returns:
            list[PerspectiveReceipt]: Ordered pinned perspective evidence.

        Raises:
            PublicationProvenanceError: If a selected approved entry is unavailable.
        """
        receipts = []
        requested_ids = (
            order.author_contribution.reusable_perspective_entry_ids
            if order.author_contribution
            else []
        )
        for selection in order.perspective_selections:
            resolved = PerspectiveRegistry(self.root, order.voice_id).resolve(
                selection.context_id,
                selection.version,
                allow_inactive=not strict,
            )
            entries_path = self.root / resolved["path"] / "entries.json"
            entries = json.loads(entries_path.read_text(encoding="utf-8"))
            approved = {
                entry["id"]: entry
                for entry in entries
                if entry.get("status") == PerspectiveEntryStatus.APPROVED.value
            }
            selected_ids = requested_ids or list(resolved["active_entry_ids"])
            missing = sorted(set(selected_ids) - set(approved))
            if missing:
                raise PublicationProvenanceError(
                    "Unavailable approved perspective entries: {}".format(", ".join(missing))
                )
            receipts.append(
                PerspectiveReceipt(
                    context_id=selection.context_id,
                    version=resolved["version"],
                    status_at_publication=resolved["status"],
                    manifest_hash=resolved["manifest_hash"],
                    entries_hash=hash_file(entries_path),
                    selected_entry_hashes={
                        entry_id: hash_json(approved[entry_id]) for entry_id in selected_ids
                    },
                )
            )
        return receipts

    def _verify_receipt(
        self, receipt_path: Path, expected_artifact: str
    ) -> list[PublicationFinding]:
        """Return deterministic failures for one receipt and artifact pair.

        Validate the schema before comparing the published bytes, recorded lifecycle
        status, author provenance, voice, and perspectives.

        Args:
            receipt_path (Path): Tracked receipt file to validate.
            expected_artifact (str): Artifact path implied by the receipt sidecar.

        Returns:
            list[PublicationFinding]: Stable deterministic validation failures.
        """
        try:
            receipt = PublicationReceipt.model_validate_json(
                receipt_path.read_text(encoding="utf-8")
            )
        except Exception as exc:
            return [self._finding("invalid_receipt", expected_artifact, str(exc))]
        failures: list[PublicationFinding] = []
        if receipt.artifact_path != expected_artifact:
            failures.append(
                self._finding(
                    "artifact_path_mismatch",
                    expected_artifact,
                    f"Receipt names {receipt.artifact_path}",
                )
            )
        artifact = self._within_root(receipt.artifact_path)
        if not artifact.is_file():
            failures.append(
                self._finding("missing_artifact", receipt.artifact_path, "Missing file")
            )
        elif hash_file(artifact) != receipt.artifact_hash:
            failures.append(
                self._finding("artifact_hash_mismatch", receipt.artifact_path, "Content changed")
            )
        failures.extend(
            PublicationFinding.model_validate(item) for item in self.packages.verify(receipt)
        )
        if receipt.final_status != RunStatus.PUBLISHED.value:
            failures.append(
                self._finding(
                    "invalid_originating_status",
                    receipt.artifact_path,
                    f"Recorded status is {receipt.final_status}",
                )
            )
        evaluation = receipt.perspective_evaluation
        if not evaluation.passed or evaluation.errors:
            failures.append(
                self._finding(
                    "failed_perspective_evaluation",
                    receipt.artifact_path,
                    "; ".join(evaluation.errors) or "Evaluation did not pass",
                )
            )
        if (
            evaluation.position_marker_count
            and receipt.author_contribution_provenance == "none"
            and not receipt.perspectives
        ):
            failures.append(
                self._finding(
                    "missing_authorial_provenance",
                    receipt.artifact_path,
                    "Authorial position has neither direct nor selected provenance",
                )
            )
        failures.extend(self._verify_voice(receipt))
        failures.extend(self._verify_perspectives(receipt))
        failures.extend(
            self._finding(code, receipt.artifact_path, detail)
            for code, detail in verify_production_governance(self.root, receipt)
        )
        failures.extend(self._verify_semantic(receipt))
        return failures

    def _verify_semantic(self, receipt: PublicationReceipt) -> list[PublicationFinding]:
        """Return failures for an unresolved or inconsistent semantic review.

        Args:
            receipt (PublicationReceipt): Receipt containing semantic review evidence.

        Returns:
            list[PublicationFinding]: Semantic review consistency failures.
        """
        review = receipt.semantic_review
        if review.status == "review_required":
            return [
                self._finding(
                    "unresolved_semantic_review",
                    receipt.artifact_path,
                    "Review-required findings have no author decision",
                )
            ]
        if review.status == "passed" and review.review_required_codes:
            return [
                self._finding(
                    "inconsistent_semantic_review",
                    receipt.artifact_path,
                    "Passed review contains review-required findings",
                )
            ]
        if review.status == "author_approved" and not review.decision_artifact_hash:
            return [
                self._finding(
                    "missing_semantic_review_decision",
                    receipt.artifact_path,
                    "Author-approved review has no decision artifact hash",
                )
            ]
        if review.status not in {
            "not_applicable",
            "disabled",
            "passed",
            "author_approved",
        }:
            return [
                self._finding(
                    "invalid_semantic_review_status",
                    receipt.artifact_path,
                    f"Unsupported semantic review status: {review.status}",
                )
            ]
        return []

    def _verify_voice(self, receipt: PublicationReceipt) -> list[PublicationFinding]:
        """Return failures for the pinned voice evidence.

        Args:
            receipt (PublicationReceipt): Receipt containing the pinned voice.

        Returns:
            list[PublicationFinding]: Voice availability or hash failures.
        """
        try:
            voice = VoiceRegistry(self.root).resolve(
                receipt.voice_id, receipt.voice_version, allow_inactive=True
            )
        except Exception as exc:
            return [self._finding("unavailable_voice", receipt.artifact_path, str(exc))]
        if (
            receipt.voice_manifest_hash
            and voice.get("manifest_hash") != receipt.voice_manifest_hash
        ):
            return [
                self._finding(
                    "voice_hash_mismatch", receipt.artifact_path, "Pinned voice manifest changed"
                )
            ]
        return []

    def _verify_perspectives(self, receipt: PublicationReceipt) -> list[PublicationFinding]:
        """Return failures for pinned perspective versions and entries.

        Args:
            receipt (PublicationReceipt): Receipt containing selected perspectives.

        Returns:
            list[PublicationFinding]: Perspective availability or hash failures.

        Raises:
            PublicationProvenanceError: If immutable perspective evidence differs.
        """
        failures = []
        for expected in receipt.perspectives:
            try:
                actual = PerspectiveRegistry(self.root, receipt.voice_id).resolve(
                    expected.context_id,
                    expected.version,
                    allow_inactive=True,
                )
                entries_path = self.root / actual["path"] / "entries.json"
                entries = json.loads(entries_path.read_text(encoding="utf-8"))
                approved = {
                    item["id"]: item
                    for item in entries
                    if item.get("status") == PerspectiveEntryStatus.APPROVED.value
                }
                if actual["manifest_hash"] != expected.manifest_hash:
                    raise PublicationProvenanceError("Pinned perspective manifest changed")
                if hash_file(entries_path) != expected.entries_hash:
                    raise PublicationProvenanceError("Pinned perspective entries changed")
                for entry_id, entry_hash in expected.selected_entry_hashes.items():
                    if entry_id not in approved or hash_json(approved[entry_id]) != entry_hash:
                        raise PublicationProvenanceError(
                            f"Pinned perspective entry is unavailable or changed: {entry_id}"
                        )
            except Exception as exc:
                failures.append(
                    self._finding("invalid_perspective", receipt.artifact_path, str(exc))
                )
        return failures

    def _published_artifacts(self) -> list[Path]:
        """Return files from every configured pack publication destination.

        Returns:
            list[Path]: Published files in stable path order.
        """
        destinations = {
            (self.root / pack.destination).resolve() for pack in PackRegistry(self.root).list()
        }
        return sorted(
            path
            for destination in destinations
            if destination.exists()
            for path in destination.rglob("*")
            if path.is_file() and path.name != ".gitkeep"
        )

    def _receipt_files(self) -> Iterable[Path]:
        """Return tracked publication receipt files in stable order.

        Returns:
            Iterable[Path]: Existing receipt sidecars, excluding the baseline.
        """
        if not self.receipts_root.exists():
            return []
        return sorted(path for path in self.receipts_root.rglob("*.receipt.json") if path.is_file())

    def _load_baseline(self) -> Dict[str, str]:
        """Return legacy baseline artifact hashes keyed by path.

        Returns:
            Dict[str, str]: Workspace-relative paths mapped to approved legacy hashes.
        """
        if not self.baseline_path.exists():
            return {}
        baseline = PublicationBaseline.model_validate_json(
            self.baseline_path.read_text(encoding="utf-8")
        )
        return {item.artifact_path: item.artifact_hash for item in baseline.artifacts}

    @staticmethod
    def _receipt_required(
        policy: PublicationPolicy,
        artifact: Path,
        relative: str,
        baseline: Dict[str, str],
    ) -> bool:
        """Return whether policy requires a receipt for this artifact.

        Args:
            policy (PublicationPolicy): Active enforcement level.
            artifact (Path): Existing publication being assessed.
            relative (str): Workspace-relative artifact path.
            baseline (Dict[str, str]): Approved legacy path and hash mapping.

        Returns:
            bool: Whether a missing receipt is an active finding.
        """
        if policy == PublicationPolicy.REQUIRED:
            return True
        if policy == PublicationPolicy.REQUIRED_FOR_NEW:
            return baseline.get(relative) != hash_file(artifact)
        return policy == PublicationPolicy.ADVISORY

    def _within_root(self, relative: str) -> Path:
        """Return a workspace-local path or fail closed.

        Args:
            relative (str): Candidate path relative to the workspace.

        Returns:
            Path: Resolved path inside the workspace.

        Raises:
            PublicationProvenanceError: If the resolved path leaves the workspace.
        """
        path = (self.root / relative).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise PublicationProvenanceError("Publication path leaves workspace") from exc
        return path

    def _relative(self, path: Path) -> str:
        """Return a workspace-relative path or fail closed.

        Args:
            path (Path): Candidate filesystem path.

        Returns:
            str: Stable workspace-relative path.

        Raises:
            PublicationProvenanceError: If the path leaves the workspace.
        """
        try:
            return str(path.resolve().relative_to(self.root))
        except ValueError as exc:
            raise PublicationProvenanceError("Publication path leaves workspace") from exc

    @staticmethod
    def _finding(code: str, artifact_path: Optional[str], detail: str) -> PublicationFinding:
        """Return one normalized deterministic finding.

        Args:
            code (str): Stable machine-readable finding identifier.
            artifact_path (Optional[str]): Related publication path when available.
            detail (str): Human-readable failure detail.

        Returns:
            PublicationFinding: Normalized deterministic failure.
        """
        return PublicationFinding(code=code, artifact_path=artifact_path, detail=detail)

    @staticmethod
    def _report(
        policy: PublicationPolicy,
        findings: list[PublicationFinding],
        artifacts: int,
        receipts: int,
        status: str,
    ) -> Dict[str, Any]:
        """Return a stable JSON-serializable verification report.

        Args:
            policy (PublicationPolicy): Active enforcement level.
            findings (list[PublicationFinding]): Ordered verification findings.
            artifacts (int): Number of published artifacts inspected.
            receipts (int): Number of matching receipts inspected.
            status (str): Overall disabled, advisory, failed, or successful state.

        Returns:
            Dict[str, Any]: Stable command report mapping.
        """
        return {
            "schema_version": "1.0",
            "status": status,
            "policy": policy.value,
            "artifact_count": artifacts,
            "receipt_count": receipts,
            "findings": [item.model_dump(mode="json") for item in findings],
        }
