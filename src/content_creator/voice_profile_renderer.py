from __future__ import annotations

from typing import Dict, List

from .voices import SourceRecord, VoicePattern, VoiceWorkOrder


class VoiceProfileRenderer:
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
        lines = VoiceProfileRenderer._profile_header(order, patterns, corpus)
        status_counts: Dict[str, int] = {}
        for item in patterns:
            status_counts[item.status] = status_counts.get(item.status, 0) + 1
        lines.extend(
            "- **{}:** {}".format(status.replace("_", " ").title(), count)
            for status, count in sorted(status_counts.items())
        )
        if not status_counts:
            lines.append("- No patterns were proposed.")
        lines.extend(["", "## Patterns for human review", ""])
        VoiceProfileRenderer._append_patterns(lines, patterns)
        lines.extend(VoiceProfileRenderer._evidence_limits(corpus))
        return "\n".join(lines)

    @staticmethod
    def _profile_header(
        order: VoiceWorkOrder,
        patterns: List[VoicePattern],
        corpus: dict,
    ) -> list[str]:
        return [
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

    @staticmethod
    def _append_patterns(lines: list[str], patterns: List[VoicePattern]) -> None:
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

    @staticmethod
    def _evidence_limits(corpus: dict) -> list[str]:
        return [
            "## Evidence limits",
            "",
            "- Usable sources: {:,}".format(corpus["usable_source_count"]),
            "- Usable words: {:,}".format(corpus["usable_word_count"]),
            "- Attribution-weighted words: {:,}".format(corpus["attribution_weighted_word_count"]),
            "- Semantic analysis sources: {}".format(
                len(corpus.get("semantic_analysis_source_ids", []))
            ),
            "- Held-out evaluation sources: {}".format(len(corpus.get("held_out_source_ids", []))),
            "- Unsupported channels require explicit human guidance.",
            "- Without a matched-register baseline, observed features must not be",
            "  described as distinctive to the person.",
        ]
