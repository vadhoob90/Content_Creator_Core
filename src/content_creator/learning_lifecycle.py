"""Manage auditable learning-only updates for persisted content runs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

from .domain import LearningExtraction, RunEvent, RunState, RunStatus
from .learning import LearningMemory
from .runner import AgentRunOptions
from .storage import IdempotencyError, RunStore, StorageError
from .versioned_artifacts import ActivationLock
from .voices import VoiceRegistry


class LearningLifecycle:
    """Coordinate retry-safe voice learning independently of publication."""

    def __init__(self, workflow: Any):
        """Initialize the learning lifecycle with its orchestration host.

        Args:
            workflow (Any): Orchestration host supplying stores, registries, and agents.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        self.workflow = workflow

    def execute(
        self,
        run_id: str,
        feedback: str,
        idempotency_key: Optional[str] = None,
    ) -> RunState:
        """Apply explicit author feedback to the selected voice learning memory.

        Persist a durable request before provider work, reuse any recovered extraction,
        and leave publication destinations untouched. A completed keyed request returns
        the current run state without invoking the provider or applying memory again.

        Args:
            run_id (str): Reviewed or published run supplying persisted context.
            feedback (str): Explicit author-approved durable feedback.
            idempotency_key (Optional[str]): Stable key for retrying this exact update.
                Defaults to ``None``.

        Returns:
            RunState: The unchanged lifecycle state with appended learning audit events.
        """
        state, draft, feedback = self._load_inputs(run_id, feedback)
        fingerprint = self._fingerprint(run_id, feedback)
        lock = self.workflow.store.run_dir(run_id) / ".learning-update.lock"
        with ActivationLock(lock, "Another learning update is already in progress"):
            request_name, request = self._prepare_request(
                state, feedback, fingerprint, idempotency_key
            )
            if request["status"] == "complete":
                return state
            self._begin_attempt(state, request)
            try:
                return self._execute_update(state, draft, feedback, request_name, request)
            except Exception as exc:
                self._record_failure(state, request_name, request, exc)
                raise

    def execute_publication(
        self,
        state: RunState,
        draft: str,
        assessment: Dict[str, Any],
        feedback: Optional[str],
    ) -> None:
        """Persist and attempt the retryable learning coupled to publication.

        Args:
            state (RunState): Reviewed run crossing the publication boundary.
            draft (str): Exact reviewed content used as learning context.
            assessment (Dict[str, Any]): Persisted publication assessment.
            feedback (Optional[str]): Explicit author feedback, or ``None`` for inference.

        Returns:
            None: Request, extraction, events, and pending state are persisted in place.
        """
        request_name = "publication-learning-request.json"
        request = {
            "schema_version": "1.0",
            "status": "started",
            "run_id": state.id,
            "fingerprint": self._publication_fingerprint(state.id, draft, assessment, feedback),
            "assessment_artifact": "assessment.json",
            "extraction_artifact": "learning-extraction.json",
            "feedback": feedback,
            "feedback_scope": "voice",
        }
        self.workflow.store.write_artifact(state.id, request_name, request)
        state.pending_learning_count = 1
        self.workflow.store.save_state(state)
        try:
            self.extract(state, draft, assessment, feedback, "learning-extraction.json")
        except Exception as exc:
            request.update(status="pending", error=str(exc))
            state.events.append(RunEvent(name="learning_update_failed", detail=str(exc)))
        else:
            request.update(status="complete")
            request.pop("error", None)
            state.pending_learning_count = 0
            state.events.append(RunEvent(name="learnings_updated"))
        self.workflow.store.write_artifact(state.id, request_name, request)

    def retry_publication(self, run_id: str) -> RunState:
        """Execute one durable pending publication-learning operation again.

        Reuse a recovered extraction when present so a failure after provider output
        does not invoke the provider or apply the same learning twice.

        Args:
            run_id (str): Published run with a pending durable learning request.

        Returns:
            RunState: Published run with completed or still-pending learning state.

        Raises:
            RuntimeError: If the run has no pending publication-learning request.
        """
        state = self.workflow.store.load(run_id)
        request_name = "publication-learning-request.json"
        request_path = self.workflow.store.run_dir(run_id) / request_name
        request = self._load_request(request_path)
        if not request or request.get("status") != "pending":
            raise RuntimeError("Run has no pending publication learning update")
        assessment = json.loads(
            self.workflow.store.read_artifact(run_id, str(request["assessment_artifact"]))
        )
        draft = self.workflow.store.read_artifact(run_id, "final.md").rstrip() + "\n"
        extraction_name = str(request["extraction_artifact"])
        extraction_path = self.workflow.store.run_dir(run_id) / extraction_name
        state.events.append(RunEvent(name="learning_update_started", detail="publication"))
        self.workflow.store.save_state(state)
        try:
            if extraction_path.exists():
                extraction = LearningExtraction.model_validate_json(
                    extraction_path.read_text(encoding="utf-8")
                )
                self._apply(state, extraction, request.get("feedback"))
            else:
                self.extract(
                    state,
                    draft,
                    assessment,
                    request.get("feedback"),
                    extraction_name,
                )
        except Exception as exc:
            request.update(status="pending", error=str(exc))
            state.events.append(RunEvent(name="learning_update_failed", detail=str(exc)))
            self.workflow.store.write_artifact(run_id, request_name, request)
            self.workflow.store.save_state(state)
            raise
        request.update(status="complete")
        request.pop("error", None)
        state.pending_learning_count = 0
        state.events.append(RunEvent(name="learning_update_completed", detail="publication"))
        self.workflow.store.write_artifact(run_id, request_name, request)
        self.workflow.store.save_state(state)
        return state

    def extract(
        self,
        state: RunState,
        draft: str,
        assessment: Dict[str, Any],
        feedback: Optional[str],
        artifact_name: str,
    ) -> LearningExtraction:
        """Run the shared extractor and apply its result to voice-scoped memory.

        Args:
            state (RunState): Persisted run receiving the learning update.
            draft (str): Reviewed draft used as extraction context.
            assessment (Dict[str, Any]): Author-signal assessment for the extractor.
            feedback (Optional[str]): Explicit feedback, or ``None`` for inference.
            artifact_name (str): Run-relative extraction artifact name.

        Returns:
            LearningExtraction: The validated extractor result applied to memory.
        """
        extraction = self.workflow.runner.run(
            role="learning-extractor",
            role_key="learning-extractor",
            instruction=(
                "Extract only durable, reusable learning. Explicit author feedback may "
                "be active; inferences from draft changes or publication alone must be "
                "provisional."
            ),
            payload={
                "work_order": state.work_order.model_dump(mode="json"),
                "draft": draft,
                "assessment": assessment,
                "critiques": self.workflow._available_critiques(state.id),
            },
            options=AgentRunOptions(
                order=state.work_order,
                output_model=LearningExtraction,
                provider=state.work_order.provider,
            ),
        )
        self.workflow.store.write_artifact(state.id, artifact_name, extraction)
        self._apply(state, extraction, feedback)
        return extraction

    def _load_inputs(self, run_id: str, feedback: str) -> tuple[RunState, str, str]:
        """Load and validate the persisted run, final draft, and feedback.

        Args:
            run_id (str): Run identifier to load.
            feedback (str): Unnormalised explicit feedback.

        Returns:
            tuple[RunState, str, str]: State, reviewed draft, and normalised feedback.

        Raises:
            RuntimeError: If the run cannot accept a learning-only update.
        """
        state = self.workflow.store.load(run_id)
        allowed = {RunStatus.READY, RunStatus.NEEDS_AUTHOR, RunStatus.PUBLISHED}
        if state.status not in allowed:
            raise RuntimeError("Only a reviewed or published run can receive learning feedback")
        feedback = feedback.strip()
        if not feedback:
            raise RuntimeError("Learning feedback must not be empty")
        try:
            draft = self.workflow.store.read_artifact(run_id, "final.md").rstrip() + "\n"
        except StorageError as exc:
            raise RuntimeError("Run has no reviewed final draft for learning extraction") from exc
        return state, draft, feedback

    def _prepare_request(
        self,
        state: RunState,
        feedback: str,
        fingerprint: str,
        key: Optional[str],
    ) -> tuple[str, Dict[str, Any]]:
        """Create or recover the durable learning request.

        Args:
            state (RunState): Persisted run receiving feedback.
            feedback (str): Normalised explicit feedback.
            fingerprint (str): Hash binding the complete learning input.
            key (Optional[str]): Optional retry key.

        Returns:
            tuple[str, Dict[str, Any]]: Artifact name and persisted request data.

        Raises:
            IdempotencyError: If a retry key identifies different feedback.
        """
        name = self._request_name(state.id, key)
        existing = self._load_request(self.workflow.store.run_dir(state.id) / name)
        if existing:
            if existing.get("fingerprint") != fingerprint:
                raise IdempotencyError(
                    "Learning idempotency key is already associated with different feedback"
                )
            return name, existing
        sequence = self._next_sequence(state.id)
        request: Dict[str, Any] = {
            "schema_version": "1.0",
            "sequence": sequence,
            "feedback": feedback,
            "fingerprint": fingerprint,
            "status": "started",
            "feedback_scope": "voice",
        }
        self.workflow.store.write_artifact(state.id, name, request)
        return name, request

    def _begin_attempt(self, state: RunState, request: Dict[str, Any]) -> None:
        """Bind diagnostics and record the learning attempt.

        Args:
            state (RunState): Persisted run receiving feedback.
            request (Dict[str, Any]): Durable request being attempted.

        Returns:
            None: Diagnostics and state events are updated in place.
        """
        self.workflow.diagnostics.begin_invocation(state.work_order.content_session_id)
        self.workflow.diagnostics.bind_run(state.id, state.work_order.content_session_id)
        sequence = int(request["sequence"])
        state.events.append(
            RunEvent(name="learning_update_started", detail=f"update={sequence:02d}")
        )
        self.workflow.store.save_state(state)

    def _execute_update(
        self,
        state: RunState,
        draft: str,
        feedback: str,
        request_name: str,
        request: Dict[str, Any],
    ) -> RunState:
        """Resolve context, extract learning, and persist successful audit state.

        Args:
            state (RunState): Persisted run receiving feedback.
            draft (str): Reviewed draft used as extraction context.
            feedback (str): Explicit author feedback.
            request_name (str): Durable request artifact name.
            request (Dict[str, Any]): Mutable durable request data.

        Returns:
            RunState: Run state with a completed learning event.
        """
        context = self._resolve_context(state)
        sequence = int(request["sequence"])
        assessment_name = f"learning-assessment-{sequence:02d}.json"
        extraction_name = f"learning-extraction-{sequence:02d}.json"
        assessment = self._assessment(state, feedback, context, sequence)
        self.workflow.store.write_artifact(state.id, assessment_name, assessment)
        extraction_path = self.workflow.store.run_dir(state.id) / extraction_name
        if extraction_path.exists():
            extraction = LearningExtraction.model_validate_json(extraction_path.read_text())
            self._apply(state, extraction, feedback)
        else:
            self.extract(state, draft, assessment, feedback, extraction_name)
        request.update(
            status="complete",
            resolved_context=context,
            assessment_artifact=assessment_name,
            extraction_artifact=extraction_name,
        )
        request.pop("error", None)
        self.workflow.store.write_artifact(state.id, request_name, request)
        state.events.append(
            RunEvent(
                name="learning_update_completed",
                detail=f"update={sequence:02d}, extraction={extraction_name}",
            )
        )
        self.workflow._persist_model_history(state.id)
        self.workflow.store.save_state(state)
        return state

    def _resolve_context(self, state: RunState) -> Dict[str, Any]:
        """Resolve and verify the persisted voice version and content pack.

        Args:
            state (RunState): Persisted run whose context must be verified.

        Returns:
            Dict[str, Any]: Verified voice and content-pack provenance.

        Raises:
            RuntimeError: If the persisted voice is not an immutable verified version.
        """
        order = state.work_order
        voice = VoiceRegistry(self.workflow.root).resolve(order.voice_id, order.voice_version)
        if voice.get("lifecycle_authority") != "version_manifest":
            raise RuntimeError(f"Voice {order.voice_id} has no verifiable immutable version")
        pack = self.workflow.packs.resolve(order.content_pack, order.pack_options)
        return {
            "voice_id": voice["id"],
            "voice_version": voice["version"],
            "voice_manifest_hash": voice["manifest_hash"],
            "content_pack": pack.id,
            "content_pack_version": pack.version,
        }

    @staticmethod
    def _assessment(
        state: RunState,
        feedback: str,
        context: Dict[str, Any],
        sequence: int,
    ) -> Dict[str, Any]:
        """Build the explicit-feedback assessment supplied to the extractor.

        Args:
            state (RunState): Persisted run receiving feedback.
            feedback (str): Explicit author feedback.
            context (Dict[str, Any]): Verified voice and pack context.
            sequence (int): Monotonic run-local learning update number.

        Returns:
            Dict[str, Any]: Versioned learning assessment.
        """
        return {
            "schema_version": "1.0",
            "learning_update": sequence,
            "run_id": state.id,
            "run_status": state.status.value,
            "published_path": state.published_path,
            **context,
            "author_signal": "explicit_feedback",
            "feedback": feedback,
        }

    def _apply(
        self,
        state: RunState,
        extraction: LearningExtraction,
        feedback: Optional[str],
    ) -> None:
        """Apply a validated extraction through voice-scoped memory policy.

        Args:
            state (RunState): Persisted run receiving feedback.
            extraction (LearningExtraction): Validated learning candidates.
            feedback (Optional[str]): Explicit feedback, or ``None`` for inference.

        Returns:
            None: Voice learning memory is updated atomically.
        """
        LearningMemory(self.workflow.root, state.work_order.voice_id).apply(
            state.id,
            extraction,
            explicit_feedback=feedback,
            voice_version=state.work_order.voice_version,
            content_pack=state.work_order.content_pack,
        )

    def _record_failure(
        self,
        state: RunState,
        request_name: str,
        request: Dict[str, Any],
        error: Exception,
    ) -> None:
        """Persist an observable failed attempt without changing run status.

        Args:
            state (RunState): Run whose learning update failed.
            request_name (str): Durable request artifact name.
            request (Dict[str, Any]): Mutable durable request data.
            error (Exception): Failure raised during the update.

        Returns:
            None: Failure metadata and state events are persisted in place.
        """
        sequence = int(request["sequence"])
        request.update(status="failed", error=str(error))
        self.workflow.store.write_artifact(state.id, request_name, request)
        state.events.append(
            RunEvent(name="learning_update_failed", detail=f"update={sequence:02d}: {error}")
        )
        self.workflow.store.save_state(state)

    def _request_name(self, run_id: str, key: Optional[str]) -> str:
        """Build a stable, non-sensitive request artifact name.

        Args:
            run_id (str): Run receiving the learning request.
            key (Optional[str]): Optional caller retry key.

        Returns:
            str: Safe request artifact filename.
        """
        if key is None:
            return f"learning-request-{self._next_sequence(run_id):02d}.json"
        return "learning-request-{}.json".format(RunStore.idempotency_key_hash(key)[:16])

    def _next_sequence(self, run_id: str) -> int:
        """Allocate the next run-local learning update number.

        Args:
            run_id (str): Run whose prior request artifacts are inspected.

        Returns:
            int: Next positive update sequence.
        """
        sequences = []
        for path in self.workflow.store.run_dir(run_id).glob("learning-request-*.json"):
            request = self._load_request(path)
            if request and isinstance(request.get("sequence"), int):
                sequences.append(int(request["sequence"]))
        return max(sequences, default=0) + 1

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
    def _fingerprint(run_id: str, feedback: str) -> str:
        """Hash the complete learning-only input for retry safety.

        Args:
            run_id (str): Run receiving the learning request.
            feedback (str): Normalised explicit feedback.

        Returns:
            str: Hexadecimal SHA-256 fingerprint.
        """
        payload = json.dumps(
            {"run_id": run_id, "feedback": feedback},
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _publication_fingerprint(
        run_id: str,
        draft: str,
        assessment: Dict[str, Any],
        feedback: Optional[str],
    ) -> str:
        """Hash the complete automatic publication-learning request.

        Args:
            run_id (str): Run receiving the automatic learning update.
            draft (str): Exact reviewed draft used as evidence.
            assessment (Dict[str, Any]): Publication assessment supplied to extraction.
            feedback (Optional[str]): Explicit author feedback when available.

        Returns:
            str: Stable hexadecimal SHA-256 request fingerprint.
        """
        payload = json.dumps(
            {
                "run_id": run_id,
                "draft": draft,
                "assessment": assessment,
                "feedback": feedback,
            },
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
