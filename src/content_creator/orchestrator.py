from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from .configuration import Configuration
from .context import resolved_context
from .domain import (
    Critique,
    LearningExtraction,
    ResearchBrief,
    ResearchDepth,
    ResearchSource,
    RunEvent,
    RunState,
    RunStatus,
    WorkOrder,
)
from .intake import BriefingAgent
from .learning import LearningMemory
from .packs import PackRegistry
from .perspective_evaluation import evaluate_perspective_output
from .perspectives import (
    PerspectiveCatalogueStore,
    PerspectiveExtraction,
    PerspectiveProposalStore,
    PerspectiveRegistry,
    PerspectiveResolver,
)
from .prompting import PromptAssembler
from .providers import ProviderRegistry
from .quality import evaluate_quality
from .routing import build_route
from .runner import AgentRunner
from .storage import RunStore, StorageError, slugify
from .validation import validate_draft, validate_research_brief
from .voice_evaluation import evaluate_voice_output
from .voices import VoiceRegistry, hash_file


class OrchestrationError(RuntimeError):
    pass


class Orchestrator:
    def __init__(
        self,
        root: Path,
        registry: Optional[ProviderRegistry] = None,
        max_revisions: int = 3,
    ):
        self.root = root.resolve()
        self.configuration = Configuration(self.root)
        self.registry = registry or ProviderRegistry(root=self.root)
        self.prompts = PromptAssembler(self.root)
        self.runner = AgentRunner(self.configuration, self.registry, self.prompts)
        self.intake = BriefingAgent(self.runner)
        self.store = RunStore(self.root)
        self.packs = PackRegistry(self.root)
        self.max_revisions = max_revisions

    def plan_request(self, request: str, provider: Optional[str] = None) -> WorkOrder:
        return self.intake.plan(request, provider=provider)

    def start(self, order: WorkOrder) -> RunState:
        pack = self.packs.resolve(order.content_pack, order.pack_options)
        order.pack_options = {**pack.defaults, "destination": pack.destination}
        order.resolved_voice = False
        resolved_voice = VoiceRegistry(self.root).resolve(
            order.voice_id, order.voice_version
        )
        order.voice_version = resolved_voice["version"]
        order.resolved_voice = True
        order.resolved_perspective = False
        effective_perspective_policy = dict(
            self.configuration.perspective_policy
        )
        if not resolved_voice.get("perspectives_allowed", True):
            effective_perspective_policy["mode"] = "disabled"
            effective_perspective_policy["force_disabled_reason"] = (
                "starter-voice-without-author-evidence"
            )
        perspective_resolution = PerspectiveResolver(
            self.root, self.runner
        ).resolve(order, effective_perspective_policy)
        if perspective_resolution.needs_clarification:
            raise OrchestrationError(
                perspective_resolution.clarification_question
                or "Perspective selection requires clarification"
            )
        order.perspective_mode = perspective_resolution.mode
        order.perspective_selections = perspective_resolution.selected
        resolved_perspectives = []
        for selection in order.perspective_selections:
            resolved_perspective = PerspectiveRegistry(
                self.root, order.voice_id
            ).resolve(selection.context_id, selection.version)
            requested_entries = (
                order.author_contribution.reusable_perspective_entry_ids
                if order.author_contribution
                else []
            )
            unknown_entries = sorted(
                set(requested_entries)
                - set(resolved_perspective["active_entry_ids"])
            )
            if unknown_entries:
                raise OrchestrationError(
                    "Unavailable perspective entries in {}: {}".format(
                        selection.context_id,
                        ", ".join(unknown_entries),
                    )
                )
            resolved_perspective["selected_entry_ids"] = (
                requested_entries
                if requested_entries
                else resolved_perspective["active_entry_ids"]
            )
            selection.version = resolved_perspective["version"]
            resolved_perspective["selection_reason"] = selection.reason
            resolved_perspective["selection_confidence"] = selection.confidence
            resolved_perspectives.append(resolved_perspective)
        if order.perspective_selections:
            first = order.perspective_selections[0]
            order.perspective_context = first.context_id
            order.perspective_version = first.version
            order.resolved_perspective = True
        else:
            order.perspective_context = None
            order.perspective_version = None
        resolved_perspective = (
            resolved_perspectives[0] if resolved_perspectives else None
        )
        if pack.format != order.format:
            raise OrchestrationError(
                "Pack {} expects format {}, received {}".format(
                    pack.id, pack.format, order.format
                )
            )
        if order.research_depth.value not in pack.allowed_research:
            raise OrchestrationError(
                "Pack {} does not allow {} research".format(
                    pack.id, order.research_depth.value
                )
            )
        state = RunState(work_order=order, route_plan=build_route(order))
        state.events.append(RunEvent(name="planned", detail=state.route_plan.route))
        self.store.create(state)
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
                        order.perspective_selections, resolved_perspectives
                    )
                ],
                "catalogue": (
                    str(
                        PerspectiveCatalogueStore(
                            self.root, order.voice_id
                        ).path.relative_to(self.root)
                    )
                    if PerspectiveCatalogueStore(
                        self.root, order.voice_id
                    ).path.exists()
                    else None
                ),
                "catalogue_hash": (
                    hash_file(
                        PerspectiveCatalogueStore(
                            self.root, order.voice_id
                        ).path
                    )
                    if PerspectiveCatalogueStore(
                        self.root, order.voice_id
                    ).path.exists()
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
                    "not_required"
                    if order.research_depth == ResearchDepth.NONE
                    else "pending"
                ),
                "model_proposed_framing_is_author_position": False,
            },
        )
        try:
            brief = self._research(state)
            if brief:
                self.store.write_artifact(state.id, "research.json", brief)
                provenance = json.loads(
                    self.store.read_artifact(state.id, "claim-provenance.json")
                )
                provenance["research_record"] = {
                    "status": "completed",
                    "evidence_claim_count": len(brief.evidence),
                    "tensions": brief.tensions,
                    "gaps": brief.gaps,
                }
                self.store.write_artifact(
                    state.id, "claim-provenance.json", provenance
                )
            if state.route_plan.requires_research_checkpoint:
                state.status = RunStatus.AWAITING_RESEARCH_APPROVAL
                state.events.append(RunEvent(name="research_checkpoint"))
                self._persist_model_history(state.id)
                self.store.save_state(state)
                return state
            return self._draft_and_review(state, brief)
        except Exception as exc:
            self._fail(state, exc)
            raise

    def resume_research(
        self, run_id: str, approved: bool, notes: Optional[str] = None
    ) -> RunState:
        state = self.store.load(run_id)
        if state.status != RunStatus.AWAITING_RESEARCH_APPROVAL:
            raise OrchestrationError("Run is not awaiting research approval")
        if not approved:
            state.status = RunStatus.NEEDS_AUTHOR
            state.events.append(RunEvent(name="research_rejected", detail=notes or ""))
            self.store.save_state(state)
            return state
        state.events.append(RunEvent(name="research_approved", detail=notes or ""))
        brief = ResearchBrief.model_validate_json(
            self.store.read_artifact(run_id, "research.json")
        )
        return self._draft_and_review(state, brief)

    def publish(
        self,
        run_id: str,
        filename: Optional[str] = None,
        feedback: Optional[str] = None,
    ) -> RunState:
        state = self.store.load(run_id)
        if state.status not in {RunStatus.READY, RunStatus.NEEDS_AUTHOR}:
            raise OrchestrationError("Only a reviewed draft can be published")
        draft = self.store.read_artifact(run_id, "final.md").rstrip() + "\n"
        pack = self.packs.get(state.work_order.content_pack)
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
                item.model_dump(mode="json")
                for item in state.work_order.perspective_selections
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
                        else "perspective-extraction-{}.json".format(
                            selection.context_id
                        )
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
        state.status = RunStatus.PUBLISHED
        state.events.append(RunEvent(name="published", detail=state.published_path))
        self._persist_model_history(state.id)
        self.store.save_state(state)
        return state

    def _research(self, state: RunState) -> Optional[ResearchBrief]:
        order = state.work_order
        if order.research_depth == ResearchDepth.NONE:
            state.events.append(RunEvent(name="research_skipped"))
            return None
        state.status = RunStatus.RESEARCHING
        self.store.save_state(state)
        if order.research_source == ResearchSource.SUPPLIED:
            path = Path(order.supplied_research_path or "")
            if not path.is_absolute():
                path = self.root / path
            brief = ResearchBrief.model_validate_json(path.read_text(encoding="utf-8"))
        else:
            brief = self.runner.run(
                role="researcher",
                role_key="researcher-{}".format(order.research_depth.value),
                instruction=(
                    "Create a bounded research brief. Every material claim must link to "
                    "one or more sources. Represent uncertainty and counterevidence."
                ),
                payload={"work_order": order.model_dump(mode="json")},
                order=order,
                output_model=ResearchBrief,
                provider=order.provider,
                tools=["web_search"],
            )
        research_errors = validate_research_brief(brief)
        if research_errors:
            raise OrchestrationError(
                "Research brief failed validation: {}".format("; ".join(research_errors))
            )
        state.events.append(RunEvent(name="research_complete"))
        self.store.save_state(state)
        return brief

    def _draft_and_review(
        self, state: RunState, brief: Optional[ResearchBrief]
    ) -> RunState:
        pack = self.packs.resolve(
            state.work_order.content_pack, state.work_order.pack_options
        )
        previous_critique: Optional[Critique] = None
        prior_score: Optional[float] = None
        stagnant_rounds = 0
        for revision in range(1, self.max_revisions + 1):
            state.revision = revision
            state.status = RunStatus.DRAFTING
            self.store.save_state(state)
            draft = self.runner.run(
                role="writer",
                role_key="writer-{}".format(state.work_order.format),
                instruction=(
                    "Write or revise the piece. Address the prior critique, but preserve "
                    "the author's intent. Return only publishable Markdown."
                ),
                payload=self._draft_payload(state.work_order, brief, previous_critique),
                order=state.work_order,
                provider=state.work_order.provider,
                profile=state.route_plan.model_profiles["writer"],
            )
            self.store.write_artifact(
                state.id, "draft-{:02d}.md".format(revision), draft
            )
            validation_errors = validate_draft(
                draft, state.work_order, pack.validators
            )
            voice_evaluation = evaluate_voice_output(
                self.root, state.work_order, draft
            )
            validation_errors.extend(voice_evaluation["errors"])
            perspective_evaluation = evaluate_perspective_output(
                self.root, state.work_order, draft
            )
            validation_errors.extend(perspective_evaluation["errors"])
            self.store.write_artifact(
                state.id,
                "validation-{:02d}.json".format(revision),
                {"errors": validation_errors},
            )
            self.store.write_artifact(
                state.id,
                "voice-evaluation-{:02d}.json".format(revision),
                voice_evaluation,
            )
            self.store.write_artifact(
                state.id,
                "perspective-evaluation-{:02d}.json".format(revision),
                perspective_evaluation,
            )

            state.status = RunStatus.REVIEWING
            self.store.save_state(state)
            critique = self.runner.run(
                role="critic",
                role_key="critic-{}".format(state.work_order.format),
                instruction=(
                    "Assess this draft independently against the supplied rubrics. "
                    "Return issues and scores; do not decide whether to publish."
                ),
                payload={
                    "work_order": state.work_order.model_dump(mode="json"),
                    "draft": draft,
                    "research": brief.model_dump(mode="json") if brief else None,
                    "validation_errors": validation_errors,
                    "prior_critique": (
                        previous_critique.model_dump(mode="json")
                        if previous_critique
                        else None
                    ),
                },
                order=state.work_order,
                output_model=Critique,
                provider=state.work_order.provider,
                profile=state.route_plan.model_profiles["critic"],
            )
            decision = evaluate_quality(
                critique, self.configuration.rubric("core"), validation_errors
            )
            self.store.write_artifact(
                state.id, "critique-{:02d}.json".format(revision), critique
            )
            self.store.write_artifact(
                state.id, "quality-{:02d}.json".format(revision), decision
            )
            state.events.append(
                RunEvent(
                    name="revision_reviewed",
                    detail="revision={}, score={:.2f}, passed={}".format(
                        revision, decision.weighted_score, decision.passed
                    ),
                )
            )
            if decision.passed:
                self.store.write_artifact(state.id, "final.md", draft)
                state.final_draft_path = "runs/{}/final.md".format(state.id)
                state.status = RunStatus.READY
                state.events.append(RunEvent(name="quality_gate_passed"))
                self._persist_model_history(state.id)
                self.store.save_state(state)
                return state

            if prior_score is not None and decision.weighted_score <= prior_score:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0
            if stagnant_rounds >= 2:
                state.events.append(RunEvent(name="revision_stagnation"))
                break
            prior_score = decision.weighted_score
            previous_critique = critique

        latest = self.store.read_artifact(
            state.id, "draft-{:02d}.md".format(state.revision)
        )
        self.store.write_artifact(state.id, "final.md", latest)
        state.final_draft_path = "runs/{}/final.md".format(state.id)
        state.status = RunStatus.NEEDS_AUTHOR
        state.events.append(RunEvent(name="revision_limit_reached"))
        self._persist_model_history(state.id)
        self.store.save_state(state)
        return state

    @staticmethod
    def _draft_payload(
        order: WorkOrder,
        brief: Optional[ResearchBrief],
        critique: Optional[Critique],
    ) -> Dict:
        return {
            "work_order": order.model_dump(mode="json"),
            "research": brief.model_dump(mode="json") if brief else None,
            "prior_critique": critique.model_dump(mode="json") if critique else None,
        }

    def _available_critiques(self, run_id: str):
        result = []
        for path in sorted(self.store.run_dir(run_id).glob("critique-*.json")):
            result.append(json.loads(path.read_text(encoding="utf-8")))
        return result

    def _persist_model_history(self, run_id: str) -> None:
        self.store.write_artifact(
            run_id,
            "model-selections.json",
            [
                dict(
                    role=request.role,
                    provider=request.selection.provider,
                    profile=request.selection.profile,
                    model=request.selection.model,
                    reasoning_effort=request.selection.reasoning_effort,
                    tools=request.tools,
                    input_tokens=(
                        self.runner.responses[index].input_tokens
                        if index < len(self.runner.responses)
                        else None
                    ),
                    output_tokens=(
                        self.runner.responses[index].output_tokens
                        if index < len(self.runner.responses)
                        else None
                    ),
                )
                for index, request in enumerate(self.runner.history)
            ],
        )

    def _fail(self, state: RunState, exc: Exception) -> None:
        state.status = RunStatus.FAILED
        state.last_error = str(exc)
        state.events.append(RunEvent(name="failed", detail=str(exc)))
        self.store.save_state(state)
