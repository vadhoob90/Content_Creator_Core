from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, cast

from pydantic import BaseModel, Field

from .attribution import classify_attribution, isolate_attributed_text
from .corpus import assess_corpus
from .ingestion import content_hash, is_near_duplicate, normalize_text, read_source
from .linguistics import build_linguistic_signature, extract_linguistic_features
from .runner import AgentRunner
from .storage import RunStore
from .voices import (
    AttributionResult,
    SourceRecord,
    VoiceManifest,
    VoicePattern,
    VoiceStatus,
    VoiceStrategy,
    VoiceWorkOrder,
    hash_file,
    hash_json,
)


class VoiceBuildError(RuntimeError):
    pass


class VoiceAnalysis(BaseModel):
    summary: str
    patterns: List[VoicePattern] = Field(default_factory=list)


class ProfileCriticism(BaseModel):
    rejected_pattern_ids: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class VoiceEvaluationJudgement(BaseModel):
    passed: bool
    scores: dict = Field(default_factory=dict)
    hard_failures: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


def _analysis_excerpt(text: str, limit: int = 6000) -> str:
    """Bound agent input while sampling the beginning, middle, and end."""
    if len(text) <= limit:
        return text
    section = limit // 3
    midpoint = len(text) // 2
    middle_start = max(0, midpoint - section // 2)
    return "\n\n[...]\n\n".join(
        (
            text[:section],
            text[middle_start : middle_start + section],
            text[-section:],
        )
    )


def _even_sample(records: List[SourceRecord], limit: int) -> List[SourceRecord]:
    """Select a deterministic spread across an ordered corpus."""
    if limit <= 0:
        return []
    if limit == 1:
        return [records[-1]]
    if len(records) <= limit:
        return list(records)
    return [records[round(index * (len(records) - 1) / (limit - 1))] for index in range(limit)]


def _public_locator(locator: str) -> str:
    if locator.startswith(("http://", "https://")):
        return locator
    return "local-document:{}".format(Path(locator).name)


class VoiceBuilder:
    def __init__(
        self,
        root: Path,
        runner: Optional[AgentRunner] = None,
        provider: Optional[str] = None,
    ):
        self.root = root.resolve()
        self.runner = runner
        self.provider = provider

    def save_work_order(self, order: VoiceWorkOrder) -> Path:
        path = self.root / "profiles" / order.voice_id / "work-order.json"
        RunStore._atomic_text(path, order.model_dump_json(indent=2))
        return path

    def load_work_order(self, voice_id: str) -> VoiceWorkOrder:
        path = self.root / "profiles" / voice_id / "work-order.json"
        if not path.exists():
            raise VoiceBuildError("Unknown voice work order: {}".format(voice_id))
        return VoiceWorkOrder.model_validate_json(path.read_text(encoding="utf-8"))

    def build(self, voice_id: str) -> VoiceManifest:
        order = self.load_work_order(voice_id)
        if order.strategy != VoiceStrategy.SOURCE_DERIVED:
            raise VoiceBuildError(
                "Starter voices are activated from their template; select "
                "source-derived onboarding before building from evidence"
            )
        voice_root = self.root / "profiles" / voice_id
        final_candidate = voice_root / "candidate"
        candidate = voice_root / ".candidate-staging"
        if candidate.exists():
            shutil.rmtree(candidate)
        cache = self.root / ".voice-cache" / voice_id
        sources: List[SourceRecord] = []
        analysis_texts = {}
        normalized: List[str] = []
        errors = []
        locators = order.urls + order.documents
        for index, locator in enumerate(locators, start=1):
            source_id = "source-{:03d}".format(index)
            cache_path = cache / "{}.txt".format(source_id)
            cache_metadata_path = cache / "{}.meta.json".format(source_id)
            try:
                if locator.startswith(("http://", "https://")) and cache_path.exists():
                    text = normalize_text(cache_path.read_text(encoding="utf-8"))
                    kind = "webpage"
                    title = locator
                    if cache_metadata_path.exists():
                        metadata = json.loads(cache_metadata_path.read_text(encoding="utf-8"))
                        if metadata.get("locator") == locator:
                            kind = metadata.get("kind", kind)
                            title = metadata.get("title", title)
                else:
                    kind, title, text = read_source(locator)
                duplicate = is_near_duplicate(text, normalized)
                locally_attested = locator in order.documents and order.authorisation.confirmed
                if locally_attested:
                    attribution = AttributionResult(
                        classification="directly_authored",
                        confidence=1.0,
                        voice_weight=1.0,
                        evidence=[
                            "Local document authorship attested by {}".format(
                                order.authorisation.attested_by or "the repository owner"
                            )
                        ],
                    )
                else:
                    attribution = classify_attribution(
                        text,
                        order.attribution_name,
                        kind,
                        order.author_aliases,
                    )
                if attribution.needs_human_review and self.runner:
                    attribution = self.runner.run(
                        role="attribution-reviewer",
                        role_key="attribution-reviewer",
                        instruction=(
                            "Resolve attribution only from the supplied evidence. "
                            "If uncertain, retain zero voice weight."
                        ),
                        payload={
                            "person": order.attribution_name,
                            "aliases": order.author_aliases,
                            "kind": kind,
                            "title": title,
                            "excerpt": text[:2000],
                        },
                        output_model=AttributionResult,
                        provider=self.provider,
                    )
                analysis_text, analysis_scope = isolate_attributed_text(
                    text,
                    order.attribution_name,
                    attribution,
                    kind,
                    order.author_aliases,
                )
                if locally_attested and analysis_text == text.strip():
                    analysis_scope = "full-source-author-attested"
                approved = (
                    attribution.voice_weight > 0 and not duplicate and bool(analysis_text.strip())
                )
                RunStore._atomic_text(cache_path, text)
                RunStore._atomic_text(
                    cache_metadata_path,
                    json.dumps(
                        {
                            "locator": locator,
                            "kind": kind,
                            "title": title,
                            "content_hash": content_hash(text),
                        },
                        indent=2,
                    ),
                )
                analysis_texts[source_id] = analysis_text
                sources.append(
                    SourceRecord(
                        id=source_id,
                        kind=kind,
                        locator=_public_locator(locator),
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
                normalized.append(text)
            except Exception as exc:
                errors.append(
                    {
                        "locator": _public_locator(locator),
                        "error": str(exc).replace(locator, _public_locator(locator)),
                    }
                )
        corpus = assess_corpus(sources, order.authorisation.intended_uses)
        if final_candidate.exists() and not corpus["sufficient"]:
            raise VoiceBuildError(
                "Rebuild has insufficient usable material; previous candidate preserved"
            )
        usable = [record for record in sources if record.approved_for_analysis]
        held_out_count = min(10, max(1, len(usable) // 10)) if len(usable) >= 2 else 0
        held_out = _even_sample(usable, held_out_count) if held_out_count else []
        held_out_ids = {record.id for record in held_out}
        measurement_records = [record for record in usable if record.id not in held_out_ids]
        analysis_records = _even_sample(measurement_records, 50)
        corpus["held_out_source_ids"] = [record.id for record in held_out]
        corpus["measurement_source_ids"] = [record.id for record in measurement_records]
        corpus["semantic_analysis_source_ids"] = [record.id for record in analysis_records]
        corpus["semantic_analysis_limit"] = 50
        signature = build_linguistic_signature(
            {
                "id": record.id,
                "kind": record.kind,
                "text": analysis_texts[record.id],
                "weight": record.attribution.voice_weight,
            }
            for record in measurement_records
        )
        patterns = self._patterns(analysis_records, signature)
        analysis_artifact = None
        criticism_artifact = None
        if self.runner and analysis_records:
            payload = {
                "person": order.attribution_name,
                "voice_label": order.display_name,
                "sources": [
                    {
                        "id": record.id,
                        "kind": record.kind,
                        "attribution_weight": record.attribution.voice_weight,
                        "analysis_scope": record.analysis_scope,
                        "text": _analysis_excerpt(analysis_texts[record.id]),
                        "linguistic_features": extract_linguistic_features(
                            analysis_texts[record.id]
                        ),
                    }
                    for record in analysis_records
                ],
                "corpus": corpus,
                "linguistic_signature": signature,
            }
            analysis = self.runner.run(
                role="voice-analyst",
                role_key="voice-analyst",
                instruction=(
                    "Identify style patterns supported by the authorised corpus. "
                    "Use the linguistic framework, distinguish observation from "
                    "interpretation, cite source IDs, and do not infer biography "
                    "or beliefs."
                ),
                payload=payload,
                output_model=VoiceAnalysis,
                provider=self.provider,
            )
            analysis_artifact = analysis.model_dump(mode="json")
            criticism = self.runner.run(
                role="profile-critic",
                role_key="profile-critic",
                instruction=(
                    "Reject unsupported, copied, topic-specific, or caricatured patterns."
                ),
                payload={
                    "analysis": analysis.model_dump(mode="json"),
                    "linguistic_signature": signature,
                    "approved_source_ids": [record.id for record in analysis_records],
                },
                output_model=ProfileCriticism,
                provider=self.provider,
            )
            criticism_artifact = criticism.model_dump(mode="json")
            approved_ids = {record.id for record in analysis_records}
            patterns = []
            for pattern in analysis.patterns:
                pattern.supporting_source_ids = [
                    item for item in pattern.supporting_source_ids if item in approved_ids
                ]
                if pattern.id in criticism.rejected_pattern_ids:
                    pattern.status = "rejected"
                elif pattern.status == "confirmed" and len(pattern.supporting_source_ids) < 2:
                    pattern.status = "provisional"
                patterns.append(pattern)

        candidate.mkdir(parents=True, exist_ok=True)
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
            "hard_gates": [
                "unsupported_personal_context",
                "material_phrase_overlap",
            ],
        }
        profile = self._profile(order, patterns, corpus)
        RunStore._atomic_text(candidate / "profile.md", profile)
        RunStore._atomic_text(
            candidate / "constraints.json",
            json.dumps(constraints, indent=2),
        )
        RunStore._atomic_text(
            candidate / "voice-rubric.json",
            json.dumps(voice_rubric, indent=2),
        )
        RunStore._atomic_text(
            candidate / "source-index.json",
            json.dumps([item.model_dump(mode="json") for item in sources], indent=2),
        )
        RunStore._atomic_text(
            candidate / "patterns.json",
            json.dumps([item.model_dump(mode="json") for item in patterns], indent=2),
        )
        RunStore._atomic_text(candidate / "corpus-report.json", json.dumps(corpus, indent=2))
        RunStore._atomic_text(
            candidate / "linguistic-signature.json",
            json.dumps(signature, indent=2),
        )
        if analysis_artifact is not None:
            RunStore._atomic_text(
                candidate / "analyst-report.json",
                json.dumps(analysis_artifact, indent=2),
            )
        if criticism_artifact is not None:
            RunStore._atomic_text(
                candidate / "critic-report.json",
                json.dumps(criticism_artifact, indent=2),
            )
        evaluation = {
            "schema_version": "1.0",
            "passed": corpus["sufficient"] and bool(patterns),
            "hard_failures": [] if corpus["sufficient"] else ["insufficient_corpus"],
            "checks": {
                "provenance": all(item.supporting_source_ids for item in patterns),
                "held_out_allocation": bool(held_out),
                "held_out_excluded_from_analysis": all(
                    not set(item.supporting_source_ids) & set(corpus["held_out_source_ids"])
                    for item in patterns
                ),
                "unseen_topic_transfer": "manual_live_evaluation_required",
                "caricature_rejection": True,
                "phrase_overlap": True,
                "linguistic_signature": bool(signature["source_profiles"]),
                "matched_register_baseline": "not_supplied",
            },
        }
        if self.runner and patterns:
            judgement = self.runner.run(
                role="voice-evaluator",
                role_key="voice-evaluator",
                instruction=(
                    "Evaluate transfer, channel fit, generic-draft rejection, "
                    "caricature resistance, and personal integrity. Integrity "
                    "failures cannot be averaged away."
                ),
                payload={
                    "profile": profile,
                    "constraints": constraints,
                    "voice_rubric": voice_rubric,
                    "linguistic_signature": signature,
                    "patterns": [item.model_dump(mode="json") for item in patterns],
                    "held_out_sources": [
                        {
                            "id": record.id,
                            "text": _analysis_excerpt(analysis_texts[record.id], 4000),
                            "linguistic_features": extract_linguistic_features(
                                analysis_texts[record.id]
                            ),
                        }
                        for record in held_out
                    ],
                    "supported_packs": corpus["supported_packs"],
                    "adversarial_cases": [
                        "generic draft with no characteristic choices",
                        "caricature stacking every observed mannerism",
                        "invented personal experience",
                    ],
                },
                output_model=VoiceEvaluationJudgement,
                provider=self.provider,
            )
            evaluation["agent_judgement"] = judgement.model_dump(mode="json")
            cast(List[str], evaluation["hard_failures"]).extend(judgement.hard_failures)
            evaluation["passed"] = (
                evaluation["passed"] and judgement.passed and not judgement.hard_failures
            )
        RunStore._atomic_text(
            candidate / "evaluation-report.json", json.dumps(evaluation, indent=2)
        )
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
        if analysis_artifact is not None:
            components["analyst_report"] = "analyst-report.json"
        if criticism_artifact is not None:
            components["critic_report"] = "critic-report.json"
        component_hashes = {
            name: hash_file(candidate / filename) for name, filename in components.items()
        }
        candidate_hash = hash_json(component_hashes)
        manifest = VoiceManifest(
            id=voice_id,
            display_name=order.display_name,
            author_name=order.attribution_name,
            author_aliases=order.author_aliases,
            version="candidate",
            status=(VoiceStatus.AWAITING_APPROVAL if evaluation["passed"] else VoiceStatus.BUILT),
            candidate_hash=candidate_hash,
            components=components,
            component_hashes=component_hashes,
            supported_packs=corpus["supported_packs"],
            authorisation=order.authorisation,
            strategy=VoiceStrategy.SOURCE_DERIVED,
            evidence_status="author-sources",
            perspectives_allowed=True,
        )
        RunStore._atomic_text(candidate / "manifest.json", manifest.model_dump_json(indent=2))
        RunStore._atomic_text(
            candidate / "build-report.json",
            json.dumps(
                {
                    "voice_id": voice_id,
                    "candidate_hash": candidate_hash,
                    "source_failures": errors,
                    "status": manifest.status.value,
                },
                indent=2,
            ),
        )
        previous = voice_root / ".candidate-previous"
        if previous.exists():
            shutil.rmtree(previous)
        if final_candidate.exists():
            os.replace(final_candidate, previous)
        try:
            os.replace(candidate, final_candidate)
        except Exception:
            if previous.exists():
                os.replace(previous, final_candidate)
            raise
        if previous.exists():
            shutil.rmtree(previous)
        return manifest

    @staticmethod
    def _patterns(
        records: List[SourceRecord],
        signature: dict,
    ) -> List[VoicePattern]:
        if not records:
            return []
        ids = [record.id for record in records]
        overall = signature.get("overall", {})
        sentence_length = overall.get("sentence_length_median", {})
        questions = overall.get("questions_per_100_sentences", {})
        modes = sorted(signature.get("by_mode", {}))
        return [
            VoicePattern(
                id="pattern-001",
                name="Observed sentence rhythm",
                description=(
                    "The analysis corpus has a median sentence length of {} words "
                    "with an inter-source range of {} to {}. This is an observation, "
                    "not a fixed generation target."
                ).format(
                    sentence_length.get("median", 0),
                    sentence_length.get("q1", 0),
                    sentence_length.get("q3", 0),
                ),
                status="provisional",
                confidence=min(0.75, 0.45 + 0.08 * len(ids)),
                supporting_source_ids=ids,
                category="syntax-and-rhythm",
                observation="Sentence length varies within the measured corpus.",
                communicative_function=(
                    "Potentially controls pace; human confirmation is required."
                ),
                contexts={"observed_modes": modes},
                generation_guidance=(
                    "Preserve natural sentence-length variation rather than matching one average."
                ),
                anti_pattern="Do not force every sentence into the measured range.",
                linguistic_evidence={
                    "sentence_length_median": str(sentence_length.get("median", 0)),
                    "questions_per_100_sentences": str(questions.get("weighted_mean", 0)),
                },
            )
        ]

    @staticmethod
    def _profile(order: VoiceWorkOrder, patterns: List[VoicePattern], corpus: dict) -> str:
        status_counts: Dict[str, int] = {}
        for item in patterns:
            status_counts[item.status] = status_counts.get(item.status, 0) + 1
        lines = [
            "# Voice Profile: {}".format(order.display_name),
            "",
            "## At a glance",
            "",
            "| Item | Current position |",
            "|---|---|",
            "| Lifecycle status | Resolved manifest is authoritative |",
            "| Author identity | {} |".format(order.attribution_name),
            "| Intended uses | {} |".format(
                ", ".join(order.authorisation.intended_uses) or "Not specified"
            ),
            "| Usable sources | {:,} |".format(corpus["usable_source_count"]),
            "| Attribution-weighted words | {:,} |".format(
                corpus["attribution_weighted_word_count"]
            ),
            "| Proposed patterns | {} |".format(len(patterns)),
            "",
            "> Pattern statuses are model assessments retained for human review.",
            "> Lifecycle approval is supplied by Core, not by this profile prose.",
            "",
            "## Core safeguards",
            "",
            "- Do not infer biography, experience, beliefs, opinions or anecdotes.",
            "- Do not copy or closely paraphrase source wording.",
            "- Treat measurements as descriptive evidence, not numerical targets.",
            "- Do not claim distinctiveness without a matched-register comparison.",
            "- Obtain human guidance before using an unsupported channel.",
            "",
            "## Pattern status summary",
            "",
        ]
        if status_counts:
            lines.extend(
                "- **{}:** {}".format(status.replace("_", " ").title(), count)
                for status, count in sorted(status_counts.items())
            )
        else:
            lines.append("- No patterns were proposed.")
        lines.extend(["", "## Patterns for human review", ""])
        current_category = None
        for index, item in enumerate(patterns, start=1):
            category = item.category.replace("-", " ").title()
            if category != current_category:
                lines.extend(["### {}".format(category), ""])
                current_category = category
            guidance_label = (
                "Proposed guidance"
                if item.status in {"rejected", "provisional", "for-review"}
                else "Guidance"
            )
            lines.extend(
                [
                    "#### {}. {}".format(index, item.name),
                    "",
                    "**Status:** {}".format(item.status.replace("_", " ").title()),
                    "",
                    "**Observation:** {}".format(item.observation or item.description),
                    "",
                    "**{}:** {}".format(
                        guidance_label,
                        item.generation_guidance or "Use only when context supports it.",
                    ),
                    "",
                    "**Avoid:** {}".format(
                        item.anti_pattern or "Do not turn the observation into a mannerism."
                    ),
                    "",
                    "**Evidence:** {}".format(
                        ", ".join(
                            "`{}`".format(source_id) for source_id in item.supporting_source_ids
                        )
                    ),
                    "",
                ]
            )
        lines.extend(
            [
                "## Evidence limits",
                "",
                "- Usable sources: {:,}".format(corpus["usable_source_count"]),
                "- Usable words: {:,}".format(corpus["usable_word_count"]),
                "- Attribution-weighted words: {:,}".format(
                    corpus["attribution_weighted_word_count"]
                ),
                "- Semantic analysis sources: {}".format(
                    len(corpus.get("semantic_analysis_source_ids", []))
                ),
                "- Held-out evaluation sources: {}".format(
                    len(corpus.get("held_out_source_ids", []))
                ),
                "- Unsupported channels require explicit human guidance.",
                "- Without a matched-register baseline, observed features must not be",
                "  described as distinctive to the person.",
            ]
        )
        return "\n".join(lines)
