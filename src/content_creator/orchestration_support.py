from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from .capabilities import DefaultRunCapabilities, RunCapabilities
from .configuration import Configuration
from .diagnostics import RuntimeDiagnostics
from .domain import (
    Critique,
    ModelResponse,
    ResearchBrief,
    ResearchDepth,
    ResearchSource,
    RunEvent,
    RunState,
    RunStatus,
    WorkOrder,
)
from .intake import BriefingAgent
from .packs import PackRegistry
from .perspective_evaluation import evaluate_perspective_output
from .prompting import PromptAssembler
from .providers import ProviderRegistry
from .quality import evaluate_quality
from .runner import AgentRunner, AgentRunOptions
from .stages import CallableDraftReviewStage, CallableResearchStage, LifecycleStages
from .storage import RunStore, StorageError
from .validation import validate_draft, validate_research_brief
from .voice_evaluation import evaluate_voice_output


class OrchestrationError(RuntimeError):
    pass


class OrchestrationSupport:
    def __init__(
        self,
        root: Path,
        registry: Optional[ProviderRegistry] = None,
        visual_adapters: Any = None,
        max_revisions: int = 3,
        capabilities: Optional[RunCapabilities] = None,
        stages: Optional[LifecycleStages] = None,
    ):
        self.root = root.resolve()
        self.configuration = Configuration(self.root)
        self.registry = registry or ProviderRegistry(root=self.root)
        self.prompts = PromptAssembler(self.root)
        self.diagnostics = RuntimeDiagnostics(
            self.root,
            enabled=self.configuration.diagnostic_policy["enabled"],
        )
        self.runner = AgentRunner(
            self.configuration,
            self.registry,
            self.prompts,
            diagnostics=self.diagnostics,
        )
        self.intake = BriefingAgent(self.runner)
        self.store = RunStore(self.root)
        self.packs = PackRegistry(self.root)
        self.capabilities = capabilities or DefaultRunCapabilities(self.root, visual_adapters)
        self.visuals = self.capabilities.visuals
        self.max_revisions = max_revisions
        self.stages = stages or LifecycleStages(
            research=CallableResearchStage(self._research),
            draft_review=CallableDraftReviewStage(self._draft_and_review),
        )

    def diagnostic_preflight(self, run_id: str) -> Dict:
        state = self.store.load(run_id)
        self.diagnostics.begin_invocation(state.work_order.content_session_id)
        self.diagnostics.bind_run(run_id, state.work_order.content_session_id)
        result = self.diagnostics.preflight(run_id)
        self._apply_diagnostic_state(state, result)
        self.store.save_state(state)
        return result

    def link_diagnostic_issue(self, run_id: str, issue_url: str) -> Dict:
        result = self.diagnostics.link_issue(run_id, issue_url)
        state = self.store.load(run_id)
        preflight = self.diagnostics.preflight(run_id)
        self._apply_diagnostic_state(state, preflight)
        self.store.save_state(state)
        return result

    def _preflight_supplied_research(self, order: WorkOrder) -> Optional[ResearchBrief]:
        if order.research_source != ResearchSource.SUPPLIED:
            return None
        path = Path(order.supplied_research_path or "")
        if not path.is_absolute():
            path = self.root / path
        try:
            payload = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise OrchestrationError("Supplied research file could not be read") from exc
        try:
            brief = ResearchBrief.model_validate_json(payload)
        except ValueError as exc:
            raise OrchestrationError("Supplied research is not valid ResearchBrief JSON") from exc
        research_errors = validate_research_brief(brief)
        if research_errors:
            raise OrchestrationError(
                "Research brief failed validation: {}".format("; ".join(research_errors))
            )
        return brief

    @staticmethod
    def _submission_fingerprint(
        order: WorkOrder,
        supplied_brief: Optional[ResearchBrief],
    ) -> str:
        payload = order.model_dump(mode="json")
        for transient in (
            "content_session_id",
            "resolved_voice",
            "resolved_perspective",
            "supplied_research_path",
        ):
            payload.pop(transient, None)
        payload["supplied_research"] = (
            supplied_brief.model_dump(mode="json") if supplied_brief else None
        )
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _research(
        self,
        state: RunState,
        supplied_brief: Optional[ResearchBrief] = None,
    ) -> Optional[ResearchBrief]:
        order = state.work_order
        if order.research_depth == ResearchDepth.NONE:
            state.events.append(RunEvent(name="research_skipped"))
            return None
        state.status = RunStatus.RESEARCHING
        self.store.save_state(state)
        if order.research_source == ResearchSource.SUPPLIED:
            if supplied_brief is None:
                raise OrchestrationError("Supplied research did not pass preflight")
            brief = supplied_brief
        else:
            brief = self.runner.run(
                role="researcher",
                role_key="researcher-{}".format(order.research_depth.value),
                instruction=(
                    "Create a bounded research brief. Every material claim must link to "
                    "one or more sources. Represent uncertainty and counterevidence."
                ),
                payload={"work_order": order.model_dump(mode="json")},
                options=AgentRunOptions(
                    order=order,
                    output_model=ResearchBrief,
                    provider=order.provider,
                    tools=["web_search"],
                ),
            )
            research_errors = validate_research_brief(brief)
            if research_errors:
                raise OrchestrationError(
                    "Research brief failed validation: {}".format("; ".join(research_errors))
                )
        state.events.append(RunEvent(name="research_complete"))
        self.store.save_state(state)
        return brief

    def _draft_and_review(self, state: RunState, brief: Optional[ResearchBrief]) -> RunState:
        pack = self.packs.resolve(state.work_order.content_pack, state.work_order.pack_options)
        revision_context = self._revision_context(state.work_order)
        previous_critique: Optional[Critique] = None
        prior_score: Optional[float] = None
        stagnant_rounds = 0
        for revision in range(1, self.max_revisions + 1):
            draft, critique, decision = self._draft_revision(
                state, brief, pack, revision_context, previous_critique, revision
            )
            if decision.passed:
                return self._accept_draft(state, draft)
            stagnant_rounds = (
                stagnant_rounds + 1
                if prior_score is not None and decision.weighted_score <= prior_score
                else 0
            )
            if stagnant_rounds >= 2:
                state.events.append(RunEvent(name="revision_stagnation"))
                break
            prior_score = decision.weighted_score
            previous_critique = critique
        return self._defer_to_author(state)

    def _draft_revision(
        self,
        state: RunState,
        brief: Optional[ResearchBrief],
        pack: Any,
        revision_context: Optional[Dict],
        previous_critique: Optional[Critique],
        revision: int,
    ) -> tuple[str, Critique, Any]:
        state.revision = revision
        state.status = RunStatus.DRAFTING
        self.store.save_state(state)
        draft = self.runner.run(
            role="writer",
            role_key=f"writer-{state.work_order.format}",
            instruction=(
                "Write or revise the piece. Address the prior critique, but preserve "
                "the author's intent. Return only publishable Markdown."
            ),
            payload=self._draft_payload(
                state.work_order, brief, previous_critique, revision_context
            ),
            options=AgentRunOptions(
                order=state.work_order,
                provider=state.work_order.provider,
                profile=state.route_plan.model_profiles["writer"],
            ),
        )
        self.store.write_artifact(state.id, f"draft-{revision:02d}.md", draft)
        validation_errors, statistical_score = self._validate_revision(state, pack, draft, revision)
        critique = self._critique_revision(
            state, brief, draft, validation_errors, statistical_score, previous_critique
        )
        decision = evaluate_quality(critique, self.configuration.rubric("core"), validation_errors)
        self.store.write_artifact(state.id, f"critique-{revision:02d}.json", critique)
        self.store.write_artifact(state.id, f"quality-{revision:02d}.json", decision)
        state.events.append(
            RunEvent(
                name="revision_reviewed",
                detail=(
                    f"revision={revision}, score={decision.weighted_score:.2f}, "
                    f"passed={decision.passed}"
                ),
            )
        )
        return draft, critique, decision

    def _validate_revision(
        self, state: RunState, pack: Any, draft: str, revision: int
    ) -> tuple[List[str], Optional[Dict[str, Any]]]:
        errors = validate_draft(draft, state.work_order, pack.validators)
        voice_evaluation = evaluate_voice_output(self.root, state.work_order, draft)
        errors.extend(voice_evaluation["errors"])
        perspective_evaluation = evaluate_perspective_output(self.root, state.work_order, draft)
        errors.extend(perspective_evaluation["errors"])
        self.store.write_artifact(state.id, f"validation-{revision:02d}.json", {"errors": errors})
        self.store.write_artifact(
            state.id, f"voice-evaluation-{revision:02d}.json", voice_evaluation
        )
        self.store.write_artifact(
            state.id, f"perspective-evaluation-{revision:02d}.json", perspective_evaluation
        )
        statistical_score = self.capabilities.assess_voice(
            state.work_order.voice_id,
            state.work_order.voice_version,
            draft,
            self.configuration.statistical_voice_score_policy,
            pack.statistical_voice_score.eligible,
        )
        if statistical_score is not None:
            self.store.write_artifact(
                state.id, f"statistical-voice-score-{revision:02d}.json", statistical_score
            )
        return errors, statistical_score

    def _critique_revision(
        self,
        state: RunState,
        brief: Optional[ResearchBrief],
        draft: str,
        validation_errors: List[str],
        statistical_score: Optional[Dict[str, Any]],
        previous_critique: Optional[Critique],
    ) -> Critique:
        state.status = RunStatus.REVIEWING
        self.store.save_state(state)
        payload = {
            "work_order": state.work_order.model_dump(mode="json"),
            "draft": draft,
            "research": brief.model_dump(mode="json") if brief else None,
            "validation_errors": validation_errors,
            "prior_critique": (
                previous_critique.model_dump(mode="json") if previous_critique else None
            ),
        }
        if statistical_score is not None:
            payload["statistical_voice_score"] = statistical_score
        advisory = (
            " Treat the statistical voice score as advisory evidence only. Account for "
            "context and natural variation; do not request a change solely to improve "
            "numerical conformity."
            if statistical_score is not None
            else ""
        )
        return self.runner.run(
            role="critic",
            role_key=f"critic-{state.work_order.format}",
            instruction=(
                "Assess this draft independently against the supplied rubrics. Return issues "
                "and scores; do not decide whether to publish. For each prior issue, return "
                "a machine-readable status of resolved, unresolved, or author_rejected "
                f"separately from its note.{advisory}"
            ),
            payload=payload,
            options=AgentRunOptions(
                order=state.work_order,
                output_model=Critique,
                provider=state.work_order.provider,
                profile=state.route_plan.model_profiles["critic"],
            ),
        )

    def _accept_draft(self, state: RunState, draft: str) -> RunState:
        self.store.write_artifact(state.id, "final.md", draft)
        state.final_draft_path = f"runs/{state.id}/final.md"
        state.status = RunStatus.READY
        state.events.append(RunEvent(name="quality_gate_passed"))
        self._persist_model_history(state.id)
        self.store.save_state(state)
        return state

    def _defer_to_author(self, state: RunState) -> RunState:
        latest = self.store.read_artifact(state.id, f"draft-{state.revision:02d}.md")
        self.store.write_artifact(state.id, "final.md", latest)
        state.final_draft_path = f"runs/{state.id}/final.md"
        state.status = RunStatus.NEEDS_AUTHOR
        state.events.append(RunEvent(name="revision_limit_reached"))
        self._persist_model_history(state.id)
        self.store.save_state(state)
        return state

    def _revision_context(self, order: WorkOrder) -> Optional[Dict]:
        if not order.parent_run_id:
            return None
        parent = self.store.load(order.parent_run_id)
        if parent.status not in {RunStatus.READY, RunStatus.NEEDS_AUTHOR, RunStatus.PUBLISHED}:
            raise OrchestrationError(
                "Parent run {} has no reviewed draft to revise (status: {})".format(
                    parent.id, parent.status.value
                )
            )
        try:
            parent_draft = self.store.read_artifact(parent.id, "final.md")
        except StorageError as exc:
            raise OrchestrationError(
                "Parent run {} is missing its reviewed final draft".format(parent.id)
            ) from exc
        return {
            "parent_run_id": parent.id,
            "content_session_id": parent.work_order.content_session_id,
            "parent_status": parent.status.value,
            "parent_revision": parent.revision,
            "parent_draft": parent_draft,
            "revision_instruction": (
                "Use the parent draft as the revision baseline. Make only the requested "
                "changes and preserve all unaffected approved passages."
            ),
        }

    @staticmethod
    def _draft_payload(
        order: WorkOrder,
        brief: Optional[ResearchBrief],
        critique: Optional[Critique],
        revision_context: Optional[Dict] = None,
    ) -> Dict:
        return {
            "work_order": order.model_dump(mode="json"),
            "research": brief.model_dump(mode="json") if brief else None,
            "prior_critique": critique.model_dump(mode="json") if critique else None,
            "revision_context": revision_context,
        }

    def _available_critiques(self, run_id: str) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for path in sorted(self.store.run_dir(run_id).glob("critique-*.json")):
            result.append(json.loads(path.read_text(encoding="utf-8")))
        return result

    def _persist_model_history(self, run_id: str) -> None:
        responses = self.runner.responses
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
                        cast(ModelResponse, responses[index]).input_tokens
                        if index < len(responses) and responses[index] is not None
                        else None
                    ),
                    output_tokens=(
                        cast(ModelResponse, responses[index]).output_tokens
                        if index < len(responses) and responses[index] is not None
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
        self.diagnostics.record_terminal_failure(exc)
        self.store.save_state(state)
        preflight = self.diagnostics.preflight(state.id)
        self._apply_diagnostic_state(state, preflight)
        self.store.save_state(state)

    @staticmethod
    def _apply_diagnostic_state(state: RunState, preflight: Dict) -> None:
        state.diagnostic_summary_path = preflight.get("diagnostic_summary")
        state.support_candidate_path = preflight.get("support_candidate")
        state.pending_support_count = sum(
            1
            for item in preflight.get("candidates", [])
            if item.get("status") in {"deferred", "presented"}
        )
