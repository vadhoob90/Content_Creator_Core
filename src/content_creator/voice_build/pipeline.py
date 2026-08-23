"""Provide voice build pipeline contracts and behavior."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import List, Optional, cast

from ..attribution import classify_attribution, isolate_attributed_text
from ..ingestion import content_hash, is_near_duplicate, normalize_text, read_source
from ..linguistics import extract_linguistic_features
from ..runner import AgentRunner, AgentRunOptions
from ..storage import RunStore
from ..versioned_artifacts import publish_candidate, replace_candidate
from ..voice_evolution import VoiceEvolution
from ..voice_upgrade.artifacts import write_upgrade_artifacts
from ..voice_upgrade.guidance import apply_learning_overlays
from ..voice_upgrade.measurements import combine_incremental_measurements
from ..voice_upgrade.models import VoiceUpgradeBuildContext, VoiceUpgradeMode
from ..voices import (
    AttributionResult,
    SourceRecord,
    VoiceManifest,
    VoicePattern,
    VoiceStrategy,
    VoiceWorkOrder,
)
from .corpus import analyse_corpus
from .manifest import write_voice_manifest
from .models import (
    BuildState,
    ProfileCriticism,
    VoiceAnalysis,
    VoiceBuildError,
    VoiceEvaluationJudgement,
    analysis_excerpt,
    public_locator,
)
from .renderer import VoiceProfileRenderer


class VoiceBuildPipeline:
    """Represent a voice build pipeline.

    Compose evidence collection, analysis, rendering, evaluation, and activation.
    """

    def __init__(self, root: Path, runner: Optional[AgentRunner], provider: Optional[str]):
        """Initialize the voice build pipeline.

        Args:
            root (Path): The workspace root directory.
            runner (Optional[AgentRunner]): The agent or command runner used to execute the
                operation.
            provider (Optional[str]): The provider implementation used for generation.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        self.root = root
        self.runner = runner
        self.provider = provider
        self.renderer = VoiceProfileRenderer()

    def build(
        self,
        order: VoiceWorkOrder,
        full_regenerate: bool = False,
        change_set: Optional[Path] = None,
        upgrade_context: Optional[VoiceUpgradeBuildContext] = None,
        source_ids: Optional[dict[str, str]] = None,
        lifecycle_lock_held: bool = False,
    ) -> VoiceManifest:
        """Build a source-derived candidate through the complete governed pipeline.

        Collect only the evidence authorized by the supplied order, preserve active
        guidance by default, evaluate the result, and publish one reviewable candidate.

        Args:
            order (VoiceWorkOrder): The work order that defines the requested content run.
            full_regenerate (bool): Explicitly replace active guidance. Defaults to
                ``False``.
            change_set (Optional[Path]): Evidence-backed semantic change proposals.
                Defaults to ``None``.
            upgrade_context (Optional[VoiceUpgradeBuildContext]): Validated governed
                upgrade plan. Defaults to ``None``.
            source_ids (Optional[dict[str, str]]): Stable evidence IDs by locator. Defaults
                to ``None``.
            lifecycle_lock_held (bool): Whether the application boundary owns the shared
                lifecycle lock. Defaults to ``False``.

        Returns:
            VoiceManifest: The constructed voice manifest for value.
        """
        state = self._prepare(order)
        state.upgrade_context = upgrade_context
        state.source_ids = source_ids or {}
        state.lifecycle_lock_held = lifecycle_lock_held
        selected_learning_ids = (
            {
                item.learning_id
                for item in upgrade_context.learning_selection.dispositions
                if item.disposition.value == "incorporate"
            }
            if upgrade_context
            else set()
        )
        state.evolution = VoiceEvolution(
            self.root,
            order.voice_id,
            full_regenerate,
            change_set,
            approved_learning_ids=selected_learning_ids,
        )
        self._collect_sources(state)
        self._analyse_corpus(state)
        if upgrade_context and upgrade_context.plan.mode == VoiceUpgradeMode.INCREMENTAL:
            combine_incremental_measurements(state, state.evolution.baseline_dir)
        self._analyse_patterns(state)
        profile, constraints, voice_rubric = self._write_profile_artifacts(state)
        evolved = state.evolution.apply(state.candidate)
        if upgrade_context:
            evolved = apply_learning_overlays(
                state.candidate,
                evolved,
                upgrade_context.learning_selection,
                upgrade_context.selected_learning_records,
            )
            write_upgrade_artifacts(state.candidate, upgrade_context)
        state.patterns = evolved.patterns
        evaluation = self._evaluate(state, evolved.profile, evolved.constraints, evolved.rubric)
        manifest = write_voice_manifest(state, evaluation)
        if state.lifecycle_lock_held:
            self._activate_candidate(state)
        else:
            publish_candidate(state.voice_root, self._activate_candidate, state, VoiceBuildError)
        return manifest

    def _prepare(self, order: VoiceWorkOrder) -> BuildState:
        """Prepare the voice build pipeline workflow.

        Args:
            order (VoiceWorkOrder): The work order that defines the requested content run.

        Returns:
            BuildState: The prepared build state for value.

        Raises:
            VoiceBuildError: If the voice build operation cannot complete.
        """
        if order.strategy != VoiceStrategy.SOURCE_DERIVED:
            raise VoiceBuildError(
                "Starter voices are activated from their template; select "
                "source-derived onboarding before building from evidence"
            )
        voice_root = self.root / "profiles" / order.voice_id
        candidate = voice_root / ".candidate-staging"
        if candidate.exists():
            shutil.rmtree(candidate)
        return BuildState(
            order=order,
            voice_root=voice_root,
            candidate=candidate,
            final_candidate=voice_root / "candidate",
            cache=self.root / ".voice-cache" / order.voice_id,
        )

    def _collect_sources(self, state: BuildState) -> None:
        """Collect the sources.

        Args:
            state (BuildState): The persisted lifecycle state to inspect or update.

        Returns:
            None: The callable updates sources state and returns no value.
        """
        for index, locator in enumerate(state.order.urls + state.order.documents, start=1):
            try:
                self._collect_source(
                    state,
                    locator,
                    state.source_ids.get(locator, f"source-{index:03d}"),
                )
            except Exception as error:
                state.errors.append(
                    {
                        "locator": public_locator(locator),
                        "error": str(error).replace(locator, public_locator(locator)),
                    }
                )

    def _collect_source(self, state: BuildState, locator: str, source_id: str) -> None:
        """Collect the source.

        Args:
            state (BuildState): The persisted lifecycle state to inspect or update.
            locator (str): The source locator used to retrieve the document.
            source_id (str): The stable identifier for the source.

        Returns:
            None: The callable updates source state and returns no value.
        """
        cache_path = state.cache / f"{source_id}.txt"
        metadata_path = state.cache / f"{source_id}.meta.json"
        kind, title, text = self._read_source(locator, cache_path, metadata_path)
        duplicate = is_near_duplicate(text, state.normalized_sources)
        locally_attested = locator in state.order.documents and state.order.authorisation.confirmed
        attribution = self._attribution(state.order, locator, kind, title, text, locally_attested)
        analysis_text, analysis_scope = isolate_attributed_text(
            text,
            state.order.attribution_name,
            attribution,
            kind,
            state.order.author_aliases,
        )
        if locally_attested and analysis_text == text.strip():
            analysis_scope = "full-source-author-attested"
        approved = attribution.voice_weight > 0 and not duplicate and bool(analysis_text.strip())
        self._cache_source(cache_path, metadata_path, locator, kind, title, text)
        state.analysis_texts[source_id] = analysis_text
        state.sources.append(
            SourceRecord(
                id=source_id,
                kind=kind,
                locator=public_locator(locator),
                content_hash=content_hash(text),
                title=title,
                word_count=len(text.split()),
                attribution=attribution,
                approved_for_analysis=approved,
                cache_path=str(cache_path.relative_to(self.root)),
                analysis_word_count=len(analysis_text.split()),
                analysis_scope=analysis_scope,
            )
        )
        state.normalized_sources.append(text)

    @staticmethod
    def _read_source(locator: str, cache_path: Path, metadata_path: Path) -> tuple[str, str, str]:
        """Read the source.

        Args:
            locator (str): The source locator used to retrieve the document.
            cache_path (Path): The filesystem path for the cache path.
            metadata_path (Path): The filesystem path for the metadata path.

        Returns:
            tuple[str, str, str]: The loaded source values in their documented order.
        """
        if not (locator.startswith(("http://", "https://")) and cache_path.exists()):
            return read_source(locator)
        text = normalize_text(cache_path.read_text(encoding="utf-8"))
        kind, title = "webpage", locator
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("locator") == locator:
                kind = metadata.get("kind", kind)
                title = metadata.get("title", title)
        return kind, title, text

    def _attribution(
        self,
        order: VoiceWorkOrder,
        _locator: str,
        kind: str,
        title: str,
        text: str,
        locally_attested: bool,
    ) -> AttributionResult:
        """Return the attribution.

        Args:
            order (VoiceWorkOrder): The work order that defines the requested content run.
            _locator (str): The intentionally unused source locator retained by the
                attribution callback contract.
            kind (str): The domain category used to classify the value.
            title (str): The title text processed when attribution.
            text (str): The text to process.
            locally_attested (bool): Whether locally attested behavior is enabled.

        Returns:
            AttributionResult: The resulting attribution result for attribution.
        """
        if locally_attested:
            return AttributionResult(
                classification="directly_authored",
                confidence=1.0,
                voice_weight=1.0,
                evidence=[
                    "Local document authorship attested by "
                    + (order.authorisation.attested_by or "the repository owner")
                ],
            )
        attribution = classify_attribution(text, order.attribution_name, kind, order.author_aliases)
        if not (attribution.needs_human_review and self.runner):
            return attribution
        return self.runner.run(
            role="attribution-reviewer",
            role_key="attribution-reviewer",
            instruction=(
                "Resolve attribution only from supplied evidence; retain zero "
                "weight when uncertain."
            ),
            payload={
                "person": order.attribution_name,
                "aliases": order.author_aliases,
                "kind": kind,
                "title": title,
                "excerpt": text[:2000],
            },
            options=AgentRunOptions(output_model=AttributionResult, provider=self.provider),
        )

    @staticmethod
    def _cache_source(
        cache_path: Path,
        metadata_path: Path,
        locator: str,
        kind: str,
        title: str,
        text: str,
    ) -> None:
        """Return the cache source.

        Args:
            cache_path (Path): The filesystem path for the cache path.
            metadata_path (Path): The filesystem path for the metadata path.
            locator (str): The source locator used to retrieve the document.
            kind (str): The domain category used to classify the value.
            title (str): The title text processed when cache source.
            text (str): The text to process.

        Returns:
            None: The callable updates cache source state and returns no value.
        """
        RunStore._atomic_text(cache_path, text)
        metadata = {
            "locator": locator,
            "kind": kind,
            "title": title,
            "content_hash": content_hash(text),
        }
        RunStore._atomic_text(metadata_path, json.dumps(metadata, indent=2))

    def _analyse_corpus(self, state: BuildState) -> None:
        """Return the analyse corpus.

        Args:
            state (BuildState): The persisted lifecycle state to inspect or update.

        Returns:
            None: The callable updates analyse corpus state and returns no value.

        """
        analyse_corpus(
            state,
            self.renderer,
            allow_insufficient_delta=bool(
                state.upgrade_context
                and state.upgrade_context.plan.mode == VoiceUpgradeMode.INCREMENTAL
            ),
        )

    def _analyse_patterns(self, state: BuildState) -> None:
        """Return the analyse patterns.

        Args:
            state (BuildState): The persisted lifecycle state to inspect or update.

        Returns:
            None: The callable updates analyse patterns state and returns no value.
        """
        if not (self.runner and state.analysis_records):
            return
        analysis = self.runner.run(
            role="voice-analyst",
            role_key="voice-analyst",
            instruction="Identify supported style patterns without inferring biography or beliefs.",
            payload=self._analysis_payload(state),
            options=AgentRunOptions(output_model=VoiceAnalysis, provider=self.provider),
        )
        criticism = self.runner.run(
            role="profile-critic",
            role_key="profile-critic",
            instruction="Reject unsupported, copied, topic-specific, or caricatured patterns.",
            payload={
                "analysis": analysis.model_dump(mode="json"),
                "linguistic_signature": state.signature,
                "approved_source_ids": [record.id for record in state.analysis_records],
            },
            options=AgentRunOptions(output_model=ProfileCriticism, provider=self.provider),
        )
        state.analysis_artifact = analysis.model_dump(mode="json")
        state.criticism_artifact = criticism.model_dump(mode="json")
        approved_ids = {record.id for record in state.analysis_records}
        state.patterns = self._reviewed_patterns(analysis, criticism, approved_ids)

    def _analysis_payload(self, state: BuildState) -> dict:
        """Return the analysis payload.

        Args:
            state (BuildState): The persisted lifecycle state to inspect or update.

        Returns:
            dict: The resulting dict for analysis payload.
        """
        return {
            "person": state.order.attribution_name,
            "voice_label": state.order.display_name,
            "sources": [
                {
                    "id": record.id,
                    "kind": record.kind,
                    "attribution_weight": record.attribution.voice_weight,
                    "analysis_scope": record.analysis_scope,
                    "text": analysis_excerpt(state.analysis_texts[record.id]),
                    "linguistic_features": extract_linguistic_features(
                        state.analysis_texts[record.id]
                    ),
                }
                for record in state.analysis_records
            ],
            "corpus": state.corpus,
            "linguistic_signature": state.signature,
        }

    @staticmethod
    def _reviewed_patterns(
        analysis: VoiceAnalysis,
        criticism: ProfileCriticism,
        approved_ids: set[str],
    ) -> List[VoicePattern]:
        """Return the reviewed patterns.

        Args:
            analysis (VoiceAnalysis): The analysis value passed to reviewed patterns.
            criticism (ProfileCriticism): The criticism value passed to reviewed patterns.
            approved_ids (set[str]): The approved ids collection consumed while reviewed
                patterns.

        Returns:
            List[VoicePattern]: The resulting reviewed patterns values in their documented
                order.
        """
        reviewed = []
        for pattern in analysis.patterns:
            pattern.supporting_source_ids = [
                source_id
                for source_id in pattern.supporting_source_ids
                if source_id in approved_ids
            ]
            if pattern.id in criticism.rejected_pattern_ids:
                pattern.status = "rejected"
            elif pattern.status == "confirmed" and len(pattern.supporting_source_ids) < 2:
                pattern.status = "provisional"
            reviewed.append(pattern)
        return reviewed

    def _write_profile_artifacts(self, state: BuildState) -> tuple[str, dict, dict]:
        """Write the profile artifacts.

        Args:
            state (BuildState): The persisted lifecycle state to inspect or update.

        Returns:
            tuple[str, dict, dict]: The resulting write profile artifacts values in their
                documented order.
        """
        state.candidate.mkdir(parents=True, exist_ok=True)
        constraints = {
            "never_invent_personal_context": True,
            "never_copy_source_phrases": True,
            "provisional_patterns_are_optional": True,
        }
        voice_rubric = {
            "minimums": {
                "characteristic_alignment": 8,
                "naturalness": 8,
                "personal_integrity": 10,
                "channel_fit": 8,
                "non_imitation": 10,
            },
            "hard_gates": ["unsupported_personal_context", "material_phrase_overlap"],
        }
        profile = self.renderer.profile(state.order, state.patterns, state.corpus)
        artifacts = {
            "profile.md": profile,
            "constraints.json": json.dumps(constraints, indent=2),
            "voice-rubric.json": json.dumps(voice_rubric, indent=2),
            "source-index.json": json.dumps(
                [record.model_dump(mode="json") for record in state.sources], indent=2
            ),
            "patterns.json": json.dumps(
                [pattern.model_dump(mode="json") for pattern in state.patterns], indent=2
            ),
            "corpus-report.json": json.dumps(state.corpus, indent=2),
            "linguistic-signature.json": json.dumps(state.signature, indent=2),
        }
        for filename, contents in artifacts.items():
            RunStore._atomic_text(state.candidate / filename, contents)
        self._write_agent_artifacts(state)
        return profile, constraints, voice_rubric

    @staticmethod
    def _write_agent_artifacts(state: BuildState) -> None:
        """Write the agent artifacts.

        Args:
            state (BuildState): The persisted lifecycle state to inspect or update.

        Returns:
            None: The callable updates write agent artifacts state and returns no value.
        """
        optional_artifacts = {
            "analyst-report.json": state.analysis_artifact,
            "critic-report.json": state.criticism_artifact,
        }
        for filename, report in optional_artifacts.items():
            if report is not None:
                RunStore._atomic_text(state.candidate / filename, json.dumps(report, indent=2))

    def _evaluate(
        self, state: BuildState, profile: str, constraints: dict, voice_rubric: dict
    ) -> dict:
        """Evaluate the voice build pipeline workflow.

        Args:
            state (BuildState): The persisted lifecycle state to inspect or update.
            profile (str): The resolved voice, perspective, or content profile.
            constraints (dict): The constraints value passed to evaluate.
            voice_rubric (dict): The voice rubric value passed to evaluate.

        Returns:
            dict: The evaluation dict for value.
        """
        evaluation = {
            "schema_version": "1.0",
            "passed": state.corpus["sufficient"] and bool(state.patterns),
            "hard_failures": [] if state.corpus["sufficient"] else ["insufficient_corpus"],
            "checks": {
                "provenance": all(pattern.supporting_source_ids for pattern in state.patterns),
                "held_out_allocation": bool(state.held_out) or bool(state.upgrade_context),
                "held_out_excluded_from_analysis": all(
                    not set(pattern.supporting_source_ids)
                    & set(state.corpus["held_out_source_ids"])
                    for pattern in state.patterns
                ),
                "unseen_topic_transfer": "manual_live_evaluation_required",
                "caricature_rejection": True,
                "phrase_overlap": True,
                "linguistic_signature": bool(state.signature["source_profiles"]),
                "matched_register_baseline": "not_supplied",
            },
        }
        regression = state.evolution.regression_evaluation(state.candidate)
        evaluation["regression_evaluation"] = regression
        if not regression["passed"]:
            cast(List[str], evaluation["hard_failures"]).append("active_voice_regression")
            evaluation["passed"] = False
        if self.runner and state.patterns:
            self._apply_agent_evaluation(state, evaluation, profile, constraints, voice_rubric)
        RunStore._atomic_text(
            state.candidate / "evaluation-report.json", json.dumps(evaluation, indent=2)
        )
        return evaluation

    def _apply_agent_evaluation(
        self,
        state: BuildState,
        evaluation: dict,
        profile: str,
        constraints: dict,
        voice_rubric: dict,
    ) -> None:
        """Apply the agent evaluation.

        Args:
            state (BuildState): The persisted lifecycle state to inspect or update.
            evaluation (dict): The evaluation value passed to apply agent evaluation.
            profile (str): The resolved voice, perspective, or content profile.
            constraints (dict): The constraints value passed to apply agent evaluation.
            voice_rubric (dict): The voice rubric value passed to apply agent evaluation.

        Returns:
            None: The callable updates apply agent evaluation state and returns no value.
        """
        if self.runner is None:
            return
        judgement = self.runner.run(
            role="voice-evaluator",
            role_key="voice-evaluator",
            instruction=(
                "Evaluate transfer, channel fit, caricature resistance, and personal integrity."
            ),
            payload=self._evaluation_payload(state, profile, constraints, voice_rubric),
            options=AgentRunOptions(output_model=VoiceEvaluationJudgement, provider=self.provider),
        )
        evaluation["agent_judgement"] = judgement.model_dump(mode="json")
        cast(List[str], evaluation["hard_failures"]).extend(judgement.hard_failures)
        evaluation["passed"] = (
            evaluation["passed"] and judgement.passed and not judgement.hard_failures
        )

    @staticmethod
    def _evaluation_payload(
        state: BuildState, profile: str, constraints: dict, voice_rubric: dict
    ) -> dict:
        """Return the evaluation payload.

        Args:
            state (BuildState): The persisted lifecycle state to inspect or update.
            profile (str): The resolved voice, perspective, or content profile.
            constraints (dict): The constraints value passed to evaluation payload.
            voice_rubric (dict): The voice rubric value passed to evaluation payload.

        Returns:
            dict: The resulting dict for evaluation payload.
        """
        return {
            "profile": profile,
            "constraints": constraints,
            "voice_rubric": voice_rubric,
            "linguistic_signature": state.signature,
            "patterns": [pattern.model_dump(mode="json") for pattern in state.patterns],
            "held_out_sources": [
                {
                    "id": record.id,
                    "text": analysis_excerpt(state.analysis_texts[record.id], 4000),
                    "linguistic_features": extract_linguistic_features(
                        state.analysis_texts[record.id]
                    ),
                }
                for record in state.held_out
            ],
            "supported_packs": state.corpus["supported_packs"],
            "adversarial_cases": [
                "generic draft with no characteristic choices",
                "caricature stacking every observed mannerism",
                "invented personal experience",
            ],
        }

    @staticmethod
    def _activate_candidate(state: BuildState) -> None:
        """Activate the candidate.

        Args:
            state (BuildState): The persisted lifecycle state to inspect or update.

        Returns:
            None: The callable updates activate candidate state and returns no value.
        """
        replace_candidate(state.candidate, state.final_candidate)
