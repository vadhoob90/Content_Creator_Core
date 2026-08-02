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
from .stages import CallableDraftReviewStage as CallableDraftReviewStage
from .stages import CallableResearchStage as CallableResearchStage
from .stages import LifecycleStages as LifecycleStages
from .storage import RunStore, StorageError, slugify
from .voices import VoiceRegistry, hash_file


class Orchestrator(OrchestrationSupport):
    def plan_request(self, request: str, provider: Optional[str] = None) -> WorkOrder:
        return self.intake.plan(request, provider=provider)

    def start(
        self,
        order: WorkOrder,
        idempotency_key: Optional[str] = None,
    ) -> RunState:
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
        pack = self.packs.resolve(order.content_pack, order.pack_options)
        order.pack_options = {**pack.defaults, "destination": pack.destination}
        if pack.format != order.format:
            raise OrchestrationError(
                "Pack {} expects format {}, received {}".format(pack.id, pack.format, order.format)
            )
        if order.research_depth.value not in pack.allowed_research:
            raise OrchestrationError(
                "Pack {} does not allow {} research".format(pack.id, order.research_depth.value)
            )
        route_plan = build_route(order)
        supplied_brief = self._preflight_supplied_research(order)
        submission_fingerprint = self._submission_fingerprint(
            submitted_order or order, supplied_brief
        )
        if idempotency_key is not None:
            existing = self.store.load_by_idempotency_key(idempotency_key, submission_fingerprint)
            if existing:
                self.diagnostics.bind_run(
                    existing.id,
                    existing.work_order.content_session_id,
                )
                return existing
        order.resolved_voice = False
        resolved_voice = VoiceRegistry(self.root).resolve(order.voice_id, order.voice_version)
        order.voice_version = resolved_voice["version"]
        order.resolved_voice = True
        order.resolved_perspective = False
        effective_perspective_policy = dict(self.configuration.perspective_policy)
        if not resolved_voice.get("perspectives_allowed", True):
            effective_perspective_policy["mode"] = "disabled"
            effective_perspective_policy["force_disabled_reason"] = (
                "starter-voice-without-author-evidence"
            )
        perspective_resolution = PerspectiveResolver(self.root, self.runner).resolve(
            order, effective_perspective_policy
        )
        if perspective_resolution.needs_clarification:
            raise OrchestrationError(
                perspective_resolution.clarification_question
                or "Perspective selection requires clarification"
            )
        order.perspective_mode = perspective_resolution.mode
        order.perspective_selections = perspective_resolution.selected
        resolved_perspectives = []
        for selection in order.perspective_selections:
            perspective_record = PerspectiveRegistry(self.root, order.voice_id).resolve(
                selection.context_id, selection.version
            )
            requested_entries = (
                order.author_contribution.reusable_perspective_entry_ids
                if order.author_contribution
                else []
            )
            unknown_entries = sorted(
                set(requested_entries) - set(perspective_record["active_entry_ids"])
            )
            if unknown_entries:
                raise OrchestrationError(
                    "Unavailable perspective entries in {}: {}".format(
                        selection.context_id,
                        ", ".join(unknown_entries),
                    )
                )
            perspective_record["selected_entry_ids"] = (
                requested_entries if requested_entries else perspective_record["active_entry_ids"]
            )
            selection.version = perspective_record["version"]
            perspective_record["selection_reason"] = selection.reason
            perspective_record["selection_confidence"] = selection.confidence
            resolved_perspectives.append(perspective_record)
        if order.perspective_selections:
            first = order.perspective_selections[0]
            order.perspective_context = first.context_id
            order.perspective_version = first.version
            order.resolved_perspective = True
        else:
            order.perspective_context = None
            order.perspective_version = None
        resolved_perspective: Optional[Dict[str, Any]] = (
            resolved_perspectives[0] if resolved_perspectives else None
        )
        state = RunState(work_order=order, route_plan=route_plan)
        state.events.append(RunEvent(name="planned", detail=state.route_plan.route))
        if idempotency_key is not None:
            state.events.append(RunEvent(name="submission_accepted"))
            state, created = self.store.create_idempotent(
                state,
                idempotency_key,
                submission_fingerprint,
            )
            if not created:
                self.diagnostics.bind_run(
                    state.id,
                    state.work_order.content_session_id,
                )
                return state
        else:
            self.store.create(state)
        self.diagnostics.bind_run(state.id, order.content_session_id)
        self.store.write_artifact(state.id, "work-order.json", order)
        self.store.write_artifact(state.id, "route-plan.json", state.route_plan)
        self.store.write_artifact(
            state.id,
            "resolved-context.json",
            resolved_context(
                self.root,
                order,
                pack,
                resolved_voice,
                resolved_perspectives,
            ),
        )
        self.store.write_artifact(
            state.id,
            "perspective-resolution.json",
            {
                **perspective_resolution.model_dump(mode="json"),
                "selected": [
                    {
                        **item.model_dump(mode="json"),
                        "version": resolved["version"],
                    }
                    for item, resolved in zip(
                        order.perspective_selections,
                        resolved_perspectives,
                        strict=True,
                    )
                ],
                "catalogue": (
                    str(
                        PerspectiveCatalogueStore(self.root, order.voice_id).path.relative_to(
                            self.root
                        )
                    )
                    if PerspectiveCatalogueStore(self.root, order.voice_id).path.exists()
                    else None
                ),
                "catalogue_hash": (
                    hash_file(PerspectiveCatalogueStore(self.root, order.voice_id).path)
                    if PerspectiveCatalogueStore(self.root, order.voice_id).path.exists()
                    else None
                ),
                "policy": effective_perspective_policy,
            },
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
                "perspective": resolved_perspective,
                "perspectives": resolved_perspectives,
                "research_record": (
                    "not_required" if order.research_depth == ResearchDepth.NONE else "pending"
                ),
                "model_proposed_framing_is_author_position": False,
            },
        )
        try:
            brief = self.stages.research.execute(state, supplied_brief)
            if brief:
                self.store.write_artifact(state.id, "research.json", brief)
                provenance = json.loads(self.store.read_artifact(state.id, "claim-provenance.json"))
                provenance["research_record"] = {
                    "status": "completed",
                    "evidence_claim_count": len(brief.evidence),
                    "tensions": brief.tensions,
                    "gaps": brief.gaps,
                }
                self.store.write_artifact(state.id, "claim-provenance.json", provenance)
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

    def resume_research(self, run_id: str, approved: bool, notes: Optional[str] = None) -> RunState:
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
        pack = self.packs.resolve(
            state.work_order.content_pack,
            state.work_order.pack_options,
        )
        visual_asset = self.visuals.ensure_publication_ready(run_id, pack.visuals)
        target_dir = self.root / pack.destination
        target_dir.mkdir(parents=True, exist_ok=True)
        requested = filename or "{}.md".format(slugify(state.work_order.topic))
        target = target_dir / Path(requested).name
        if target.exists():
            raise StorageError("Refusing to overwrite {}".format(target))
        RunStore._atomic_text(target, draft.rstrip())

        assessment = {
            "run_id": run_id,
            "published_path": str(target.relative_to(self.root)),
            "voice_id": state.work_order.voice_id,
            "voice_version": state.work_order.voice_version,
            "content_pack": state.work_order.content_pack,
            "perspective_context": state.work_order.perspective_context,
            "perspective_version": state.work_order.perspective_version,
            "perspective_selections": [
                item.model_dump(mode="json") for item in state.work_order.perspective_selections
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
        self.store.write_artifact(run_id, "assessment.json", assessment)

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
                    "critiques": self._available_critiques(run_id),
                },
                order=state.work_order,
                output_model=LearningExtraction,
                provider=state.work_order.provider,
            )
            self.store.write_artifact(run_id, "learning-extraction.json", extraction)
            LearningMemory(self.root, state.work_order.voice_id).apply(
                run_id,
                extraction,
                explicit_feedback=feedback,
                voice_version=state.work_order.voice_version,
                content_pack=state.work_order.content_pack,
            )
            state.events.append(RunEvent(name="learnings_updated"))
        except Exception as exc:
            state.events.append(RunEvent(name="learning_update_failed", detail=str(exc)))

        for selection in state.work_order.perspective_selections:
            try:
                extraction_order = state.work_order.model_copy(deep=True)
                extraction_order.perspective_context = selection.context_id
                extraction_order.perspective_version = selection.version
                extraction_order.perspective_selections = [selection]
                perspective_extraction = self.runner.run(
                    role="perspective-extractor",
                    role_key="perspective-extractor",
                    instruction=(
                        "Propose only reusable author positions evidenced by this "
                        "published run. Preserve qualifications and keep every proposal "
                        "in the explicitly resolved context. Compare direct author input "
                        "and explicit feedback with active entries. When they conflict, "
                        "use qualify, replace, or supersede and name the exact target "
                        "entry id. Never activate a proposal. Conflict policy: {}."
                    ).format(
                        self.configuration.perspective_policy.get(
                            "conflict_policy", "propose-update"
                        )
                    ),
                    payload={
                        "work_order": state.work_order.model_dump(mode="json"),
                        "draft": draft,
                        "assessment": assessment,
                        "research": (
                            json.loads(self.store.read_artifact(run_id, "research.json"))
                            if (self.store.run_dir(run_id) / "research.json").exists()
                            else None
                        ),
                    },
                    order=extraction_order,
                    output_model=PerspectiveExtraction,
                    provider=state.work_order.provider,
                )
                self.store.write_artifact(
                    run_id,
                    (
                        "perspective-extraction.json"
                        if len(state.work_order.perspective_selections) == 1
                        else "perspective-extraction-{}.json".format(selection.context_id)
                    ),
                    perspective_extraction,
                )
                proposal_paths = PerspectiveProposalStore(
                    self.root,
                    state.work_order.voice_id,
                    selection.context_id,
                ).apply(run_id, perspective_extraction)
                state.events.append(
                    RunEvent(
                        name="perspective_candidates_proposed",
                        detail="count={}".format(len(proposal_paths)),
                    )
                )
            except Exception as exc:
                state.events.append(
                    RunEvent(
                        name="perspective_update_failed",
                        detail=str(exc),
                    )
                )

        state.published_path = str(target.relative_to(self.root))
        if visual_asset is not None:
            visual_target = self.visuals.publish(run_id, pack.visuals)
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
        post_publish = self.diagnostics.preflight(run_id)
        self._apply_diagnostic_state(state, post_publish)
        self.store.save_state(state)
        return state
