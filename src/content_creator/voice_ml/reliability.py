"""Provide deterministic voice-ML corpus eligibility policy."""

from __future__ import annotations

from typing import Any

HARD_MINIMUM_DOCUMENTS_PER_CLASS = 10
HARD_MINIMUM_WORDS_PER_CLASS = 5000
RELIABLE_MINIMUM_DOCUMENTS_PER_CLASS = 40
RELIABLE_MINIMUM_WORDS_PER_CLASS = 20000


def training_reliability(
    author_documents: int,
    author_words: int,
    comparison_documents: int,
    comparison_words: int,
) -> dict[str, Any]:
    """Return whether corpus volume and class balance support model training.

    Classify hard insufficiency separately from low-confidence warnings so the
    caller cannot accidentally convert a training refusal into confirmation.

    Args:
        author_documents (int): Number of independent author documents.
        author_words (int): Weighted author word count.
        comparison_documents (int): Number of independent comparison documents.
        comparison_words (int): Comparison word count.

    Returns:
        dict[str, Any]: Eligibility status, warnings, failures, and thresholds.
    """
    hard_failures = []
    warnings = []
    for label, documents, words in (
        ("author", author_documents, author_words),
        ("comparison", comparison_documents, comparison_words),
    ):
        if documents < HARD_MINIMUM_DOCUMENTS_PER_CLASS:
            hard_failures.append(
                f"{label} corpus has {documents} documents; "
                f"at least {HARD_MINIMUM_DOCUMENTS_PER_CLASS} are required to train."
            )
        elif documents < RELIABLE_MINIMUM_DOCUMENTS_PER_CLASS:
            warnings.append(
                f"{label} corpus has {documents} documents; "
                f"{RELIABLE_MINIMUM_DOCUMENTS_PER_CLASS} are recommended for a reliable model."
            )
        if words < HARD_MINIMUM_WORDS_PER_CLASS:
            hard_failures.append(
                f"{label} corpus has {words} words; "
                f"at least {HARD_MINIMUM_WORDS_PER_CLASS} are required to train."
            )
        elif words < RELIABLE_MINIMUM_WORDS_PER_CLASS:
            warnings.append(
                f"{label} corpus has {words} words; "
                f"{RELIABLE_MINIMUM_WORDS_PER_CLASS} are recommended for a reliable model."
            )
    smaller = min(author_documents, comparison_documents)
    larger = max(author_documents, comparison_documents)
    if smaller and larger / smaller > 2:
        warnings.append(
            "The class sizes differ by more than 2:1; use a better-matched comparison corpus."
        )
    status = "insufficient_data" if hard_failures else "low_confidence" if warnings else "reliable"
    return {
        "status": status,
        "can_train": not hard_failures,
        "requires_low_confidence_acceptance": bool(warnings and not hard_failures),
        "hard_failures": hard_failures,
        "warnings": warnings,
        "thresholds": {
            "hard_minimum_documents_per_class": HARD_MINIMUM_DOCUMENTS_PER_CLASS,
            "hard_minimum_words_per_class": HARD_MINIMUM_WORDS_PER_CLASS,
            "reliable_minimum_documents_per_class": RELIABLE_MINIMUM_DOCUMENTS_PER_CLASS,
            "reliable_minimum_words_per_class": RELIABLE_MINIMUM_WORDS_PER_CLASS,
        },
    }


def training_preflight(
    author_rows: list[list[float]],
    author_words: int,
    comparison_rows: list[list[float]],
    comparison_words: int,
    comparison_audit: dict[str, Any],
    reliability: dict[str, Any],
) -> dict[str, Any]:
    """Return corpus eligibility inputs without fitting a model.

    Args:
        author_rows (list[list[float]]): Prepared author feature rows.
        author_words (int): Weighted author word count.
        comparison_rows (list[list[float]]): Prepared comparison feature rows.
        comparison_words (int): Comparison word count.
        comparison_audit (dict[str, Any]): Deduplication and exclusion evidence.
        reliability (dict[str, Any]): Evaluated corpus reliability result.

    Returns:
        dict[str, Any]: Stable author, comparison, and reliability summary.
    """
    return {
        "author": {"documents": len(author_rows), "weighted_words": author_words},
        "comparison": {
            "documents": len(comparison_rows),
            "words": comparison_words,
            "skipped": comparison_audit["skipped"],
        },
        "reliability": reliability,
    }


def blocked_training_result(
    voice_id: str,
    voice_version: str,
    preflight: dict[str, Any],
    reliability: dict[str, Any],
    accept_low_confidence: bool,
) -> dict[str, Any] | None:
    """Return a stable refusal or confirmation request when training is ineligible.

    Args:
        voice_id (str): Stable voice identifier.
        voice_version (str): Immutable voice version.
        preflight (dict[str, Any]): Corpus preflight evidence.
        reliability (dict[str, Any]): Evaluated corpus reliability result.
        accept_low_confidence (bool): Whether warnings received explicit acceptance.

    Returns:
        dict[str, Any] | None: Blocked result, or ``None`` when training may proceed.
    """
    result = {
        "trained": False,
        "voice_id": voice_id,
        "voice_version": voice_version,
        "preflight": preflight,
    }
    if not reliability["can_train"]:
        return {"status": "insufficient_data", **result}
    if reliability["requires_low_confidence_acceptance"] and not accept_low_confidence:
        return {
            "status": "warning_confirmation_required",
            **result,
            "next_step": (
                "Add more independent matched documents, or repeat with "
                "--accept-low-confidence after reviewing the warnings."
            ),
        }
    return None
