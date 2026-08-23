"""Manage traceable post-gate content revisions."""

from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

from .domain import Critique, ResearchBrief, RunEvent, RunState, RunStatus
from .quality import evaluate_quality
from .storage import IdempotencyError, RunStore, StorageError
from .validation import normalize_publishable_markdown
from .voices import VoiceRegistry


class RevisionLifecycle:
    """Coordinate resumable revisions against an existing reviewed run."""

    def __init__(self, workflow: Any):
        """Initialize the revision lifecycle.

        Args:
            workflow (Any): Orchestration host supplying stores, checks, and agents.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        self.workflow = workflow

    def execute(
        self,
        run_id: str,
        feedback: str,
        draft: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> RunState:
        """Apply a reviewed-draft revision and refresh its final-draft metadata.

        Persist the revision request before provider work so an interrupted invocation
        can resume without creating a disconnected run or another revision number.

        Args:
            run_id (str): Reviewed run to revise.
            feedback (str): Run-scoped author feedback guiding the revision.
            draft (Optional[str]): Author-edited Markdown, or ``None`` to invoke the
                configured writer. Defaults to ``None``.
            idempotency_key (Optional[str]): Stable key for retrying this exact revision.
                Defaults to ``None``.

        Returns:
            RunState: The run state after refreshed quality checks.

        """
        state, baseline, feedback = self._load_inputs(run_id, feedback)
        fingerprint = self._fingerprint(run_id, feedback, draft)
        request_name, request = self._prepare_request(state, feedback, fingerprint, idempotency_key)
        if request["status"] == "complete":
            return state
        revision = int(request["revision"])
        self.workflow.diagnostics.begin_invocation(state.work_order.content_session_id)
        self.workflow.diagnostics.bind_run(run_id, state.work_order.content_session_id)
        try:
            return self._execute_revision(
                state, baseline, feedback, draft, revision, request_name, request
            )
        except Exception as exc:
            self._record_failure(state, request_name, request, revision, exc)
            raise

    def adopt_current_pack(self, run_id: str) -> RunState:
        """Run current-pack adoption and revalidate the affected final draft.

        Args:
            run_id (str): Historical run whose conflicting legacy policy was approved.

        Returns:
            RunState: Revised run after current-policy validation and criticism.

        Raises:
            RuntimeError: If the run has no conflicting legacy pack policy.
        """
        state = self.workflow.store.load(run_id)
        VoiceRegistry(self.workflow.root).resolve(
            state.work_order.voice_id, state.work_order.voice_version
        )
        migrations = self.workflow.packs.override_compatibility(
            state.work_order.content_pack, state.work_order.pack_options
        )
        conflicts = [item for item in migrations if item["outcome"] == "conflict"]
        if not conflicts:
            raise RuntimeError("Run has no conflicting legacy pack policy to resolve")
        prior_options = dict(state.work_order.pack_options)
        for item in conflicts:
            state.work_order.pack_options.pop(item["setting"], None)
        self.workflow.store.write_artifact(run_id, "work-order.json", state.work_order)
        self.workflow.store.write_artifact(
            run_id,
            "pack-migration-decision.json",
            {
                "decision": "adopt_current_pack_and_revalidate",
                "previous_pack_options": prior_options,
                "effective_pack_options": state.work_order.pack_options,
                "differences": conflicts,
            },
        )
        state.events.append(
            RunEvent(name="current_pack_policy_adopted", detail=f"settings={len(conflicts)}")
        )
        self.workflow.store.save_state(state)
        draft = self.workflow.store.read_artifact(run_id, "final.md")
        key = "pack-migration-{}-{}".format(run_id, self._hash(json.dumps(conflicts))[:16])
        return self.execute(
            run_id,
            "Adopt the current content-pack policy and revalidate the existing final draft.",
            draft,
            key,
        )

    def _load_inputs(self, run_id: str, feedback: str) -> tuple[RunState, str, str]:
        """Load and validate the reviewed state, baseline, and feedback.

        Args:
            run_id (str): Run identifier to load.
            feedback (str): Unnormalised author feedback.

        Returns:
            tuple[RunState, str, str]: State, final-draft baseline, and normalised feedback.

        Raises:
            RuntimeError: If the run cannot enter post-gate revision.
        """
        state = self.workflow.store.load(run_id)
        allowed = {RunStatus.READY, RunStatus.NEEDS_AUTHOR, RunStatus.FAILED}
        if state.status not in allowed:
            raise RuntimeError("Only a reviewed or interrupted draft can be revised")
        feedback = feedback.strip()
        if not feedback:
            raise RuntimeError("Revision feedback must not be empty")
        try:
            baseline = self.workflow.store.read_artifact(run_id, "final.md").rstrip() + "\n"
        except StorageError as exc:
            raise RuntimeError("Run has no reviewed final draft to revise") from exc
        return state, baseline, feedback

    def _prepare_request(
        self,
        state: RunState,
        feedback: str,
        fingerprint: str,
        key: Optional[str],
    ) -> tuple[str, Dict[str, Any]]:
        """Create or recover the durable revision request.

        Args:
            state (RunState): Persisted run being revised.
            feedback (str): Normalised author feedback.
            fingerprint (str): Hash binding the complete revision input.
            key (Optional[str]): Optional retry key.

        Returns:
            tuple[str, Dict[str, Any]]: Artifact name and persisted request data.

        Raises:
            IdempotencyError: If a retry key identifies different input.
        """
        name = self._request_name(key, state.revision + 1)
        existing = self._load_request(self.workflow.store.run_dir(state.id) / name)
        if existing:
            if existing.get("fingerprint") != fingerprint:
                raise IdempotencyError(
                    "Revision idempotency key is already associated with different input"
                )
            return name, existing
        request = {
            "revision": state.revision + 1,
            "parent_revision": state.revision,
            "feedback": feedback,
            "fingerprint": fingerprint,
            "status": "started",
            "feedback_scope": "run",
        }
        self.workflow.store.write_artifact(state.id, name, request)
        return name, request

    def _execute_revision(
        self,
        state: RunState,
        baseline: str,
        feedback: str,
        supplied_draft: Optional[str],
        revision: int,
        request_name: str,
        request: Dict[str, Any],
    ) -> RunState:
        """Run drafting, checks, history updates, and final state transition.

        Args:
            state (RunState): Persisted run being revised.
            baseline (str): Reviewed draft before the revision.
            feedback (str): Run-scoped feedback guiding the revision.
            supplied_draft (Optional[str]): Author edit, or ``None`` for writer output.
            revision (int): Revision number reserved by the durable request.
            request_name (str): Durable request artifact name.
            request (Dict[str, Any]): Mutable durable request data.

        Returns:
            RunState: Updated state after the quality decision.
        """
        pack = self.workflow.packs.resolve(
            state.work_order.content_pack, state.work_order.pack_options
        )
        critique = self._latest_critique(state.id)
        brief = self._research_brief(state.id)
        state.revision = revision
        state.last_error = None
        self.workflow.store.write_artifact(
            state.id, f"revision-baseline-{revision:02d}.md", baseline
        )
        context = self._revision_context(state, baseline, feedback, request)
        if supplied_draft is None:
            revised, _, decision = self.workflow._draft_revision(
                state, brief, pack, context, critique, revision
            )
        else:
            revised, decision = self._review_author_draft(
                state, brief, pack, critique, supplied_draft, revision
            )
        self._write_success_artifacts(
            state, baseline, revised, revision, request_name, request, decision
        )
        return state

    def _review_author_draft(
        self,
        state: RunState,
        brief: Optional[ResearchBrief],
        pack: Any,
        previous_critique: Optional[Critique],
        draft: str,
        revision: int,
    ) -> tuple[str, Any]:
        """Run the normal validation, critic, and quality gate on an author edit.

        Args:
            state (RunState): Persisted run being revised.
            brief (Optional[ResearchBrief]): Persisted research when available.
            pack (Any): Resolved content pack.
            previous_critique (Optional[Critique]): Prior critique for issue continuity.
            draft (str): Author-edited Markdown.
            revision (int): Reserved revision number.

        Returns:
            tuple[str, Any]: Normalised draft and refreshed quality decision.
        """
        revised = normalize_publishable_markdown(draft).rstrip() + "\n"
        self.workflow.store.write_artifact(state.id, f"draft-{revision:02d}.md", revised)
        errors, score = self.workflow._validate_revision(state, pack, revised, revision)
        critique = self.workflow._critique_revision(
            state, brief, revised, errors, score, previous_critique
        )
        decision = evaluate_quality(critique, self.workflow.configuration.rubric("core"), errors)
        self.workflow.store.write_artifact(state.id, f"critique-{revision:02d}.json", critique)
        self.workflow.store.write_artifact(state.id, f"quality-{revision:02d}.json", decision)
        state.events.append(
            RunEvent(
                name="revision_reviewed",
                detail=(
                    f"revision={revision}, score={decision.weighted_score:.2f}, "
                    f"passed={decision.passed}"
                ),
            )
        )
        return revised, decision

    def _write_success_artifacts(
        self,
        state: RunState,
        baseline: str,
        revised: str,
        revision: int,
        request_name: str,
        request: Dict[str, Any],
        decision: Any,
    ) -> None:
        """Persist the diff, provenance, request result, and final state atomically.

        Args:
            state (RunState): Persisted run being revised.
            baseline (str): Draft before the revision.
            revised (str): Draft after the revision.
            revision (int): Completed revision number.
            request_name (str): Durable request artifact name.
            request (Dict[str, Any]): Mutable durable request data.
            decision (Any): Refreshed quality decision.

        Returns:
            None: Artifacts and state are updated in place.
        """
        diff = self._diff(baseline, revised, int(request["parent_revision"]), revision)
        self.workflow.store.write_artifact(state.id, f"revision-{revision:02d}.diff", diff)
        self.workflow.store.write_artifact(state.id, "final.md", revised)
        state.final_draft_path = f"runs/{state.id}/final.md"
        state.status = RunStatus.READY if decision.passed else RunStatus.NEEDS_AUTHOR
        state.events.append(
            RunEvent(
                name="post_gate_revision_completed",
                detail=f"revision={revision}, passed={decision.passed}",
            )
        )
        self._refresh_provenance(state, revision, baseline, revised, str(request["feedback"]))
        request.update(status="complete", quality=decision.model_dump(mode="json"))
        request.pop("error", None)
        self.workflow.store.write_artifact(state.id, request_name, request)
        self.workflow._persist_model_history(state.id)
        self.workflow.store.save_state(state)

    def _record_failure(
        self,
        state: RunState,
        request_name: str,
        request: Dict[str, Any],
        revision: int,
        error: Exception,
    ) -> None:
        """Persist an interrupted revision so the same request can resume.

        Args:
            state (RunState): Run whose revision failed.
            request_name (str): Durable request artifact name.
            request (Dict[str, Any]): Mutable durable request data.
            revision (int): Interrupted revision number.
            error (Exception): Failure raised during revision.

        Returns:
            None: Failure details and state are persisted in place.
        """
        request.update(status="failed", error=str(error))
        self.workflow.store.write_artifact(state.id, request_name, request)
        state.status = RunStatus.FAILED
        state.last_error = str(error)
        state.events.append(
            RunEvent(name="revision_failed", detail=f"revision={revision}: {error}")
        )
        self.workflow.store.save_state(state)

    def _refresh_provenance(
        self,
        state: RunState,
        revision: int,
        baseline: str,
        revised: str,
        feedback: str,
    ) -> None:
        """Append final-draft lineage to claim provenance.

        Args:
            state (RunState): Run receiving revision lineage.
            revision (int): Completed revision number.
            baseline (str): Draft before revision.
            revised (str): Draft after revision.
            feedback (str): Run-scoped feedback supporting the change.

        Returns:
            None: Provenance is persisted in place.
        """
        path = self.workflow.store.run_dir(state.id) / "claim-provenance.json"
        provenance = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        provenance.setdefault("revision_history", []).append(
            {
                "revision": revision,
                "parent_revision": revision - 1,
                "baseline_sha256": self._hash(baseline),
                "final_sha256": self._hash(revised),
                "feedback": feedback,
                "feedback_scope": "run",
            }
        )
        provenance["final_draft_revision"] = revision
        self.workflow.store.write_artifact(state.id, "claim-provenance.json", provenance)

    def _research_brief(self, run_id: str) -> Optional[ResearchBrief]:
        """Load persisted research when the run has it.

        Args:
            run_id (str): Run identifier whose research is requested.

        Returns:
            Optional[ResearchBrief]: Parsed brief, or ``None`` for no-research routes.
        """
        path = self.workflow.store.run_dir(run_id) / "research.json"
        return ResearchBrief.model_validate_json(path.read_text()) if path.exists() else None

    def _latest_critique(self, run_id: str) -> Optional[Critique]:
        """Load the latest critique for prior-issue continuity.

        Args:
            run_id (str): Run identifier whose critique is requested.

        Returns:
            Optional[Critique]: Latest critique, or ``None`` when unavailable.
        """
        paths = sorted(self.workflow.store.run_dir(run_id).glob("critique-*.json"))
        return Critique.model_validate_json(paths[-1].read_text()) if paths else None

    @staticmethod
    def _revision_context(
        state: RunState, baseline: str, feedback: str, request: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build writer context for a post-gate revision.

        Args:
            state (RunState): Run being revised.
            baseline (str): Reviewed draft before revision.
            feedback (str): Run-scoped author feedback.
            request (Dict[str, Any]): Durable revision request.

        Returns:
            Dict[str, Any]: Structured writer revision context.
        """
        return {
            "parent_run_id": state.id,
            "parent_revision": request["parent_revision"],
            "parent_draft": baseline,
            "author_feedback": feedback,
            "feedback_scope": "run",
            "revision_instruction": (
                "Apply the explicit author feedback while preserving unaffected approved text."
            ),
        }

    @staticmethod
    def _fingerprint(run_id: str, feedback: str, draft: Optional[str]) -> str:
        """Hash the complete revision input for retry safety.

        Args:
            run_id (str): Run identifier being revised.
            feedback (str): Normalised author feedback.
            draft (Optional[str]): Optional author-edited draft.

        Returns:
            str: Hexadecimal SHA-256 fingerprint.
        """
        payload = json.dumps(
            {"run_id": run_id, "feedback": feedback, "draft": draft},
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _request_name(key: Optional[str], revision: int) -> str:
        """Build a stable, non-sensitive request artifact name.

        Args:
            key (Optional[str]): Optional caller retry key.
            revision (int): Next revision number for unkeyed requests.

        Returns:
            str: Safe request artifact filename.
        """
        if key is None:
            return f"revision-request-{revision:02d}.json"
        return "revision-request-{}.json".format(RunStore.idempotency_key_hash(key)[:16])

    @staticmethod
    def _load_request(path: Path) -> Optional[Dict[str, Any]]:
        """Load an existing durable request when present.

        Args:
            path (Path): Expected request artifact path.

        Returns:
            Optional[Dict[str, Any]]: Parsed request, or ``None`` when absent.
        """
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    @staticmethod
    def _diff(baseline: str, revised: str, parent: int, revision: int) -> str:
        """Build the unified revision diff.

        Args:
            baseline (str): Draft before revision.
            revised (str): Draft after revision.
            parent (int): Parent revision number.
            revision (int): Completed revision number.

        Returns:
            str: Unified diff text.
        """
        return "".join(
            difflib.unified_diff(
                baseline.splitlines(keepends=True),
                revised.splitlines(keepends=True),
                fromfile=f"revision-{parent:02d}",
                tofile=f"revision-{revision:02d}",
            )
        )

    @staticmethod
    def _hash(value: str) -> str:
        """Hash persisted draft content.

        Args:
            value (str): Draft text to hash.

        Returns:
            str: Hexadecimal SHA-256 digest.
        """
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
