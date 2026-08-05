"""Provide voice assessment capabilities."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .linguistics import extract_linguistic_features
from .storage import RunStore
from .voices import VoiceRegistry

ASSESSMENT_FRAMEWORK = "lightweight-corpus-stylistics-assessment"
ASSESSMENT_VERSION = "1.0"
SCORE_TYPE = "statistical_voice_score"
SCORE_METHODS = {"deterministic", "ml"}
_NON_STYLE_FEATURES = {"word_count", "sentence_count", "paragraph_count"}


def score_preference_path(root: Path, voice_id: str) -> Path:
    """Score the preference path.

    Args:
        root (Path): The workspace root directory.
        voice_id (str): The stable identifier for the selected voice.

    Returns:
        Path: The resolved filesystem path for preference path.
    """
    return root.resolve() / "profiles" / voice_id / "statistical-voice-score.json"


def load_score_preference(root: Path, voice_id: str) -> Optional[Dict[str, Any]]:
    """Load the score preference.

    Args:
        root (Path): The workspace root directory.
        voice_id (str): The stable identifier for the selected voice.

    Returns:
        Optional[Dict[str, Any]]: The loaded score preference when available; otherwise
            ``None``.

    Raises:
        ValueError: If an input value violates the supported domain constraints.
    """
    path = score_preference_path(root, voice_id)
    if not path.exists():
        return None
    preference = json.loads(path.read_text(encoding="utf-8"))
    if preference.get("voice_id") != voice_id:
        raise ValueError("Statistical voice score preference identity mismatch")
    if preference.get("method") not in SCORE_METHODS:
        raise ValueError("Statistical voice score method must be deterministic or ml")
    if not isinstance(preference.get("enabled"), bool):
        raise ValueError("Statistical voice score enabled value must be a boolean")
    return preference


def save_score_preference(
    root: Path,
    voice_id: str,
    *,
    enabled: bool,
    method: str,
    selected_by: Optional[str] = None,
) -> Dict[str, Any]:
    """Save the score preference.

    Args:
        root (Path): The workspace root directory.
        voice_id (str): The stable identifier for the selected voice.
        enabled (bool): Whether enabled behavior is enabled.
        method (str): The method text processed when save score preference.
        selected_by (Optional[str]): The selected by text processed when save score
            preference. Defaults to ``None``.

    Returns:
        Dict[str, Any]: The structured persisted data for score preference.

    Raises:
        ValueError: If an input value violates the supported domain constraints.
    """
    if method not in SCORE_METHODS:
        raise ValueError("Statistical voice score method must be deterministic or ml")
    preference = {
        "schema_version": "1.0",
        "voice_id": voice_id,
        "enabled": enabled,
        "method": method,
        "selected_by": selected_by,
        "selected_at": datetime.now(UTC).isoformat(),
    }
    RunStore._atomic_text(
        score_preference_path(root, voice_id),
        json.dumps(preference, indent=2),
    )
    return preference


def resolve_score_policy(
    root: Path, voice_id: str, workspace_policy: Dict[str, Any]
) -> Dict[str, Any]:
    """Resolve the score policy.

    Args:
        root (Path): The workspace root directory.
        voice_id (str): The stable identifier for the selected voice.
        workspace_policy (Dict[str, Any]): The workspace policy collection consumed
            while resolve score policy.

    Returns:
        Dict[str, Any]: The structured resolved data for score policy.
    """
    policy = dict(workspace_policy)
    preference = load_score_preference(root, voice_id)
    if preference is not None:
        policy["enabled"] = preference["enabled"]
        policy["method"] = preference["method"]
        policy["voice_preference"] = preference
    return policy


def _unavailable(
    voice_id: str,
    voice_version: Optional[str],
    status: str,
    reason: str,
    method: str = "deterministic",
) -> Dict[str, Any]:
    """Return the unavailable.

    Args:
        voice_id (str): The stable identifier for the selected voice.
        voice_version (Optional[str]): The immutable version of the selected voice
            profile.
        status (str): The status text processed when unavailable.
        reason (str): The human-readable reason recorded for the decision.
        method (str): The method text processed when unavailable. Defaults to
            ``'deterministic'``.

    Returns:
        Dict[str, Any]: The structured resulting data for unavailable.
    """
    return {
        "schema_version": "1.0",
        "type": SCORE_TYPE,
        "method": method,
        "framework": ASSESSMENT_FRAMEWORK,
        "framework_version": ASSESSMENT_VERSION,
        "status": status,
        "voice_id": voice_id,
        "voice_version": voice_version,
        "score": None,
        "score_scale": {"minimum": 0, "maximum": 100},
        "evidence_coverage": 0.0,
        "reason": reason,
        "outliers": [],
        "claim_limit": (
            "This assessment is advisory corpus comparison, not proof of authorship or identity."
        ),
    }


@dataclass(frozen=True)
class LinguisticAssessmentOptions:
    """Configure a linguistic voice assessment."""

    voice_id: str
    voice_version: Optional[str]
    minimum_sources: int = 20
    minimum_draft_words: int = 100
    outlier_iqr_multiplier: float = 1.5
    max_reported_outliers: int = 8


def assess_linguistic_signature(
    signature: Dict[str, Any],
    draft: str,
    options: LinguisticAssessmentOptions,
) -> Dict[str, Any]:
    """Compare a draft with a voice distribution without judging authorship.

    Args:
        signature (Dict[str, Any]): The statistical voice signature used for comparison.
        draft (str): The draft content to evaluate or transform.
        options (LinguisticAssessmentOptions): The options controlling this operation.

    Returns:
        Dict[str, Any]: The structured assessment data for linguistic signature.
    """
    baseline, baseline_details, source_count = _baseline(signature, options)
    if source_count < options.minimum_sources:
        report = _unavailable(
            options.voice_id,
            options.voice_version,
            "insufficient_evidence",
            f"The selected signature has {source_count} usable sources; "
            f"{options.minimum_sources} are required.",
        )
        report["baseline"] = baseline_details
        return report
    features = extract_linguistic_features(draft)
    word_count = int(features["word_count"])
    if word_count < options.minimum_draft_words:
        return _short_draft_report(options, baseline_details, word_count)
    outliers, evaluated, eligible = _outliers(features, baseline, options.outlier_iqr_multiplier)
    if evaluated == 0:
        return _no_variation_report(options, baseline_details, word_count)
    return _assessment_report(
        options,
        baseline_details,
        word_count,
        source_count,
        outliers,
        evaluated,
        eligible,
    )


def _baseline(
    signature: Dict[str, Any],
    options: LinguisticAssessmentOptions,
) -> tuple[dict, dict, int]:
    """Return the baseline.

    Args:
        signature (Dict[str, Any]): The statistical voice signature used for comparison.
        options (LinguisticAssessmentOptions): The options controlling this operation.

    Returns:
        tuple[dict, dict, int]: The resulting baseline values in their documented order.
    """
    profiles = signature.get("source_profiles", [])
    written_profiles = [
        item for item in profiles if item.get("context", {}).get("mode") == "written"
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
        "minimum_sources": options.minimum_sources,
        "outlier_rule": f"{options.outlier_iqr_multiplier} times the interquartile range",
    }
    return baseline, baseline_details, source_count


def _short_draft_report(
    options: LinguisticAssessmentOptions,
    baseline_details: dict,
    word_count: int,
) -> Dict[str, Any]:
    """Return the short draft report.

    Args:
        options (LinguisticAssessmentOptions): The options controlling this operation.
        baseline_details (dict): The baseline details value passed to short draft
            report.
        word_count (int): The word count value that controls short draft report.

    Returns:
        Dict[str, Any]: The structured resulting data for short draft report.
    """
    report = _unavailable(
        options.voice_id,
        options.voice_version,
        "insufficient_draft",
        f"The draft has {word_count} words; {options.minimum_draft_words} are required.",
    )
    report["baseline"] = baseline_details
    report["draft"] = {"word_count": word_count}
    return report


def _outliers(
    features: Dict[str, Any],
    baseline: dict,
    multiplier: float,
) -> tuple[List[Dict[str, Any]], int, int]:
    """Return the outliers.

    Compare each draft feature with the voice distribution and return only deviations
    that exceed the configured tolerance.

    Args:
        features (Dict[str, Any]): The features collection consumed while outliers.
        baseline (dict): The baseline value passed to outliers.
        multiplier (float): The multiplier value that controls outliers.

    Returns:
        tuple[List[Dict[str, Any]], int, int]: The resulting outliers values in their
            documented order.
    """
    outliers: List[Dict[str, Any]] = []
    evaluated = 0
    eligible = 0
    for name, value in features.items():
        if name in _NON_STYLE_FEATURES or name not in baseline:
            continue
        distribution = baseline[name]
        eligible += 1
        q1 = float(distribution["q1"])
        q3 = float(distribution["q3"])
        observed_min = float(distribution["min"])
        observed_max = float(distribution["max"])
        iqr = q3 - q1
        if iqr <= 0:
            # A constant feature supplies no evidence about tolerated variation.
            continue
        lower = q1 - (multiplier * iqr)
        upper = q3 + (multiplier * iqr)
        if observed_min >= 0:
            lower = max(0.0, lower)
        evaluated += 1
        if lower <= float(value) <= upper:
            continue
        direction = "above" if float(value) > upper else "below"
        deviation = (
            (float(value) - upper) / iqr if direction == "above" else (lower - float(value)) / iqr
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
    return outliers, evaluated, eligible


def _no_variation_report(
    options: LinguisticAssessmentOptions,
    baseline_details: dict,
    word_count: int,
) -> Dict[str, Any]:
    """Return the no variation report.

    Args:
        options (LinguisticAssessmentOptions): The options controlling this operation.
        baseline_details (dict): The baseline details value passed to no variation
            report.
        word_count (int): The word count value that controls no variation report.

    Returns:
        Dict[str, Any]: The structured resulting data for no variation report.
    """
    report = _unavailable(
        options.voice_id,
        options.voice_version,
        "insufficient_variation",
        "The signature has no variable style features suitable for comparison.",
    )
    report["baseline"] = baseline_details
    report["draft"] = {"word_count": word_count}
    report["evaluated_feature_count"] = 0
    return report


def _assessment_report(
    options: LinguisticAssessmentOptions,
    baseline_details: dict,
    word_count: int,
    source_count: int,
    outliers: List[Dict[str, Any]],
    evaluated: int,
    eligible: int,
) -> Dict[str, Any]:
    """Return the assessment report.

    Combine deterministic and optional statistical evidence into one policy-aware voice
    assessment report.

    Args:
        options (LinguisticAssessmentOptions): The options controlling this operation.
        baseline_details (dict): The baseline details value passed to assessment report.
        word_count (int): The word count value that controls assessment report.
        source_count (int): The source count value that controls assessment report.
        outliers (List[Dict[str, Any]]): The outliers collection consumed while
            assessment report.
        evaluated (int): The evaluated value that controls assessment report.
        eligible (int): The eligible value that controls assessment report.

    Returns:
        Dict[str, Any]: The structured resulting data for assessment report.
    """
    outliers.sort(key=lambda item: (-item["distance_beyond_envelope_iqr"], item["feature"]))
    reported = outliers[: options.max_reported_outliers]
    # Only distance beyond the tolerated IQR envelope is penalised. Values
    # anywhere inside the envelope receive the same treatment, so the score
    # cannot reward regression toward the corpus median.
    capped_excess = sum(min(float(item["distance_beyond_envelope_iqr"]), 4.0) for item in outliers)
    score = round(100.0 * math.exp(-(capped_excess / evaluated)), 1)
    evidence_coverage = round(evaluated / max(eligible, 1), 4)
    return {
        "schema_version": "1.0",
        "type": SCORE_TYPE,
        "method": "deterministic",
        "framework": ASSESSMENT_FRAMEWORK,
        "framework_version": ASSESSMENT_VERSION,
        "status": "material_outliers" if outliers else "no_material_outliers",
        "voice_id": options.voice_id,
        "voice_version": options.voice_version,
        "score": score,
        "score_scale": {"minimum": 0, "maximum": 100},
        "score_interpretation": (
            "Compatibility with the observed feature envelopes; higher is more "
            "compatible. Values within an envelope are not rewarded for moving "
            "closer to its centre."
        ),
        "evidence_coverage": evidence_coverage,
        "reliability": {
            "status": "adequate",
            "source_count": source_count,
            "minimum_sources": options.minimum_sources,
        },
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
    """Resolve an active voice signature and assess one draft against it.

    Resolve the active voice signature, select the configured assessment method, and
    score the draft without asserting authorship.

    Args:
        root (Path): The workspace root directory.
        voice_id (str): The stable identifier for the selected voice.
        voice_version (Optional[str]): The immutable version of the selected voice
            profile.
        draft (str): The draft content to evaluate or transform.
        policy (Dict[str, Any]): The policy collection consumed while assess voice
            draft.

    Returns:
        Dict[str, Any]: The structured assessment data for voice draft.

    Raises:
        ValueError: If an input value violates the supported domain constraints.
    """
    method = policy.get("method", policy.get("mode", "deterministic"))
    if method == "statistical":
        method = "deterministic"
    if method not in SCORE_METHODS:
        raise ValueError("Statistical voice score method must be deterministic or ml")
    if voice_id == "default":
        return _unavailable(
            voice_id,
            voice_version,
            "unavailable",
            "The default placeholder voice has no source-derived signature.",
            method,
        )
    resolved = VoiceRegistry(root).resolve(voice_id, voice_version)
    if method == "ml":
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
            method,
        )
    signature = json.loads(signature_path.read_text(encoding="utf-8"))
    return assess_linguistic_signature(
        signature,
        draft,
        LinguisticAssessmentOptions(
            voice_id=voice_id,
            voice_version=resolved.get("version"),
            minimum_sources=policy["minimum_sources"],
            minimum_draft_words=policy["minimum_draft_words"],
            outlier_iqr_multiplier=policy["outlier_iqr_multiplier"],
            max_reported_outliers=policy["max_reported_outliers"],
        ),
    )
