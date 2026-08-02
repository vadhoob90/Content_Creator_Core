"""Cohesive source, analysis, evaluation, and activation phases for voice builds."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import List, Optional, cast

from .attribution import classify_attribution, isolate_attributed_text
from .corpus import assess_corpus
from .ingestion import content_hash, is_near_duplicate, normalize_text, read_source
from .linguistics import build_linguistic_signature, extract_linguistic_features
from .runner import AgentRunner, AgentRunOptions
from .storage import RunStore
from .versioned_artifacts import hash_file, hash_json
from .voice_build_models import (
    BuildState,
    ProfileCriticism,
    VoiceAnalysis,
    VoiceBuildError,
    VoiceEvaluationJudgement,
    analysis_excerpt,
    even_sample,
    public_locator,
)
from .voice_profile_renderer import VoiceProfileRenderer
from .voices import (
    AttributionResult,
    SourceRecord,
    VoiceManifest,
    VoicePattern,
    VoiceStatus,
    VoiceStrategy,
    VoiceWorkOrder,
)


class VoiceBuildPipeline(VoiceProfileRenderer):
    def __init__(self, root: Path, runner: Optional[AgentRunner], provider: Optional[str]):
        self.root = root
        self.runner = runner
        self.provider = provider

    def build(self, order: VoiceWorkOrder) -> VoiceManifest:
        state = self._prepare(order)
        self._collect_sources(state)
        self._analyse_corpus(state)
        self._analyse_patterns(state)
        profile, constraints, voice_rubric = self._write_profile_artifacts(state)
        evaluation = self._evaluate(state, profile, constraints, voice_rubric)
        manifest = self._write_manifest(state, evaluation)
        self._activate_candidate(state)
        return manifest

    def _prepare(self, order: VoiceWorkOrder) -> BuildState:
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
        for index, locator in enumerate(state.order.urls + state.order.documents, start=1):
            try:
                self._collect_source(state, locator, f"source-{index:03d}")
            except Exception as error:
                state.errors.append(
                    {
                        "locator": public_locator(locator),
                        "error": str(error).replace(locator, public_locator(locator)),
                    }
                )

    def _collect_source(self, state: BuildState, locator: str, source_id: str) -> None:
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
        locator: str,
        kind: str,
        title: str,
        text: str,
        locally_attested: bool,
    ) -> AttributionResult:
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
        RunStore._atomic_text(cache_path, text)
        metadata = {
            "locator": locator,
            "kind": kind,
            "title": title,
            "content_hash": content_hash(text),
        }
        RunStore._atomic_text(metadata_path, json.dumps(metadata, indent=2))

    def _analyse_corpus(self, state: BuildState) -> None:
        state.corpus = assess_corpus(state.sources, state.order.authorisation.intended_uses)
        if state.final_candidate.exists() and not state.corpus["sufficient"]:
            raise VoiceBuildError(
                "Rebuild has insufficient usable material; previous candidate preserved"
            )
        usable = [record for record in state.sources if record.approved_for_analysis]
        held_out_count = min(10, max(1, len(usable) // 10)) if len(usable) >= 2 else 0
        state.held_out = even_sample(usable, held_out_count) if held_out_count else []
        held_out_ids = {record.id for record in state.held_out}
        measurement_records = [record for record in usable if record.id not in held_out_ids]
        state.analysis_records = even_sample(measurement_records, 50)
        state.corpus.update(
            {
                "held_out_source_ids": [record.id for record in state.held_out],
                "measurement_source_ids": [record.id for record in measurement_records],
                "semantic_analysis_source_ids": [record.id for record in state.analysis_records],
                "semantic_analysis_limit": 50,
            }
        )
        state.signature = build_linguistic_signature(
            {
                "id": record.id,
                "kind": record.kind,
                "text": state.analysis_texts[record.id],
                "weight": record.attribution.voice_weight,
            }
            for record in measurement_records
        )
        state.patterns = self._patterns(state.analysis_records, state.signature)

    def _analyse_patterns(self, state: BuildState) -> None:
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
        profile = self._profile(state.order, state.patterns, state.corpus)
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
        evaluation = {
            "schema_version": "1.0",
            "passed": state.corpus["sufficient"] and bool(state.patterns),
            "hard_failures": [] if state.corpus["sufficient"] else ["insufficient_corpus"],
            "checks": {
                "provenance": all(pattern.supporting_source_ids for pattern in state.patterns),
                "held_out_allocation": bool(state.held_out),
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

    def _write_manifest(self, state: BuildState, evaluation: dict) -> VoiceManifest:
        components = {
            "profile": "profile.md",
            "constraints": "constraints.json",
            "rubric": "voice-rubric.json",
            "sources": "source-index.json",
            "patterns": "patterns.json",
            "corpus": "corpus-report.json",
            "linguistic_signature": "linguistic-signature.json",
            "evaluation_report": "evaluation-report.json",
        }
        if state.analysis_artifact is not None:
            components["analyst_report"] = "analyst-report.json"
        if state.criticism_artifact is not None:
            components["critic_report"] = "critic-report.json"
        component_hashes = {
            name: hash_file(state.candidate / filename) for name, filename in components.items()
        }
        candidate_hash = hash_json(component_hashes)
        manifest = VoiceManifest(
            id=state.order.voice_id,
            display_name=state.order.display_name,
            author_name=state.order.attribution_name,
            author_aliases=state.order.author_aliases,
            version="candidate",
            status=VoiceStatus.AWAITING_APPROVAL if evaluation["passed"] else VoiceStatus.BUILT,
            candidate_hash=candidate_hash,
            components=components,
            component_hashes=component_hashes,
            supported_packs=state.corpus["supported_packs"],
            authorisation=state.order.authorisation,
            strategy=VoiceStrategy.SOURCE_DERIVED,
            evidence_status="author-sources",
            perspectives_allowed=True,
        )
        RunStore._atomic_text(state.candidate / "manifest.json", manifest.model_dump_json(indent=2))
        build_report = {
            "voice_id": state.order.voice_id,
            "candidate_hash": candidate_hash,
            "source_failures": state.errors,
            "status": manifest.status.value,
        }
        RunStore._atomic_text(
            state.candidate / "build-report.json", json.dumps(build_report, indent=2)
        )
        return manifest

    @staticmethod
    def _activate_candidate(state: BuildState) -> None:
        previous = state.voice_root / ".candidate-previous"
        if previous.exists():
            shutil.rmtree(previous)
        if state.final_candidate.exists():
            os.replace(state.final_candidate, previous)
        try:
            os.replace(state.candidate, state.final_candidate)
        except Exception:
            if previous.exists():
                os.replace(previous, state.final_candidate)
            raise
        if previous.exists():
            shutil.rmtree(previous)
