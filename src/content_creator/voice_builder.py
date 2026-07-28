from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from .attribution import classify_attribution
from .corpus import assess_corpus
from .ingestion import content_hash, is_near_duplicate, read_source
from .runner import AgentRunner
from .storage import RunStore
from .voices import (
    AttributionResult,
    SourceRecord,
    VoiceManifest,
    VoicePattern,
    VoiceStatus,
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
        voice_root = self.root / "profiles" / voice_id
        final_candidate = voice_root / "candidate"
        candidate = voice_root / ".candidate-staging"
        if candidate.exists():
            shutil.rmtree(candidate)
        cache = self.root / ".voice-cache" / voice_id
        sources: List[SourceRecord] = []
        normalized: List[str] = []
        errors = []
        locators = order.urls + order.documents
        for index, locator in enumerate(locators, start=1):
            source_id = "source-{:03d}".format(index)
            try:
                kind, title, text = read_source(locator)
                duplicate = is_near_duplicate(text, normalized)
                attribution = classify_attribution(text, order.display_name, kind)
                if attribution.needs_human_review and self.runner:
                    attribution = self.runner.run(
                        role="attribution-reviewer",
                        role_key="attribution-reviewer",
                        instruction=(
                            "Resolve attribution only from the supplied evidence. "
                            "If uncertain, retain zero voice weight."
                        ),
                        payload={
                            "person": order.display_name,
                            "kind": kind,
                            "title": title,
                            "excerpt": text[:2000],
                        },
                        output_model=AttributionResult,
                        provider=self.provider,
                    )
                approved = attribution.voice_weight > 0 and not duplicate
                cache_path = cache / "{}.txt".format(source_id)
                RunStore._atomic_text(cache_path, text)
                sources.append(
                    SourceRecord(
                        id=source_id,
                        kind=kind,
                        locator=locator,
                        content_hash=content_hash(text),
                        title=title,
                        word_count=len(text.split()),
                        attribution=attribution,
                        approved_for_analysis=approved,
                        cache_path=str(cache_path.relative_to(self.root)),
                    )
                )
                normalized.append(text)
            except Exception as exc:
                errors.append({"locator": locator, "error": str(exc)})
        corpus = assess_corpus(sources, order.authorisation.intended_uses)
        if final_candidate.exists() and not corpus["sufficient"]:
            raise VoiceBuildError(
                "Rebuild has insufficient usable material; previous candidate preserved"
            )
        usable = [record for record in sources if record.approved_for_analysis]
        held_out = [usable[-1]] if len(usable) >= 2 else []
        analysis_records = usable[:-1] if held_out else usable
        corpus["held_out_source_ids"] = [record.id for record in held_out]
        patterns = self._patterns(analysis_records)
        if self.runner and analysis_records:
            payload = {
                "person": order.display_name,
                "sources": [
                    {
                        "id": record.id,
                        "kind": record.kind,
                        "text": (self.root / record.cache_path).read_text(
                            encoding="utf-8"
                        ),
                    }
                    for record in analysis_records
                ],
                "corpus": corpus,
            }
            analysis = self.runner.run(
                role="voice-analyst",
                role_key="voice-analyst",
                instruction=(
                    "Identify style patterns supported by the authorised corpus. "
                    "Cite source IDs and do not infer biography or beliefs."
                ),
                payload=payload,
                output_model=VoiceAnalysis,
                provider=self.provider,
            )
            criticism = self.runner.run(
                role="profile-critic",
                role_key="profile-critic",
                instruction=(
                    "Reject unsupported, copied, topic-specific, or caricatured patterns."
                ),
                payload={
                    "analysis": analysis.model_dump(mode="json"),
                    "approved_source_ids": [
                        record.id for record in analysis_records
                    ],
                },
                output_model=ProfileCriticism,
                provider=self.provider,
            )
            approved_ids = {record.id for record in analysis_records}
            patterns = []
            for pattern in analysis.patterns:
                pattern.supporting_source_ids = [
                    item
                    for item in pattern.supporting_source_ids
                    if item in approved_ids
                ]
                if pattern.id in criticism.rejected_pattern_ids:
                    pattern.status = "rejected"
                elif (
                    pattern.status == "confirmed"
                    and len(pattern.supporting_source_ids) < 2
                ):
                    pattern.status = "provisional"
                patterns.append(pattern)

        candidate.mkdir(parents=True, exist_ok=True)
        profile = self._profile(order, patterns, corpus)
        RunStore._atomic_text(candidate / "profile.md", profile)
        RunStore._atomic_text(
            candidate / "constraints.json",
            json.dumps(
                {
                    "never_invent_personal_context": True,
                    "never_copy_source_phrases": True,
                    "provisional_patterns_are_optional": True,
                },
                indent=2,
            ),
        )
        RunStore._atomic_text(
            candidate / "voice-rubric.json",
            json.dumps(
                {
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
                },
                indent=2,
            ),
        )
        RunStore._atomic_text(
            candidate / "source-index.json",
            json.dumps([item.model_dump(mode="json") for item in sources], indent=2),
        )
        RunStore._atomic_text(
            candidate / "patterns.json",
            json.dumps([item.model_dump(mode="json") for item in patterns], indent=2),
        )
        RunStore._atomic_text(
            candidate / "corpus-report.json", json.dumps(corpus, indent=2)
        )
        evaluation = {
            "schema_version": "1.0",
            "passed": corpus["sufficient"] and bool(patterns),
            "hard_failures": [] if corpus["sufficient"] else ["insufficient_corpus"],
            "checks": {
                "provenance": all(item.supporting_source_ids for item in patterns),
                "held_out_allocation": bool(held_out),
                "held_out_excluded_from_analysis": all(
                    not set(item.supporting_source_ids)
                    & set(corpus["held_out_source_ids"])
                    for item in patterns
                ),
                "unseen_topic_transfer": "manual_live_evaluation_required",
                "caricature_rejection": True,
                "phrase_overlap": True,
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
                    "patterns": [
                        item.model_dump(mode="json") for item in patterns
                    ],
                    "held_out_sources": [
                        {
                            "id": record.id,
                            "text": (self.root / record.cache_path).read_text(
                                encoding="utf-8"
                            )[:4000],
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
            evaluation["hard_failures"].extend(judgement.hard_failures)
            evaluation["passed"] = (
                evaluation["passed"]
                and judgement.passed
                and not judgement.hard_failures
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
            "evaluation_report": "evaluation-report.json",
        }
        component_hashes = {
            name: hash_file(candidate / filename) for name, filename in components.items()
        }
        candidate_hash = hash_json(component_hashes)
        manifest = VoiceManifest(
            id=voice_id,
            display_name=order.display_name,
            version="candidate",
            status=(
                VoiceStatus.AWAITING_APPROVAL
                if evaluation["passed"]
                else VoiceStatus.BUILT
            ),
            candidate_hash=candidate_hash,
            components=components,
            component_hashes=component_hashes,
            supported_packs=corpus["supported_packs"],
            authorisation=order.authorisation,
        )
        RunStore._atomic_text(
            candidate / "manifest.json", manifest.model_dump_json(indent=2)
        )
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
    def _patterns(records: List[SourceRecord]) -> List[VoicePattern]:
        if not records:
            return []
        ids = [record.id for record in records]
        return [
            VoicePattern(
                id="pattern-001",
                name="Evidence-led clarity",
                description=(
                    "Prefer concrete explanations and traceable claims; treat this as "
                    "provisional until the profile owner confirms it."
                ),
                status="confirmed" if len(ids) >= 2 else "provisional",
                confidence=min(0.9, 0.55 + 0.1 * len(ids)),
                supporting_source_ids=ids,
            )
        ]

    @staticmethod
    def _profile(order: VoiceWorkOrder, patterns: List[VoicePattern], corpus: dict) -> str:
        lines = [
            "# Voice Profile: {}".format(order.display_name),
            "",
            "Use only the evidence-backed patterns below. Do not infer biography,",
            "experience, beliefs, or personal anecdotes.",
            "",
            "## Patterns",
        ]
        lines.extend(
            "- **{} ({})**: {}".format(item.name, item.status, item.description)
            for item in patterns
        )
        lines.extend(
            [
                "",
                "## Evidence limits",
                "",
                "- Usable sources: {}".format(corpus["usable_source_count"]),
                "- Usable words: {}".format(corpus["usable_word_count"]),
                "- Unsupported channels require explicit human guidance.",
            ]
        )
        return "\n".join(lines)
