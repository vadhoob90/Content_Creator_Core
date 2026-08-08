"""Provide voice evaluation capabilities."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

from .domain import WorkOrder
from .voices import VoiceRegistry


def phrase_overlap(text: str, corpus: Iterable[str], n: int = 12) -> dict:
    """Return material phrase overlap between a draft and voice evidence.

    Args:
        text (str): Draft text to inspect.
        corpus (Iterable[str]): Authorized voice evidence.
        n (int): Phrase length in normalized words. Defaults to ``12``.

    Returns:
        dict: Pass status and sorted matching phrases.
    """
    words = re.findall(r"\b[\w'-]+\b", text.lower())
    generated = {" ".join(words[index : index + n]) for index in range(max(0, len(words) - n + 1))}
    matches = set()
    for source in corpus:
        source_words = re.findall(r"\b[\w'-]+\b", source.lower())
        source_ngrams = {
            " ".join(source_words[index : index + n])
            for index in range(max(0, len(source_words) - n + 1))
        }
        matches.update(generated & source_ngrams)
    return {"passed": not matches, "matches": sorted(matches)}


def evaluate_voice_output(root: Path, order: WorkOrder, draft: str) -> dict:
    """Evaluate the voice output.

    Args:
        root (Path): The workspace root directory.
        order (WorkOrder): The work order that defines the requested content run.
        draft (str): The draft content to evaluate or transform.

    Returns:
        dict: The evaluation dict for voice output.
    """
    if order.voice_id == "default":
        return {"passed": True, "errors": [], "overlap": {"passed": True, "matches": []}}
    resolved = VoiceRegistry(root).resolve(
        order.voice_id,
        order.voice_version,
        allow_inactive=order.resolved_voice,
    )
    version_root = root / resolved["path"]
    source_index = json.loads((version_root / "source-index.json").read_text(encoding="utf-8"))
    corpus = []
    for record in source_index:
        cache = root / record["cache_path"]
        if cache.exists() and record.get("approved_for_analysis"):
            corpus.append(cache.read_text(encoding="utf-8"))
    overlap = phrase_overlap(draft, corpus)
    errors = []
    if not overlap["passed"]:
        errors.append("Draft materially overlaps voice source text")
    experiential = re.findall(
        r"\bI\s+(?:worked|led|built|remember|experienced|founded|joined)\b",
        draft,
        re.I,
    )
    if experiential and not any(
        phrase.lower() in source.lower() for phrase in experiential for source in corpus
    ):
        errors.append("Draft contains unsupported personal experience")
    return {"passed": not errors, "errors": errors, "overlap": overlap}
