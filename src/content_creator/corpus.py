"""Provide corpus capabilities."""

from __future__ import annotations

from collections import Counter

from .voices import SourceRecord


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
