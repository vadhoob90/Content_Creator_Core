"""Return cached baseline measurements combined with incremental measurements."""

from __future__ import annotations

import json
from pathlib import Path

from ..linguistics import combine_linguistic_signatures
from ..voice_build.models import BuildState


def combine_incremental_measurements(state: BuildState, baseline_directory: Path | None) -> None:
    """Return combined measurements without reading historical corpus text.

    Args:
        state (BuildState): Mutable build state containing delta measurements.
        baseline_directory (Path | None): Verified immutable active-version directory.

    Returns:
        None: Corpus and linguistic signature are replaced with deterministic aggregates.
    """
    if baseline_directory is None:
        return
    signature_path = baseline_directory / "linguistic-signature.json"
    baseline_signature = (
        json.loads(signature_path.read_text(encoding="utf-8"))
        if signature_path.is_file()
        else {"source_profiles": []}
    )
    baseline_corpus = (
        json.loads((baseline_directory / "corpus-report.json").read_text(encoding="utf-8"))
        if (baseline_directory / "corpus-report.json").is_file()
        else {}
    )
    state.signature = combine_linguistic_signatures(baseline_signature, state.signature)
    state.corpus = _combined_corpus(baseline_corpus, state.corpus)


def _combined_corpus(baseline: dict, delta: dict) -> dict:
    """Return deterministic aggregate corpus counts for baseline plus delta.

    Args:
        baseline (dict): Persisted active corpus report.
        delta (dict): Newly measured evidence-delta corpus report.

    Returns:
        dict: Combined report retaining visible delta allocation fields.
    """
    result = dict(delta)
    for field in (
        "usable_source_count",
        "usable_word_count",
        "attribution_weighted_word_count",
        "direct_authorship_count",
    ):
        result[field] = int(baseline.get(field, 0)) + int(delta.get(field, 0))
    kinds = dict(baseline.get("content_types", {}))
    for kind, count in delta.get("content_types", {}).items():
        kinds[kind] = int(kinds.get(kind, 0)) + int(count)
    result["content_types"] = kinds
    result["sufficient"] = bool(baseline.get("sufficient")) or bool(delta.get("sufficient"))
    result["gaps"] = list(delta.get("gaps", [])) if not result["sufficient"] else []
    result["measurement_basis"] = "persisted-baseline-plus-evidence-delta"
    result["baseline_measurements_reused"] = True
    result["baseline_corpus_text_retrieved"] = False
    result["delta_source_count"] = int(delta.get("usable_source_count", 0))
    result["baseline_source_count"] = int(baseline.get("usable_source_count", 0))
    return result
