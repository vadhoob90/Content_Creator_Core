"""Provide orchestrator capabilities."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from .capabilities import DefaultRunCapabilities as DefaultRunCapabilities
from .capabilities import RunCapabilities as RunCapabilities
from .context import resolved_context
from .diagnostics import DiagnosticDecisionRequired
from .domain import (
    ResearchBrief,
    ResearchDepth,
    RunEvent,
    RunState,
    RunStatus,
    WorkOrder,
)
from .orchestration_support import OrchestrationError as OrchestrationError
from .orchestration_support import OrchestrationRuntime
from .perspective_extraction import extract_perspectives
from .perspectives import PerspectiveCatalogueStore, PerspectiveRegistry, PerspectiveResolver
from .providers import ProviderRegistry
from .publication_assessment import build_publication_assessment
from .routing import build_route
from .stages import CallableDraftReviewStage as CallableDraftReviewStage
from .stages import CallableResearchStage as CallableResearchStage
from .stages import LifecycleStages as LifecycleStages
from .storage import RunStore, StorageError, slugify
from .versioned_artifacts import hash_file
from .voices import VoiceRegistry
from .work_order_resolution import resolve_workspace_defaults

logger = logging.getLogger(__name__)


class Orchestrator:
    """Coordinate the content creation lifecycle."""

    def __init__(
        self,
        root: Path,
        registry: Optional[ProviderRegistry] = None,
        visual_adapters: Any = None,
        max_revisions: int = 3,
        capabilities: Optional[RunCapabilities] = None,
        stages: Optional[LifecycleStages] = None,
    ):
        """Initialize orchestration through a composed runtime service.

        Keep lifecycle coordination in this class while the runtime owns construction
        and focused drafting, revision, diagnostic, and research operations.

        Args:
            root (Path): The workspace root directory.
            registry (Optional[ProviderRegistry]): Provider registry used for model
                execution. Defaults to ``None``.
            visual_adapters (Any): Optional visual adapter registry. Defaults to ``None``.
            max_revisions (int): Maximum automated revision attempts. Defaults to ``3``.
            capabilities (Optional[RunCapabilities]): Optional capability implementation.
                Defaults to ``None``.
            stages (Optional[LifecycleStages]): Optional lifecycle stage implementations.
                Defaults to ``None``.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        self._runtime = OrchestrationRuntime(
            root,
            registry=registry,
            visual_adapters=visual_adapters,
            max_revisions=max_revisions,
            capabilities=capabilities,
            stages=stages,
        )
        self.root = self._runtime.root
        self.configuration = self._runtime.configuration
        self.registry = self._runtime.registry
        self.prompts = self._runtime.prompts
        self.diagnostics = self._runtime.diagnostics
        self.runner = self._runtime.runner
        self.intake = self._runtime.intake
        self.store = self._runtime.store
        self.packs = self._runtime.packs
        self.capabilities = self._runtime.capabilities
        self.visuals = self._runtime.visuals
        self.max_revisions = self._runtime.max_revisions
        self.stages = self._runtime.stages
        self.learning = self._runtime.learning
        self.publications = self._runtime.publications
        self.semantic_review = self._runtime.semantic_review
        self.publication_lifecycle = self._runtime.publication_lifecycle

    def learn(self, run_id: str, feedback: str, idempotency_key: Optional[str] = None) -> RunState:
        """Apply explicit author feedback through the runtime lifecycle.

        Args:
            run_id (str): Reviewed or published run supplying persisted context.
            feedback (str): Explicit author-approved durable feedback.
            idempotency_key (Optional[str]): Stable retry key. Defaults to ``None``.

        Returns:
            RunState: Run state with appended learning audit events.
        """
        return self._runtime.learn(run_id, feedback, idempotency_key)

    def revise(
        self,
        run_id: str,
        feedback: str,
        draft: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> RunState:
        """Apply a reviewed-run revision through the runtime lifecycle.

        Args:
            run_id (str): Reviewed run identifier.
            feedback (str): Run-scoped author feedback.
            draft (Optional[str]): Author-edited Markdown. Defaults to ``None``.
            idempotency_key (Optional[str]): Stable retry key. Defaults to ``None``.

        Returns:
            RunState: Updated state after revision and review.
        """
        return self._runtime.revise(run_id, feedback, draft, idempotency_key)

    def adopt_current_pack(self, run_id: str) -> RunState:
        """Run current-pack adoption through the runtime lifecycle.

        Args:
            run_id (str): Historical run identifier.

        Returns:
            RunState: Updated state after policy migration and revalidation.
        """
        return self._runtime.adopt_current_pack(run_id)

    def diagnostic_preflight(self, run_id: str) -> Dict:
        """Apply diagnostic preflight through the runtime lifecycle.

        Args:
            run_id (str): Persisted run identifier.

        Returns:
            Dict: Structured diagnostic preflight result.
        """
        return self._runtime.diagnostic_preflight(run_id)

    def link_diagnostic_issue(self, run_id: str, issue_url: str) -> Dict:
        """Link a prepared diagnostic issue through the runtime lifecycle.

        Args:
            run_id (str): Persisted run identifier.
            issue_url (str): GitHub issue URL created from the support candidate.

        Returns:
            Dict: Structured diagnostic issue-link result.
        """
        return self._runtime.link_diagnostic_issue(run_id, issue_url)

    def plan_request(self, request: str, provider: Optional[str] = None) -> WorkOrder:
        """Plan a work order from a natural-language content request.

        Args:
            request (str): The validated request that initiates the operation.
            provider (Optional[str]): The provider implementation used for generation.
                Defaults to ``None``.

        Returns:
            WorkOrder: The planned work order for request.
        """
        order = self.intake.plan(request, provider=provider)
        return resolve_workspace_defaults(
            order,
            self.configuration.coordinator_policy,
            self.packs,
        )

    def start(
        self,
        order: WorkOrder,
        idempotency_key: Optional[str] = None,
    ) -> RunState:
        """Start an idempotent content run from a validated work order.

        Args:
            order (WorkOrder): The work order that defines the requested content run.
            idempotency_key (Optional[str]): The stable retry key for an equivalent
                submission. Defaults to ``None``.

        Returns:
            RunState: The resulting run state for start.
        """
        if order.parent_run_id:
            parent = self.store.load(order.parent_run_id)
            order.content_session_id = parent.work_order.content_session_id
        self.diagnostics.begin_invocation(order.content_session_id)
        submitted_order = order.model_copy(deep=True)
        try:
            return self._start(order, idempotency_key, submitted_order)
        except Exception as exc:
            if self.diagnostics.run_id is None:
                diagnostic = self.diagnostics.record_invocation_failure(exc)
                if diagnostic is not None:
                    try:
                        setattr(  # noqa: B010
                            exc, "diagnostic_path", str(diagnostic.relative_to(self.root))
                        )
                    except (AttributeError, ValueError) as metadata_error:
                        logger.warning(
                            "Unable to attach the diagnostic path to %s (%s)",
                            exc.__class__.__name__,
                            metadata_error.__class__.__name__,
                        )
            raise

    def _start(
        self,
        order: WorkOrder,
        idempotency_key: Optional[str] = None,
        submitted_order: Optional[WorkOrder] = None,
    ) -> RunState:
        """Execute the validated startup sequence for a content run.

        Args:
            order (WorkOrder): The work order that defines the requested content run.
            idempotency_key (Optional[str]): The stable retry key for an equivalent
                submission. Defaults to ``None``.
            submitted_order (Optional[WorkOrder]): The submitted order value passed to
                start. Defaults to ``None``.

        Returns:
            RunState: The resulting run state for start.
        """
        pack = self._validated_pack(order)
        supplied_brief = self._runtime._preflight_supplied_research(order)
        fingerprint = self._runtime._submission_fingerprint(
            submitted_order or order, supplied_brief
        )
        existing = self._existing_submission(idempotency_key, fingerprint)
        if existing:
            return existing
        context = self._resolve_start_context(order)
        state, created = self._create_run(
            order, context["route_plan"], idempotency_key, fingerprint
        )
        if not created:
            return state
        self._write_start_artifacts(state, pack, context)
        return self._execute_start(state, supplied_brief)

    def _validated_pack(self, order: WorkOrder) -> Any:
        """Resolve and validate the content pack selected by a work order.

        Args:
            order (WorkOrder): The work order that defines the requested content run.

        Returns:
            Any: The resulting value for validated pack.

        Raises:
            OrchestrationError: If the orchestration operation cannot complete.
        """
        pack = self.packs.resolve(order.content_pack, order.pack_options)
        order.pack_options = {**pack.defaults, "destination": pack.destination}
        if pack.format != order.format:
            raise OrchestrationError(
                f"Pack {pack.id} expects format {pack.format}, received {order.format}"
            )
        if order.research_depth.value not in pack.allowed_research:
            raise OrchestrationError(
                f"Pack {pack.id} does not allow {order.research_depth.value} research"
            )
        return pack

    def _existing_submission(
        self, idempotency_key: Optional[str], fingerprint: str
    ) -> Optional[RunState]:
        """Return the existing submission.

        Args:
            idempotency_key (Optional[str]): The stable retry key for an equivalent
                submission.
            fingerprint (str): The deterministic fingerprint identifying the input set.

        Returns:
            Optional[RunState]: The resulting existing submission when available; otherwise
                ``None``.
        """
        if idempotency_key is None:
            return None
        existing = self.store.load_by_idempotency_key(idempotency_key, fingerprint)
        if existing:
            self.diagnostics.bind_run(existing.id, existing.work_order.content_session_id)
        return existing

    def _resolve_start_context(self, order: WorkOrder) -> Dict[str, Any]:
        """Resolve the start context.

        Args:
            order (WorkOrder): The work order that defines the requested content run.

        Returns:
            Dict[str, Any]: The structured resolved data for start context.

        Raises:
            OrchestrationError: If the orchestration operation cannot complete.
        """
        order.resolved_voice = False
        voice = VoiceRegistry(self.root).resolve(order.voice_id, order.voice_version)
        order.voice_version = voice["version"]
        order.resolved_voice = True
        policy = dict(self.configuration.perspective_policy)
        if not voice.get("perspectives_allowed", True):
            policy["mode"] = "disabled"
            policy["force_disabled_reason"] = "starter-voice-without-author-evidence"
        resolution = PerspectiveResolver(self.root, self.runner).resolve(order, policy)
        if resolution.needs_clarification:
            raise OrchestrationError(
                resolution.clarification_question or "Perspective selection requires clarification"
            )
        order.perspective_mode = resolution.mode
        order.perspective_selections = resolution.selected
        perspectives = [
            self._resolved_perspective(order, selection) for selection in resolution.selected
        ]
        order.resolved_perspective = bool(resolution.selected)
        if resolution.selected:
            order.perspective_context = resolution.selected[0].context_id
            order.perspective_version = resolution.selected[0].version
        else:
            order.perspective_context = None
            order.perspective_version = None
        return {
            "route_plan": build_route(order),
            "voice": voice,
            "policy": policy,
            "resolution": resolution,
            "perspectives": perspectives,
        }

    def _resolved_perspective(self, order: WorkOrder, selection: Any) -> Dict[str, Any]:
        """Return the resolved perspective.

        Args:
            order (WorkOrder): The work order that defines the requested content run.
            selection (Any): The selection value passed to resolved perspective.

        Returns:
            Dict[str, Any]: The structured resulting data for resolved perspective.

        Raises:
            OrchestrationError: If the orchestration operation cannot complete.
        """
        record = PerspectiveRegistry(self.root, order.voice_id).resolve(
            selection.context_id, selection.version
        )
        requested = getattr(order.author_contribution, "reusable_perspective_entry_ids", [])
        unknown = sorted(set(requested) - set(record["active_entry_ids"]))
        if unknown:
            raise OrchestrationError(
                f"Unavailable perspective entries in {selection.context_id}: {', '.join(unknown)}"
            )
        record["selected_entry_ids"] = requested or record["active_entry_ids"]
        selection.version = record["version"]
        record["selection_reason"] = selection.reason
        record["selection_confidence"] = selection.confidence
        return record

    def _create_run(
        self,
        order: WorkOrder,
        route_plan: Any,
        idempotency_key: Optional[str],
        fingerprint: str,
    ) -> tuple[RunState, bool]:
        """Create the run.

        Args:
            order (WorkOrder): The work order that defines the requested content run.
            route_plan (Any): The route plan value passed to create run.
            idempotency_key (Optional[str]): The stable retry key for an equivalent
                submission.
            fingerprint (str): The deterministic fingerprint identifying the input set.

        Returns:
            tuple[RunState, bool]: The created run values in their documented order.
        """
        state = RunState(work_order=order, route_plan=route_plan)
        state.events.append(RunEvent(name="planned", detail=route_plan.route))
        if idempotency_key is None:
            self.store.create(state)
            created = True
        else:
            state.events.append(RunEvent(name="submission_accepted"))
            state, created = self.store.create_idempotent(state, idempotency_key, fingerprint)
        self.diagnostics.bind_run(state.id, state.work_order.content_session_id)
        self.runner.bind_context_run(state.id)
        return state, created

    def _write_start_artifacts(self, state: RunState, pack: Any, context: Dict[str, Any]) -> None:
        """Write the start artifacts.

        Args:
            state (RunState): The persisted lifecycle state to inspect or update.
            pack (Any): The resolved content-pack contract.
            context (Dict[str, Any]): The operation context and its resolved dependencies.

        Returns:
            None: The callable updates write start artifacts state and returns no value.
        """
        order = state.work_order
        perspectives = context["perspectives"]
        self.store.write_artifact(state.id, "work-order.json", order)
        self.store.write_artifact(state.id, "route-plan.json", state.route_plan)
        self.store.write_artifact(
            state.id,
            "resolved-context.json",
            resolved_context(self.root, order, pack, context["voice"], perspectives),
        )
        self.store.write_artifact(
            state.id,
            "perspective-resolution.json",
            self._perspective_resolution_artifact(order, context),
        )
        self.store.write_artifact(
            state.id,
            "claim-provenance.json",
            {
                "author_contribution": (
                    order.author_contribution.model_dump(mode="json")
                    if order.author_contribution
                    else None
                ),
                "perspective": perspectives[0] if perspectives else None,
                "perspectives": perspectives,
                "research_record": (
                    "not_required" if order.research_depth == ResearchDepth.NONE else "pending"
                ),
                "model_proposed_framing_is_author_position": False,
            },
        )

    def _perspective_resolution_artifact(
        self, order: WorkOrder, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Return the perspective resolution artifact.

        Args:
            order (WorkOrder): The work order that defines the requested content run.
            context (Dict[str, Any]): The operation context and its resolved dependencies.

        Returns:
            Dict[str, Any]: The structured resulting data for perspective resolution
                artifact.
        """
        catalogue = PerspectiveCatalogueStore(self.root, order.voice_id).path
        return {
            **context["resolution"].model_dump(mode="json"),
            "selected": [
                {**selection.model_dump(mode="json"), "version": resolved["version"]}
                for selection, resolved in zip(
                    order.perspective_selections, context["perspectives"], strict=True
                )
            ],
            "catalogue": str(catalogue.relative_to(self.root)) if catalogue.exists() else None,
            "catalogue_hash": hash_file(catalogue) if catalogue.exists() else None,
            "policy": context["policy"],
        }

    def _execute_start(self, state: RunState, supplied_brief: Optional[ResearchBrief]) -> RunState:
        """Execute the start.

        Args:
            state (RunState): The persisted lifecycle state to inspect or update.
            supplied_brief (Optional[ResearchBrief]): The supplied brief value passed to
                execute start.

        Returns:
            RunState: The resulting run state for execute start.
        """
        try:
            brief = self.stages.research.execute(state, supplied_brief)
            if brief:
                self._record_research(state, brief)
            if state.route_plan.requires_research_checkpoint:
                state.status = RunStatus.AWAITING_RESEARCH_APPROVAL
                state.events.append(RunEvent(name="research_checkpoint"))
                self._runtime._persist_model_history(state.id)
                self.store.save_state(state)
                return state
            return self.stages.draft_review.execute(state, brief)
        except Exception as exc:
            self._runtime._fail(state, exc)
            raise

    def _record_research(self, state: RunState, brief: ResearchBrief) -> None:
        """Record the research.

        Args:
            state (RunState): The persisted lifecycle state to inspect or update.
            brief (ResearchBrief): The research or content brief that defines the requested
                work.

        Returns:
            None: The callable updates record research state and returns no value.
        """
        self.store.write_artifact(state.id, "research.json", brief)
        provenance = json.loads(self.store.read_artifact(state.id, "claim-provenance.json"))
        provenance["research_record"] = {
            "status": "completed",
            "evidence_claim_count": len(brief.evidence),
            "tensions": brief.tensions,
            "gaps": brief.gaps,
        }
        self.store.write_artifact(state.id, "claim-provenance.json", provenance)

    def resume_research(self, run_id: str, approved: bool, notes: Optional[str] = None) -> RunState:
        """Return the resume research.

        Args:
            run_id (str): The stable identifier for the content run.
            approved (bool): Whether approved behavior is enabled.
            notes (Optional[str]): The notes text processed when resume research. Defaults
                to ``None``.

        Returns:
            RunState: The resulting run state for resume research.

        Raises:
            OrchestrationError: If the orchestration operation cannot complete.
        """
        state = self.store.load(run_id)
        self.diagnostics.begin_invocation(state.work_order.content_session_id)
        self.diagnostics.bind_run(run_id, state.work_order.content_session_id)
        if state.status != RunStatus.AWAITING_RESEARCH_APPROVAL:
            raise OrchestrationError("Run is not awaiting research approval")
        if not approved:
            state.status = RunStatus.NEEDS_AUTHOR
            state.events.append(RunEvent(name="research_rejected", detail=notes or ""))
            self.store.save_state(state)
            return state
        state.events.append(RunEvent(name="research_approved", detail=notes or ""))
        brief = ResearchBrief.model_validate_json(self.store.read_artifact(run_id, "research.json"))
        try:
            return self.stages.draft_review.execute(state, brief)
        except Exception as exc:
            self._runtime._fail(state, exc)
            raise

    def publish(
        self,
        run_id: str,
        filename: Optional[str] = None,
        feedback: Optional[str] = None,
        diagnostic_decision: Optional[str] = None,
        perspective_review_approved_by: Optional[str] = None,
        perspective_review_notes: Optional[str] = None,
    ) -> RunState:
        """Publish the orchestrator workflow.

        Args:
            run_id (str): The stable identifier for the content run.
            filename (Optional[str]): The filename text processed when publish. Defaults to
                ``None``.
            feedback (Optional[str]): The feedback text processed when publish. Defaults to
                ``None``.
            diagnostic_decision (Optional[str]): The diagnostic decision text processed when
                publish. Defaults to ``None``.
            perspective_review_approved_by (Optional[str]): Reviewer resolving persisted
                semantic findings. Defaults to ``None``.
            perspective_review_notes (Optional[str]): Optional author review notes. Defaults
                to ``None``.

        Returns:
            RunState: The resulting run state for publish.

        """
        state, draft, pack, visual_asset, target = self._prepare_publication(
            run_id, filename, diagnostic_decision
        )
        gate = self.publication_lifecycle.prepare(
            state,
            draft,
            perspective_review_approved_by,
            perspective_review_notes,
        )
        assessment = self._publication_assessment(state, run_id, target, feedback)
        self.store.write_artifact(run_id, "assessment.json", assessment)
        self._extract_learnings(state, draft, assessment, feedback)
        self._extract_perspectives(state, draft, assessment)
        return self._finish_publication(
            state,
            target,
            pack,
            visual_asset,
            draft,
            gate,
        )

    def _prepare_publication(
        self,
        run_id: str,
        filename: Optional[str],
        diagnostic_decision: Optional[str],
    ) -> tuple[RunState, str, Any, Any, Path]:
        """Prepare the publication.

        Args:
            run_id (str): The stable identifier for the content run.
            filename (Optional[str]): The filename text processed when prepare publication.
            diagnostic_decision (Optional[str]): The diagnostic decision text processed when
                prepare publication.

        Returns:
            tuple[RunState, str, Any, Any, Path]: The resolved filesystem path for
                publication.

        Raises:
            DiagnosticDecisionRequired: If the diagnostic decision required operation cannot
            OrchestrationError: If the orchestration operation cannot complete.
            StorageError: If the storage operation cannot complete.
        """
        state = self.store.load(run_id)
        self.diagnostics.begin_invocation(state.work_order.content_session_id)
        self.diagnostics.bind_run(run_id, state.work_order.content_session_id)
        if state.status not in {RunStatus.READY, RunStatus.NEEDS_AUTHOR}:
            raise OrchestrationError("Only a reviewed draft can be published")
        preflight = self.diagnostics.preflight(run_id)
        if preflight["requires_diagnostic_decision"]:
            if diagnostic_decision is None:
                self._runtime._apply_diagnostic_state(state, preflight)
                self.store.save_state(state)
                raise DiagnosticDecisionRequired(preflight)
            preflight = self.diagnostics.decide(run_id, diagnostic_decision)
            self._runtime._apply_diagnostic_state(state, preflight)
        draft = self.store.read_artifact(run_id, "final.md").rstrip() + "\n"
        pack = self.packs.resolve(state.work_order.content_pack, state.work_order.pack_options)
        visual_asset = self.visuals.ensure_publication_ready(run_id, pack.visuals)
        target_dir = self.root / pack.destination
        target_dir.mkdir(parents=True, exist_ok=True)
        requested = filename or f"{slugify(state.work_order.topic)}.md"
        target = target_dir / Path(requested).name
        if target.exists():
            raise StorageError(f"Refusing to overwrite {target}")
        self.publications.ensure_receipt_available(target)
        return state, draft, pack, visual_asset, target

    def _publication_assessment(
        self,
        state: RunState,
        run_id: str,
        target: Path,
        feedback: Optional[str],
    ) -> Dict[str, Any]:
        """Return the publication assessment.

        Args:
            state (RunState): The persisted lifecycle state to inspect or update.
            run_id (str): The stable identifier for the content run.
            target (Path): The filesystem path containing the target.
            feedback (Optional[str]): The feedback text processed when publication
                assessment.

        Returns:
            Dict[str, Any]: The structured resulting data for publication assessment.
        """
        return build_publication_assessment(self.root, state, run_id, target, feedback)

    def _extract_learnings(
        self,
        state: RunState,
        draft: str,
        assessment: Dict[str, Any],
        feedback: Optional[str],
    ) -> None:
        """Extract the learnings.

        Args:
            state (RunState): The persisted lifecycle state to inspect or update.
            draft (str): The draft content to evaluate or transform.
            assessment (Dict[str, Any]): The structured assessment to inspect or persist.
            feedback (Optional[str]): The feedback text processed when extract learnings.

        Returns:
            None: The callable updates learnings state and returns no value.
        """
        try:
            self.learning.extract(
                state,
                draft,
                assessment,
                feedback,
                "learning-extraction.json",
            )
            state.events.append(RunEvent(name="learnings_updated"))
        except Exception as exc:
            state.events.append(RunEvent(name="learning_update_failed", detail=str(exc)))

    def _extract_perspectives(
        self, state: RunState, draft: str, assessment: Dict[str, Any]
    ) -> None:
        """Extract the perspectives.

        Args:
            state (RunState): The persisted lifecycle state to inspect or update.
            draft (str): The draft content to evaluate or transform.
            assessment (Dict[str, Any]): The structured assessment to inspect or persist.

        Returns:
            None: The callable updates perspectives state and returns no value.
        """
        extract_perspectives(
            self.root,
            self.configuration,
            self.store,
            self.runner,
            state,
            draft,
            assessment,
        )

    def _finish_publication(
        self,
        state: RunState,
        target: Path,
        pack: Any,
        visual_asset: Any,
        draft: str,
        gate: Any,
    ) -> RunState:
        """Finish the publication.

        Args:
            state (RunState): The persisted lifecycle state to inspect or update.
            target (Path): The filesystem path containing the target.
            pack (Any): The resolved content-pack contract.
            visual_asset (Any): The visual asset value passed to finish publication.
            draft (str): Exact reviewed draft approved for publication.
            gate (Any): Deterministic and semantic receipt evidence.

        Returns:
            RunState: The resulting run state for finish publication.
        """
        RunStore._atomic_text(target, draft.rstrip())
        state.published_path = str(target.relative_to(self.root))
        if visual_asset is not None:
            visual_target = self.visuals.publish(state.id, pack.visuals)
            state.published_visual_path = (
                str(visual_target.relative_to(self.root)) if visual_target else None
            )
            state.events.append(
                RunEvent(name="visual_published", detail=state.published_visual_path or "")
            )
        state.status = RunStatus.PUBLISHED
        state.events.append(RunEvent(name="published", detail=state.published_path))
        receipt_path = self.publications.issue(
            state,
            target,
            gate.perspective_evaluation,
            gate.evaluation_artifact_hash,
            gate.semantic_review,
        )
        state.events.append(
            RunEvent(
                name="publication_receipt_written", detail=str(receipt_path.relative_to(self.root))
            )
        )
        self._runtime._persist_model_history(state.id)
        self.store.save_state(state)
        post_publish = self.diagnostics.preflight(state.id)
        self._runtime._apply_diagnostic_state(state, post_publish)
        self.store.save_state(state)
        return state
