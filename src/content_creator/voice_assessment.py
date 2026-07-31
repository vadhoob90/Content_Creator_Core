from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .linguistics import extract_linguistic_features
from .voices import VoiceRegistry

ASSESSMENT_FRAMEWORK = "lightweight-corpus-stylistics-assessment"
ASSESSMENT_VERSION = "1.0"
_NON_STYLE_FEATURES = {"word_count", "sentence_count", "paragraph_count"}


def _unavailable(
    voice_id: str,
    voice_version: Optional[str],
    status: str,
    reason: str,
) -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "framework": ASSESSMENT_FRAMEWORK,
        "framework_version": ASSESSMENT_VERSION,
        "status": status,
        "voice_id": voice_id,
        "voice_version": voice_version,
        "reason": reason,
        "outliers": [],
        "claim_limit": (
            "This assessment is advisory corpus comparison, not proof of "
            "authorship or identity."
        ),
    }


def assess_linguistic_signature(
    signature: Dict[str, Any],
    draft: str,
    *,
    voice_id: str,
    voice_version: Optional[str],
    minimum_sources: int = 20,
    minimum_draft_words: int = 100,
    outlier_iqr_multiplier: float = 1.5,
    max_reported_outliers: int = 8,
) -> Dict[str, Any]:
    """Compare a draft with a voice distribution without judging authorship."""

    profiles = signature.get("source_profiles", [])
    written_profiles = [
        item
        for item in profiles
        if item.get("context", {}).get("mode") == "written"
    ]
    if written_profiles and signature.get("by_mode", {}).get("written"):
        baseline = signature["by_mode"]["written"]
        baseline_scope = "written"
        source_count = len(written_profiles)
    else:
        baseline = signature.get("overall", {})
        baseline_scope = "overall"
        source_count = len(profiles)

    baseline_details = {
        "scope": baseline_scope,
        "source_count": source_count,
        "minimum_sources": minimum_sources,
        "outlier_rule": "{} times the interquartile range".format(
            outlier_iqr_multiplier
        ),
    }
    if source_count < minimum_sources:
        report = _unavailable(
            voice_id,
            voice_version,
            "insufficient_evidence",
            "The selected signature has {} usable sources; {} are required.".format(
                source_count, minimum_sources
            ),
        )
        report["baseline"] = baseline_details
        return report

    features = extract_linguistic_features(draft)
    word_count = int(features["word_count"])
    if word_count < minimum_draft_words:
        report = _unavailable(
            voice_id,
            voice_version,
            "insufficient_draft",
            "The draft has {} words; {} are required for a stable comparison.".format(
                word_count, minimum_draft_words
            ),
        )
        report["baseline"] = baseline_details
        report["draft"] = {"word_count": word_count}
        return report

    outliers = []
    evaluated = 0
    for name, value in features.items():
        if name in _NON_STYLE_FEATURES or name not in baseline:
            continue
        distribution = baseline[name]
        q1 = float(distribution["q1"])
        q3 = float(distribution["q3"])
        observed_min = float(distribution["min"])
        observed_max = float(distribution["max"])
        iqr = q3 - q1
        if iqr <= 0:
            # A constant feature supplies no evidence about tolerated variation.
            continue
        lower = q1 - (outlier_iqr_multiplier * iqr)
        upper = q3 + (outlier_iqr_multiplier * iqr)
        if observed_min >= 0:
            lower = max(0.0, lower)
        evaluated += 1
        if lower <= float(value) <= upper:
            continue
        direction = "above" if float(value) > upper else "below"
        deviation = (
            (float(value) - upper) / iqr
            if direction == "above"
            else (lower - float(value)) / iqr
        )
        outliers.append(
            {
                "feature": name,
                "draft_value": round(float(value), 4),
                "reference_envelope": {
                    "lower": round(lower, 4),
                    "upper": round(upper, 4),
                },
                "observed_range": {
                    "minimum": round(observed_min, 4),
                    "maximum": round(observed_max, 4),
                },
                "direction": direction,
                "distance_beyond_envelope_iqr": round(deviation, 4),
            }
        )

    if evaluated == 0:
        report = _unavailable(
            voice_id,
            voice_version,
            "insufficient_variation",
            "The signature has no variable style features suitable for comparison.",
        )
        report["baseline"] = baseline_details
        report["draft"] = {"word_count": word_count}
        report["evaluated_feature_count"] = 0
        return report

    outliers.sort(
        key=lambda item: (-item["distance_beyond_envelope_iqr"], item["feature"])
    )
    reported = outliers[:max_reported_outliers]
    return {
        "schema_version": "1.0",
        "framework": ASSESSMENT_FRAMEWORK,
        "framework_version": ASSESSMENT_VERSION,
        "status": "material_outliers" if outliers else "no_material_outliers",
        "voice_id": voice_id,
        "voice_version": voice_version,
        "baseline": baseline_details,
        "draft": {"word_count": word_count},
        "evaluated_feature_count": evaluated,
        "outlier_count": len(outliers),
        "outliers": reported,
        "outliers_truncated": len(outliers) > len(reported),
        "critic_guidance": (
            "Treat outliers as advisory evidence. Consider topic, register, length, "
            "and natural evolution. Do not request a change solely to improve "
            "numerical conformity, and do not optimise toward the corpus centre."
        ),
        "claim_limit": (
            "Compatibility with observed ranges is not proof of authorship, identity, "
            "or authenticity. No matched-register distinctiveness is implied."
        ),
    }


def assess_voice_draft(
    root: Path,
    voice_id: str,
    voice_version: Optional[str],
    draft: str,
    policy: Dict[str, Any],
) -> Dict[str, Any]:
    """Resolve an active voice signature and assess one draft against it."""

    if voice_id == "default":
        return _unavailable(
            voice_id,
            voice_version,
            "unavailable",
            "The default placeholder voice has no source-derived signature.",
        )
    resolved = VoiceRegistry(root).resolve(voice_id, voice_version)
    if policy["mode"] == "ml":
        from .voice_ml import assess_with_ml_artifact

        return assess_with_ml_artifact(
            root,
            voice_id,
            resolved["version"],
            draft,
            policy["minimum_draft_words"],
        )
    version_root = root.resolve() / resolved["path"]
    signature_path = version_root / "linguistic-signature.json"
    manifest_path = version_root / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        component = manifest.get("components", {}).get("linguistic_signature")
        if component:
            signature_path = version_root / component
    if not signature_path.exists():
        return _unavailable(
            voice_id,
            resolved.get("version"),
            "unavailable",
            "The resolved voice has no linguistic signature.",
        )
    signature = json.loads(signature_path.read_text(encoding="utf-8"))
    return assess_linguistic_signature(
        signature,
        draft,
        voice_id=voice_id,
        voice_version=resolved.get("version"),
        minimum_sources=policy["minimum_sources"],
        minimum_draft_words=policy["minimum_draft_words"],
        outlier_iqr_multiplier=policy["outlier_iqr_multiplier"],
        max_reported_outliers=policy["max_reported_outliers"],
    )
