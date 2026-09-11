"""Apply exact author edits and review changed claims without model-backed rewriting."""

from __future__ import annotations

import difflib
import json
from pathlib import Path

from .domain import RunEvent, RunState, RunStatus
from .draft_integrity import (
    DraftIntegrity,
    assess_edit,
    read_integrity,
    record_claim_binding,
    research_hash,
    text_hash,
    verified_baseline,
)
from .edit_contracts import AuthorEditRequest, ClaimReviewDecision
from .edit_transaction import JOURNAL, edit_transaction, restore_edit
from .edit_validation import validate_author_edit
from .production_store import production_run_store
from .storage import RunStore, StorageError
from .validation import validate_research_brief
from .versioned_artifacts import ActivationLock

_MUTABLE = [
    "state.json",
    "final.md",
    "research.json",
    "draft-integrity.json",
    "claim-provenance.json",
    "production-manifest.json",
    "production-manifest.md",
    "review.md",
]


class AuthorEditWorkflow:
    """Manage adoption, claim decisions, and recovery for reviewed run artifacts."""

    def __init__(self, root: Path):
        """Compose provider-free run persistence for author edits.

        Args:
            root (Path): Workspace root.

        Returns:
            None: The workflow is initialized.
        """
        self.root = root.resolve()
        self.store = production_run_store(self.root)

    def adopt(self, run_id: str, request: AuthorEditRequest) -> RunState:
        """Apply supplied text as a recoverable, idempotent revision.

        Args:
            run_id (str): Reviewed run identifier.
            request (AuthorEditRequest): Exact text, expected baseline, and retry key.

        Returns:
            RunState: Updated run with deterministic validation and claim-review status.

        Raises:
            StorageError: If the run, baseline, concurrent edit, or retry is invalid.
        """
        run = self.store.run_dir(run_id)
        with ActivationLock(run / ".author-edit.lock", "Another edit is in progress", StorageError):
            if (run / JOURNAL).exists():
                raise StorageError("Interrupted author edit; run recover-edit before retrying")
            state = self.store.load(run_id)
            key = RunStore.idempotency_key_hash(request.idempotency_key)
            receipt_name = f"author-edit-{key}.json"
            fingerprint = text_hash(request.model_dump_json())
            receipt = run / receipt_name
            if receipt.exists():
                self._verify_retry(state, receipt, fingerprint)
                return state
            self._reviewable(state)
            baseline = self._baseline(state, request)
            validation = validate_author_edit(self.root, state, request.draft)
            if request.research and validate_research_brief(request.research):
                raise StorageError("Supplied research fails deterministic validation")
            names = _MUTABLE + self._revision_names(state.revision + 1) + [receipt_name]
            names += self._snapshot_names(state.revision)
            self._baseline(state, request)
            with edit_transaction(run, names):
                self._write_adoption(state, request, baseline, validation)
                self.store.write_artifact(
                    run_id,
                    receipt_name,
                    {
                        "fingerprint": fingerprint,
                        "revision": state.revision,
                        "draft_sha256": text_hash(request.draft),
                    },
                )
                self.store.save_state(state)
            return state

    def approve_claims(self, run_id: str, decision: ClaimReviewDecision) -> RunState:
        """Record author review of the unchanged adopted draft and research.

        Args:
            run_id (str): Reviewed run identifier.
            decision (ClaimReviewDecision): Exact evidence hashes and author disposition.

        Returns:
            RunState: Ready state when deterministic checks pass.

        Raises:
            StorageError: If evidence changed or deterministic validation fails.
        """
        run = self.store.run_dir(run_id)
        with ActivationLock(run / ".author-edit.lock", "Another edit is in progress", StorageError):
            state = self.store.load(run_id)
            self._reviewable(state)
            binding = read_integrity(run)
            draft = (run / "final.md").read_bytes().decode("utf-8")
            self._verify_decision(run, binding, draft, decision)
            validation = validate_author_edit(self.root, state, draft)
            if validation["errors"]:
                raise StorageError("Author review cannot override deterministic validation errors")
            assert binding is not None
            if binding.claim_review_status == "approved":
                if (
                    binding.approved_by != decision.approved_by.strip()
                    or binding.notes != decision.notes.strip()
                ):
                    raise StorageError(
                        "This revision already has a different claim-review decision"
                    )
                return state
            review_name = f"claim-review-{state.revision:02d}.json"
            with edit_transaction(run, _MUTABLE + [review_name]):
                binding.claim_review_status = "approved"
                binding.approved_by = decision.approved_by.strip()
                binding.notes = decision.notes.strip()
                self.store.write_artifact(run_id, "draft-integrity.json", binding)
                self.store.write_artifact(run_id, review_name, decision)
                record_claim_binding(run, binding, RunStore._atomic_text)
                state.status = RunStatus.READY
                state.claim_review_required = False
                state.events.append(RunEvent(name="author_edit_claims_approved"))
                self.store.save_state(state)
            return state

    def recover(self, run_id: str) -> RunState:
        """Restore an interrupted adoption to its recorded pre-operation state.

        Args:
            run_id (str): Run with a pending recovery journal.

        Returns:
            RunState: Restored persisted state.
        """
        run = self.store.run_dir(run_id)
        with ActivationLock(run / ".author-edit.lock", "Another edit is in progress", StorageError):
            restore_edit(run)
        return self.store.load(run_id)

    def _baseline(self, state: RunState, request: AuthorEditRequest) -> str:
        """Verify recorded history and distinguish in-place edits from concurrent changes.

        Args:
            state (RunState): Current persisted state.
            request (AuthorEditRequest): Expected predecessor and proposed replacement.

        Returns:
            str: Verified original text.

        Raises:
            StorageError: If hashes disagree or no original can be recovered.
        """
        run = self.store.run_dir(state.id)
        binding = read_integrity(run)
        recorded: str | None
        if binding:
            recorded = binding.draft_sha256
        else:
            manifest = json.loads((run / "production-manifest.json").read_text())
            hashes = [
                a["content_hash"] for a in manifest["artifacts"] if a["kind"] == "final-draft"
            ]
            recorded = hashes[0] if len(hashes) == 1 else None
        if request.expected_sha256 != recorded:
            raise StorageError("Expected baseline hash does not match the recorded revision")
        current = (run / "final.md").read_bytes().decode("utf-8")
        if text_hash(current) not in {recorded, text_hash(request.draft)}:
            raise StorageError("Final draft changed concurrently; inspect it before retrying")
        return verified_baseline(run, request.expected_sha256, request.baseline)

    def _write_adoption(
        self, state: RunState, request: AuthorEditRequest, baseline: str, validation: dict
    ) -> None:
        """Write a new revision inside the operation's recovery boundary.

        Args:
            state (RunState): Mutable state to advance.
            request (AuthorEditRequest): Adopted text and optional new research.
            baseline (str): Verified original text.
            validation (dict): Provider-free validation evidence.

        Returns:
            None: Revision artifacts and in-memory state are updated.
        """
        run = self.store.run_dir(state.id)
        previous = read_integrity(run)
        self._preserve_predecessor(state, baseline)
        state.revision += 1
        revision = state.revision
        if request.research:
            self.store.write_artifact(state.id, "research.json", request.research)
        binding = assess_edit(previous, baseline, request.draft, revision, research_hash(run))
        for name, content in {
            f"revision-baseline-{revision:02d}.md": baseline,
            f"draft-{revision:02d}.md": request.draft,
            f"accepted/r{revision:04d}.md": request.draft,
            "final.md": request.draft,
            f"revision-{revision:02d}.diff": "".join(
                difflib.unified_diff(
                    baseline.splitlines(keepends=True),
                    request.draft.splitlines(keepends=True),
                    fromfile=f"revision-{revision - 1:02d}",
                    tofile=f"revision-{revision:02d}",
                )
            ),
        }.items():
            RunStore.atomic_bytes(run / name, content.encode("utf-8"))
        self.store.write_artifact(state.id, f"validation-{revision:02d}.json", validation)
        self.store.write_artifact(state.id, "draft-integrity.json", binding)
        record_claim_binding(run, binding, RunStore._atomic_text)
        state.claim_review_required = binding.claim_review_status == "required"
        state.status = (
            RunStatus.NEEDS_AUTHOR
            if validation["errors"] or binding.claim_review_status == "required"
            else RunStatus.READY
        )
        state.last_error = None
        state.events.append(RunEvent(name="author_edit_adopted", detail=f"revision={revision}"))

    def _preserve_predecessor(self, state: RunState, baseline: str) -> None:
        """Preserve verified legacy predecessors before their first adoption.

        Args:
            state (RunState): Original run revision.
            baseline (str): Hash-verified predecessor text.

        Returns:
            None: Missing predecessor snapshots are written without replacing history.
        """
        run = self.store.run_dir(state.id)
        sources = {
            f"accepted/r{state.revision:04d}.md": baseline.encode("utf-8"),
            f"accepted/r{state.revision:04d}.manifest.json": (
                run / "production-manifest.json"
            ).read_bytes(),
        }
        research = run / "research.json"
        if research.is_file():
            sources[f"accepted/r{state.revision:04d}.research.json"] = research.read_bytes()
        for name, content in sources.items():
            if not (run / name).exists():
                RunStore.atomic_bytes(run / name, content)

    @staticmethod
    def _snapshot_names(revision: int) -> list[str]:
        """List immutable predecessor snapshots owned by an adoption.

        Args:
            revision (int): Original revision number.

        Returns:
            list[str]: Relative accepted text, manifest, and research paths.
        """
        return [
            f"accepted/r{revision:04d}{suffix}"
            for suffix in (".md", ".manifest.json", ".research.json")
        ]

    @staticmethod
    def _revision_names(revision: int) -> list[str]:
        """List the new revision artifacts covered by compensation.

        Args:
            revision (int): New revision number.

        Returns:
            list[str]: Relative paths owned by adoption and its save callback.
        """
        return [
            f"revision-baseline-{revision:02d}.md",
            f"draft-{revision:02d}.md",
            f"revision-{revision:02d}.diff",
            f"validation-{revision:02d}.json",
            f"accepted/r{revision:04d}.md",
            f"accepted/r{revision:04d}.manifest.json",
        ]

    @staticmethod
    def _reviewable(state: RunState) -> None:
        """Reject operations outside reviewed, unpublished runs.

        Args:
            state (RunState): Run to check.

        Returns:
            None: The run permits author revision work.

        Raises:
            StorageError: If the run has not reached author review or is published.
        """
        if state.status not in {RunStatus.READY, RunStatus.NEEDS_AUTHOR}:
            raise StorageError("Only reviewed unpublished drafts can adopt author edits")

    @staticmethod
    def _verify_retry(state: RunState, receipt: Path, fingerprint: str) -> None:
        """Reject conflicting reuse or replay against a later run revision.

        Args:
            state (RunState): Current persisted state.
            receipt (Path): Completed adoption receipt.
            fingerprint (str): Exact request digest.

        Returns:
            None: The retry refers to the same current completed operation.

        Raises:
            StorageError: If the retry input or current revision differs.
        """
        previous = json.loads(receipt.read_text())
        if previous["fingerprint"] != fingerprint or previous["revision"] != state.revision:
            raise StorageError(
                "Edit idempotency key belongs to different input or an older revision"
            )
        if (
            text_hash((receipt.parent / "final.md").read_bytes().decode("utf-8"))
            != previous["draft_sha256"]
        ):
            raise StorageError("Final draft hash changed since this adoption completed")

    @staticmethod
    def _verify_decision(
        run: Path, binding: DraftIntegrity | None, draft: str, decision: ClaimReviewDecision
    ) -> None:
        """Require exact current evidence and an explicit nonempty author decision.

        Args:
            run (Path): Validated run directory.
            binding (DraftIntegrity | None): Persisted adoption integrity record.
            draft (str): Current final text.
            decision (ClaimReviewDecision): Submitted review decision.

        Returns:
            None: The decision refers to the exact adopted draft and research.

        Raises:
            StorageError: If any evidence hash or author decision is invalid.
        """
        if binding is None or not decision.approved_by.strip() or not decision.notes.strip():
            raise StorageError("Claim review requires a draft binding, reviewer, and notes")
        if binding.change_kind == "generated":
            raise StorageError("The run has no author-edit claim review to approve")
        if (
            binding.draft_sha256 != decision.draft_sha256
            or text_hash(draft) != decision.draft_sha256
        ):
            raise StorageError("Claim review draft hash is stale")
        if (
            binding.research_sha256 != decision.research_sha256
            or research_hash(run) != decision.research_sha256
        ):
            raise StorageError("Claim review research hash is stale")
