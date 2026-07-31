from __future__ import annotations

import math
import re
from collections import defaultdict
from statistics import median, pstdev
from typing import Dict, Iterable, List

FRAMEWORK_VERSION = "1.0"

_WORD_RE = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?")
_SENTENCE_RE = re.compile(r"(?<=[.!?])(?:[\"'’”)]*)\s+")
_CONTRACTION_RE = re.compile(r"\b(?:[A-Za-z]+(?:n't|'re|'ve|'ll|'d|'m|'s))\b", re.I)

_FIRST_PERSON = {"i", "me", "my", "mine", "we", "us", "our", "ours"}
_SECOND_PERSON = {"you", "your", "yours"}
_MODALS = {
    "can",
    "could",
    "may",
    "might",
    "must",
    "shall",
    "should",
    "will",
    "would",
}
_HEDGES = {
    "apparently",
    "approximately",
    "generally",
    "likely",
    "maybe",
    "often",
    "perhaps",
    "possibly",
    "probably",
    "seem",
    "seems",
    "sometimes",
    "typically",
}
_BOOSTERS = {
    "always",
    "certainly",
    "clearly",
    "definitely",
    "essential",
    "must",
    "never",
    "obviously",
    "undoubtedly",
}
_CONTRAST_MARKERS = {
    "although",
    "but",
    "however",
    "instead",
    "nevertheless",
    "rather",
    "whereas",
    "yet",
}
_EXAMPLE_MARKERS = {
    "example",
    "instance",
    "specifically",
}
_CONCLUSION_MARKERS = {
    "conclusion",
    "finally",
    "overall",
    "therefore",
    "ultimately",
}


def _round(value: float) -> float:
    return round(float(value), 4)


def _rate(count: int, total: int, scale: int) -> float:
    return _round((count / total) * scale) if total else 0.0


def _percentile(values: List[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return _round(ordered[lower])
    distance = position - lower
    return _round(ordered[lower] + (ordered[upper] - ordered[lower]) * distance)


def _mattr(tokens: List[str], window: int = 50) -> float:
    if not tokens:
        return 0.0
    if len(tokens) <= window:
        return _round(len(set(tokens)) / len(tokens))
    scores = [
        len(set(tokens[index : index + window])) / window
        for index in range(len(tokens) - window + 1)
    ]
    return _round(sum(scores) / len(scores))


def _sentences(text: str) -> List[str]:
    return [item.strip() for item in _SENTENCE_RE.split(text.strip()) if _WORD_RE.search(item)]


def extract_linguistic_features(text: str) -> Dict[str, float]:
    """Return transparent descriptive features, not an authorship judgement."""

    words = [item.lower().replace("’", "'") for item in _WORD_RE.findall(text)]
    sentences = _sentences(text)
    sentence_lengths = [len(_WORD_RE.findall(item)) for item in sentences]
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", text) if _WORD_RE.search(item)]
    paragraph_lengths = [len(_WORD_RE.findall(item)) for item in paragraphs]
    word_count = len(words)
    sentence_count = len(sentences)

    return {
        "word_count": float(word_count),
        "sentence_count": float(sentence_count),
        "paragraph_count": float(len(paragraphs)),
        "sentence_length_median": _round(median(sentence_lengths)) if sentence_lengths else 0.0,
        "sentence_length_q1": _percentile(sentence_lengths, 0.25),
        "sentence_length_q3": _percentile(sentence_lengths, 0.75),
        "sentence_length_variation": _round(pstdev(sentence_lengths))
        if len(sentence_lengths) > 1
        else 0.0,
        "short_sentence_ratio": _rate(
            sum(length <= 8 for length in sentence_lengths), sentence_count, 1
        ),
        "long_sentence_ratio": _rate(
            sum(length >= 25 for length in sentence_lengths), sentence_count, 1
        ),
        "paragraph_length_median": _round(median(paragraph_lengths)) if paragraph_lengths else 0.0,
        "questions_per_100_sentences": _rate(text.count("?"), sentence_count, 100),
        "exclamations_per_100_sentences": _rate(text.count("!"), sentence_count, 100),
        "first_person_per_1000_words": _rate(
            sum(word in _FIRST_PERSON for word in words), word_count, 1000
        ),
        "second_person_per_1000_words": _rate(
            sum(word in _SECOND_PERSON for word in words), word_count, 1000
        ),
        "modals_per_1000_words": _rate(sum(word in _MODALS for word in words), word_count, 1000),
        "hedges_per_1000_words": _rate(sum(word in _HEDGES for word in words), word_count, 1000),
        "boosters_per_1000_words": _rate(
            sum(word in _BOOSTERS for word in words), word_count, 1000
        ),
        "contractions_per_1000_words": _rate(
            len(_CONTRACTION_RE.findall(text.replace("’", "'"))), word_count, 1000
        ),
        "contrast_markers_per_1000_words": _rate(
            sum(word in _CONTRAST_MARKERS for word in words), word_count, 1000
        ),
        "example_markers_per_1000_words": _rate(
            sum(word in _EXAMPLE_MARKERS for word in words), word_count, 1000
        ),
        "conclusion_markers_per_1000_words": _rate(
            sum(word in _CONCLUSION_MARKERS for word in words), word_count, 1000
        ),
        "dashes_per_1000_words": _rate(text.count("—") + text.count("–"), word_count, 1000),
        "semicolons_per_1000_words": _rate(text.count(";"), word_count, 1000),
        "colons_per_1000_words": _rate(text.count(":"), word_count, 1000),
        "lexical_diversity_mattr": _mattr(words),
    }


def linguistic_context(kind: str) -> Dict[str, str]:
    mode = "spoken" if kind == "transcript" else "written"
    return {"mode": mode, "source_kind": kind}


def _aggregate(items: Iterable[Dict]) -> Dict[str, Dict[str, float]]:
    profiles = list(items)
    if not profiles:
        return {}
    metric_names = profiles[0]["features"].keys()
    result = {}
    for name in metric_names:
        values = [float(item["features"][name]) for item in profiles]
        weights = [max(float(item.get("weight", 1.0)), 0.0) for item in profiles]
        denominator = sum(weights)
        weighted_mean = (
            sum(value * weight for value, weight in zip(values, weights, strict=True))
            if denominator
            else sum(values) / len(values)
        )
        result[name] = {
            "weighted_mean": _round(weighted_mean),
            "median": _round(median(values)),
            "q1": _percentile(values, 0.25),
            "q3": _percentile(values, 0.75),
            "min": _round(min(values)),
            "max": _round(max(values)),
        }
    return result


def build_linguistic_signature(sources: Iterable[Dict]) -> Dict:
    source_profiles = []
    for source in sources:
        context = linguistic_context(source["kind"])
        source_profiles.append(
            {
                "source_id": source["id"],
                "kind": source["kind"],
                "context": context,
                "weight": _round(source.get("weight", 1.0)),
                "features": extract_linguistic_features(source["text"]),
            }
        )

    by_mode = defaultdict(list)
    by_kind = defaultdict(list)
    for profile in source_profiles:
        by_mode[profile["context"]["mode"]].append(profile)
        by_kind[profile["kind"]].append(profile)

    cautions = [
        ("Measurements are descriptive ranges, not generation targets or proof of authorship."),
        (
            "No matched-register reference corpus was supplied; observed features "
            "must not be labelled distinctive without comparison."
        ),
        (
            "Stance and connective lexicons are English-specific; structural "
            "measurements remain descriptive for other languages."
        ),
    ]
    if len(source_profiles) < 3:
        cautions.append("Fewer than three usable sources limits confidence in recurring patterns.")
    if len(by_mode) > 1:
        cautions.append(
            "Spoken and written material are reported separately because register varies."
        )

    return {
        "schema_version": "1.0",
        "framework": "lightweight-corpus-stylistics",
        "framework_version": FRAMEWORK_VERSION,
        "language_scope": "English lexicons with language-agnostic structural measures",
        "source_profiles": source_profiles,
        "overall": _aggregate(source_profiles),
        "by_mode": {name: _aggregate(profiles) for name, profiles in sorted(by_mode.items())},
        "by_source_kind": {
            name: _aggregate(profiles) for name, profiles in sorted(by_kind.items())
        },
        "reference_comparison": {
            "status": "not_supplied",
            "claim_limit": (
                "Observed features may reflect topic or register and are not necessarily "
                "person-distinctive."
            ),
        },
        "cautions": cautions,
    }
