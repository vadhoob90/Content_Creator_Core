"""Provide corpus capabilities."""

from __future__ import annotations

from collections import Counter

from ..linguistics import build_linguistic_signature
from ..voices import SourceRecord
from .models import BuildState, VoiceBuildError, even_sample
from .renderer import VoiceProfileRenderer


def assess_corpus(records: list[SourceRecord], intended_packs: list[str]) -> dict:
    """Assess the corpus workflow.

    Args:
        records (list[SourceRecord]): The ordered persisted records to process.
        intended_packs (list[str]): The intended packs collection consumed while assess
            corpus.

    Returns:
        dict: The assessment dict for corpus.
    """
    usable = [record for record in records if record.approved_for_analysis]
    words = sum(record.analysis_word_count or record.word_count for record in usable)
    weighted_words = round(
        sum(
            (record.analysis_word_count or record.word_count) * record.attribution.voice_weight
            for record in usable
        )
    )
    kinds = Counter(record.kind for record in usable)
    direct = sum(record.attribution.classification == "directly_authored" for record in usable)
    confidence = (
        "high"
        if direct >= 3 and weighted_words >= 3000
        else "medium"
        if weighted_words >= 500
        else "low"
    )
    gaps = []
    if not usable:
        gaps.append("Resolve attribution or add directly authored material.")
    if weighted_words < 500:
        gaps.append("Add at least 500 attribution-weighted words of representative material.")
    if len(kinds) < 2:
        gaps.append("Add another content type or channel to test transfer.")
    return {
        "usable_source_count": len(usable),
        "usable_word_count": words,
        "attribution_weighted_word_count": weighted_words,
        "direct_authorship_count": direct,
        "content_types": dict(kinds),
        "supported_packs": {pack: confidence for pack in intended_packs},
        "gaps": gaps,
        "sufficient": bool(usable) and weighted_words >= 500,
    }


def analyse_corpus(
    state: BuildState,
    renderer: VoiceProfileRenderer,
    allow_insufficient_delta: bool = False,
) -> None:
    """Prepare corpus sufficiency, holdout, measurement, and signature evidence.

    Args:
        state (BuildState): Mutable voice-build state.
        renderer (VoiceProfileRenderer): Renderer that converts measurements into patterns.
        allow_insufficient_delta (bool): Permit a baseline-backed delta below initial
            corpus thresholds. Defaults to ``False``.

    Returns:
        None: Corpus and analysis fields are updated in place.

    Raises:
        VoiceBuildError: If a rebuild would replace a candidate with insufficient evidence.
    """
    state.corpus = assess_corpus(state.sources, state.order.authorisation.intended_uses)
    if (
        state.final_candidate.exists()
        and not state.corpus["sufficient"]
        and not allow_insufficient_delta
    ):
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
    state.patterns = renderer.patterns(state.analysis_records, state.signature)
