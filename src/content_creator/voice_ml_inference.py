from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict

from .linguistics import extract_linguistic_features
from .storage import StorageError
from .voice_ml_training import ML_FRAMEWORK, ML_FRAMEWORK_VERSION, ml_model_path


def assess_with_ml_artifact(
    root: Path,
    voice_id: str,
    voice_version: str,
    draft: str,
    minimum_draft_words: int,
) -> Dict[str, Any]:
    path = ml_model_path(root, voice_id, voice_version)
    if not path.exists():
        return {
            "schema_version": "1.0",
            "type": "statistical_voice_score",
            "method": "ml",
            "framework": ML_FRAMEWORK,
            "framework_version": ML_FRAMEWORK_VERSION,
            "status": "ml_model_unavailable",
            "voice_id": voice_id,
            "voice_version": voice_version,
            "score": None,
            "score_scale": {"minimum": 0, "maximum": 100},
            "evidence_coverage": 0.0,
            "reason": "No trained ML model exists for the resolved voice version.",
        }
    artifact = json.loads(path.read_text(encoding="utf-8"))
    if artifact.get("voice_id") != voice_id or artifact.get("voice_version") != voice_version:
        raise StorageError("ML model identity does not match the resolved voice")
    features = extract_linguistic_features(draft)
    word_count = int(features["word_count"])
    if word_count < minimum_draft_words:
        return {
            "schema_version": "1.0",
            "type": "statistical_voice_score",
            "method": "ml",
            "framework": ML_FRAMEWORK,
            "framework_version": ML_FRAMEWORK_VERSION,
            "status": "insufficient_draft",
            "voice_id": voice_id,
            "voice_version": voice_version,
            "score": None,
            "score_scale": {"minimum": 0, "maximum": 100},
            "evidence_coverage": 0.0,
            "reason": "The draft has {} words; {} are required.".format(
                word_count, minimum_draft_words
            ),
        }
    names = artifact["feature_schema"]["feature_names"]
    row = [float(features[name]) for name in names]
    means = artifact["preprocessing"]["mean"]
    scales = artifact["preprocessing"]["scale"]
    coefficients = artifact["classifier"]["coefficients"]
    standardised = [
        (value - float(mean)) / (float(scale) or 1.0)
        for value, mean, scale in zip(row, means, scales, strict=True)
    ]
    contributions = [
        value * float(coefficient)
        for value, coefficient in zip(standardised, coefficients, strict=True)
    ]
    logit = float(artifact["classifier"]["intercept"]) + sum(contributions)
    score = 1.0 / (1.0 + math.exp(-max(min(logit, 709), -709)))
    threshold = float(artifact["classifier"]["decision_threshold"])
    ranked = sorted(
        zip(names, contributions, strict=True),
        key=lambda item: abs(item[1]),
        reverse=True,
    )[:5]
    return {
        "schema_version": "1.0",
        "type": "statistical_voice_score",
        "method": "ml",
        "framework": ML_FRAMEWORK,
        "framework_version": ML_FRAMEWORK_VERSION,
        "status": "ml_above_threshold" if score >= threshold else "ml_below_threshold",
        "voice_id": voice_id,
        "voice_version": voice_version,
        "draft": {"word_count": word_count},
        "score": round(score * 100.0, 1),
        "score_scale": {"minimum": 0, "maximum": 100},
        "score_interpretation": (
            "Classifier compatibility with the author corpus relative to the "
            "supplied comparison corpus. It is not an authorship probability."
        ),
        "evidence_coverage": 1.0,
        "model_score": round(score, 4),
        "decision_threshold": threshold,
        "top_feature_contributions": [
            {
                "feature": name,
                "direction": "author" if contribution >= 0 else "comparison",
                "contribution": round(float(contribution), 4),
            }
            for name, contribution in ranked
        ],
        "reliability": artifact["reliability"],
        "critic_guidance": (
            "Treat this score as advisory evidence only. Do not request a change "
            "solely to cross the threshold or optimise feature contributions."
        ),
        "claim_limit": artifact["claim_limit"],
    }
