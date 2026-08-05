"""Provide orchestrator capabilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .capabilities import DefaultRunCapabilities as DefaultRunCapabilities
from .capabilities import RunCapabilities as RunCapabilities
from .context import resolved_context
from .diagnostics import DiagnosticDecisionRequired
from .domain import (
    LearningExtraction,
    ResearchBrief,
    ResearchDepth,
    RunEvent,
    RunState,
    RunStatus,
    WorkOrder,
)
from .learning import LearningMemory
from .orchestration_support import OrchestrationError as OrchestrationError
from .orchestration_support import OrchestrationSupport
from .perspectives import (
    PerspectiveCatalogueStore,
    PerspectiveExtraction,
    PerspectiveProposalStore,
    PerspectiveRegistry,
    PerspectiveResolver,
)
from .routing import build_route
from .runner import AgentRunOptions
from .stages import CallableDraftReviewStage as CallableDraftReviewStage
from .stages import CallableResearchStage as CallableResearchStage
from .stages import LifecycleStages as LifecycleStages
from .storage import RunStore, StorageError, slugify
from .versioned_artifacts import hash_file
from .voices import VoiceRegistry


class Orchestrator(OrchestrationSupport):
    """Coordinate the content creation lifecycle."""

    def plan_request(self, request: str, provider: Optional[str] = None) -> WorkOrder:
        """Plan request."""
        return self.intake.plan(request, provider=provider)

    def start(
        self,
        order: WorkOrder,
        idempotency_key: Optional[str] = None,
    ) -> RunState:
        """Start orchestrator."""
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
                try:
                    setattr(  # noqa: B010
                        exc, "diagnostic_path", str(diagnostic.relative_to(self.root))
                    )
                except (AttributeError, ValueError):
                    pass
            raise

    def _start(
        self,
        order: WorkOrder,
        idempotency_key: Optional[str] = None,
        submitted_order: Optional[WorkOrder] = None,
    ) -> RunState:
        """Start orchestrator."""
        pack = self._validated_pack(order)
        supplied_brief = self._preflight_supplied_research(order)
        fingerprint = self._submission_fingerprint(submitted_order or order, supplied_brief)
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
        """Return the validated pack."""
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
        """Return the existing submission."""
        if idempotency_key is None:
            return None
        existing = self.store.load_by_idempotency_key(idempotency_key, fingerprint)
        if existing:
            self.diagnostics.bind_run(existing.id, existing.work_order.content_session_id)
        return existing

    def _resolve_start_context(self, order: WorkOrder) -> Dict[str, Any]:
        """Resolve start context."""
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
        """Return the resolved perspective."""
        record = PerspectiveRegistry(self.root, order.voice_id).resolve(
            selection.context_id, selection.version
        )
        requested = (
            order.author_contribution.reusable_perspective_entry_ids
            if order.author_contribution
            else []
        )
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
        """Create run."""
        state = RunState(work_order=order, route_plan=route_plan)
        state.events.append(RunEvent(name="planned", detail=route_plan.route))
        if idempotency_key is None:
            self.store.create(state)
            created = True
        else:
            state.events.append(RunEvent(name="submission_accepted"))
            state, created = self.store.create_idempotent(state, idempotency_key, fingerprint)
        self.diagnostics.bind_run(state.id, state.work_order.content_session_id)
        return state, created

    def _write_start_artifacts(self, state: RunState, pack: Any, context: Dict[str, Any]) -> None:
        """Write start artifacts."""
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
        """Return the perspective resolution artifact."""
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
        """Execute start."""
        try:
            brief = self.stages.research.execute(state, supplied_brief)
            if brief:
                self._record_research(state, brief)
            if state.route_plan.requires_research_checkpoint:
                state.status = RunStatus.AWAITING_RESEARCH_APPROVAL
                state.events.append(RunEvent(name="research_checkpoint"))
                self._persist_model_history(state.id)
                self.store.save_state(state)
                return state
            return self.stages.draft_review.execute(state, brief)
        except Exception as exc:
            self._fail(state, exc)
            raise

    def _record_research(self, state: RunState, brief: ResearchBrief) -> None:
        """Record research."""
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
        """Return the resume research."""
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
            self._fail(state, exc)
            raise

    def publish(
        self,
        run_id: str,
        filename: Optional[str] = None,
        feedback: Optional[str] = None,
        diagnostic_decision: Optional[str] = None,
    ) -> RunState:
        """Publish orchestrator."""
        state, draft, pack, visual_asset, target = self._prepare_publication(
            run_id, filename, diagnostic_decision
        )
        assessment = self._publication_assessment(state, run_id, target, feedback)
        self.store.write_artifact(run_id, "assessment.json", assessment)
        self._extract_learnings(state, draft, assessment, feedback)
        self._extract_perspectives(state, draft, assessment)
        return self._finish_publication(state, target, pack, visual_asset)

    def _prepare_publication(
        self,
        run_id: str,
        filename: Optional[str],
        diagnostic_decision: Optional[str],
    ) -> tuple[RunState, str, Any, Any, Path]:
        """Prepare publication."""
        state = self.store.load(run_id)
        self.diagnostics.begin_invocation(state.work_order.content_session_id)
        self.diagnostics.bind_run(run_id, state.work_order.content_session_id)
        if state.status not in {RunStatus.READY, RunStatus.NEEDS_AUTHOR}:
            raise OrchestrationError("Only a reviewed draft can be published")
        preflight = self.diagnostics.preflight(run_id)
        if preflight["requires_diagnostic_decision"]:
            if diagnostic_decision is None:
                self._apply_diagnostic_state(state, preflight)
                self.store.save_state(state)
                raise DiagnosticDecisionRequired(preflight)
            preflight = self.diagnostics.decide(run_id, diagnostic_decision)
            self._apply_diagnostic_state(state, preflight)
        draft = self.store.read_artifact(run_id, "final.md").rstrip() + "\n"
        pack = self.packs.resolve(state.work_order.content_pack, state.work_order.pack_options)
        visual_asset = self.visuals.ensure_publication_ready(run_id, pack.visuals)
        target_dir = self.root / pack.destination
        target_dir.mkdir(parents=True, exist_ok=True)
        requested = filename or f"{slugify(state.work_order.topic)}.md"
        target = target_dir / Path(requested).name
        if target.exists():
            raise StorageError(f"Refusing to overwrite {target}")
        RunStore._atomic_text(target, draft.rstrip())
        return state, draft, pack, visual_asset, target

    def _publication_assessment(
        self,
        state: RunState,
        run_id: str,
        target: Path,
        feedback: Optional[str],
    ) -> Dict[str, Any]:
        """Return the publication assessment."""
        order = state.work_order
        return {
            "run_id": run_id,
            "published_path": str(target.relative_to(self.root)),
            "voice_id": order.voice_id,
            "voice_version": order.voice_version,
            "content_pack": order.content_pack,
            "perspective_context": order.perspective_context,
            "perspective_version": order.perspective_version,
            "perspective_selections": [
                selection.model_dump(mode="json") for selection in order.perspective_selections
            ],
            "author_signal": "explicit_feedback" if feedback else "publication_approval",
            "feedback": feedback,
            "questions": {
                "plausibly_approvable": True,
                "passages_not_in_voice": None,
                "exaggerated_habit": None,
                "invented_experience": None,
                "channel_appropriate": True,
                "perspective_authentic": None,
                "unsupported_author_position": None,
                "perspective_qualifications_preserved": None,
                "research_conflicts_surfaced": None,
                "claim_provenance_clear": None,
            },
        }

    def _extract_learnings(
        self,
        state: RunState,
        draft: str,
        assessment: Dict[str, Any],
        feedback: Optional[str],
    ) -> None:
        """Extract learnings."""
        try:
            extraction = self.runner.run(
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
                    "critiques": self._available_critiques(state.id),
                },
                options=AgentRunOptions(
                    order=state.work_order,
                    output_model=LearningExtraction,
                    provider=state.work_order.provider,
                ),
            )
            self.store.write_artifact(state.id, "learning-extraction.json", extraction)
            LearningMemory(self.root, state.work_order.voice_id).apply(
                state.id,
                extraction,
                explicit_feedback=feedback,
                voice_version=state.work_order.voice_version,
                content_pack=state.work_order.content_pack,
            )
            state.events.append(RunEvent(name="learnings_updated"))
        except Exception as exc:
            state.events.append(RunEvent(name="learning_update_failed", detail=str(exc)))

    def _extract_perspectives(
        self, state: RunState, draft: str, assessment: Dict[str, Any]
    ) -> None:
        """Extract perspectives."""
        for selection in state.work_order.perspective_selections:
            try:
                self._extract_perspective(state, selection, draft, assessment)
            except Exception as exc:
                state.events.append(RunEvent(name="perspective_update_failed", detail=str(exc)))

    def _extract_perspective(
        self,
        state: RunState,
        selection: Any,
        draft: str,
        assessment: Dict[str, Any],
    ) -> None:
        """Extract perspective."""
        order = state.work_order
        extraction_order = order.model_copy(deep=True)
        extraction_order.perspective_context = selection.context_id
        extraction_order.perspective_version = selection.version
        extraction_order.perspective_selections = [selection]
        instruction = (
            "Propose only reusable author positions evidenced by this published run. "
            "Preserve qualifications and keep every proposal in the explicitly resolved "
            "context. Compare direct author input and explicit feedback with active entries. "
            "When they conflict, use qualify, replace, or supersede and name the exact target "
            "entry id. Never activate a proposal. Conflict policy: {}."
        ).format(self.configuration.perspective_policy.get("conflict_policy", "propose-update"))
        research_path = self.store.run_dir(state.id) / "research.json"
        extraction = self.runner.run(
            role="perspective-extractor",
            role_key="perspective-extractor",
            instruction=instruction,
            payload={
                "work_order": order.model_dump(mode="json"),
                "draft": draft,
                "assessment": assessment,
                "research": (
                    json.loads(self.store.read_artifact(state.id, "research.json"))
                    if research_path.exists()
                    else None
                ),
            },
            options=AgentRunOptions(
                order=extraction_order,
                output_model=PerspectiveExtraction,
                provider=order.provider,
            ),
        )
        filename = (
            "perspective-extraction.json"
            if len(order.perspective_selections) == 1
            else f"perspective-extraction-{selection.context_id}.json"
        )
        self.store.write_artifact(state.id, filename, extraction)
        paths = PerspectiveProposalStore(self.root, order.voice_id, selection.context_id).apply(
            state.id, extraction
        )
        state.events.append(
            RunEvent(name="perspective_candidates_proposed", detail=f"count={len(paths)}")
        )

    def _finish_publication(
        self, state: RunState, target: Path, pack: Any, visual_asset: Any
    ) -> RunState:
        """Finish publication."""
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
        self._persist_model_history(state.id)
        self.store.save_state(state)
        post_publish = self.diagnostics.preflight(state.id)
        self._apply_diagnostic_state(state, post_publish)
        self.store.save_state(state)
        return state
