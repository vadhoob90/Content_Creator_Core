"""Provide voice evaluation capabilities."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .domain import WorkOrder
from .overlap import phrase_overlap
from .voices import VoiceRegistry


def evaluate_voice_output(root: Path, order: WorkOrder, draft: str) -> dict:
    """Evaluate voice output."""
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
