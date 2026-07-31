from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .ingestion import content_hash, read_source
from .linguistics import extract_linguistic_features
from .storage import RunStore, StorageError
from .voices import VoiceRegistry

ML_FRAMEWORK = "regularised-logistic-regression-stylometry"
ML_FRAMEWORK_VERSION = "1.0"
MODEL_FEATURE_NAMES = (
    "sentence_length_median",
    "sentence_length_q1",
    "sentence_length_q3",
    "sentence_length_variation",
    "short_sentence_ratio",
    "long_sentence_ratio",
    "paragraph_length_median",
    "questions_per_100_sentences",
    "exclamations_per_100_sentences",
    "first_person_per_1000_words",
    "second_person_per_1000_words",
    "modals_per_1000_words",
    "hedges_per_1000_words",
    "boosters_per_1000_words",
    "contractions_per_1000_words",
    "contrast_markers_per_1000_words",
    "example_markers_per_1000_words",
    "conclusion_markers_per_1000_words",
    "dashes_per_1000_words",
    "semicolons_per_1000_words",
    "colons_per_1000_words",
    "lexical_diversity_mattr",
)

HARD_MINIMUM_DOCUMENTS_PER_CLASS = 10
HARD_MINIMUM_WORDS_PER_CLASS = 5000
RELIABLE_MINIMUM_DOCUMENTS_PER_CLASS = 40
RELIABLE_MINIMUM_WORDS_PER_CLASS = 20000


class MLDependencyError(RuntimeError):
    pass


def _signature_path(root: Path, resolved: Dict[str, Any]) -> Path:
    version_root = root.resolve() / resolved["path"]
    signature_path = version_root / "linguistic-signature.json"
    manifest_path = version_root / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        component = manifest.get("components", {}).get("linguistic_signature")
        if component:
            signature_path = version_root / component
    return signature_path


def load_voice_signature(
    root: Path, voice_id: str, voice_version: Optional[str]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    resolved = VoiceRegistry(root).resolve(voice_id, voice_version)
    path = _signature_path(root, resolved)
    if not path.exists():
        raise StorageError(
            "The resolved voice has no linguistic signature: {}@{}".format(
                voice_id, resolved.get("version")
            )
        )
    return resolved, json.loads(path.read_text(encoding="utf-8"))


def ml_model_path(root: Path, voice_id: str, voice_version: str) -> Path:
    return (
        root.resolve()
        / "profiles"
        / voice_id
        / "models"
        / voice_version
        / "logistic-regression.json"
    )


def _feature_row(features: Dict[str, Any]) -> List[float]:
    missing = [name for name in MODEL_FEATURE_NAMES if name not in features]
    if missing:
        raise StorageError(
            "Linguistic feature schema is not ML-compatible; missing: {}".format(
                ", ".join(missing)
            )
        )
    return [float(features[name]) for name in MODEL_FEATURE_NAMES]


def _fingerprint(rows: Iterable[List[float]]) -> str:
    encoded = json.dumps(
        list(rows), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _author_rows(signature: Dict[str, Any]) -> Tuple[List[List[float]], int]:
    written = [
        item
        for item in signature.get("source_profiles", [])
        if item.get("context", {}).get("mode") == "written"
    ]
    rows = [_feature_row(item["features"]) for item in written]
    words = round(
        sum(
            float(item["features"].get("word_count", 0))
            * max(float(item.get("weight", 1.0)), 0.0)
            for item in written
        )
    )
    return rows, words


def _comparison_rows(
    paths: Iterable[Path], minimum_document_words: int = 100
) -> Tuple[List[List[float]], int, Dict[str, Any]]:
    rows: List[List[float]] = []
    shingle_profiles = []
    hashes: List[str] = []
    words = 0
    skipped = {
        "unreadable": 0,
        "spoken_register": 0,
        "too_short": 0,
        "near_duplicate": 0,
    }
    for path in paths:
        try:
            kind, _, text = read_source(str(path))
        except (OSError, UnicodeError, RuntimeError):
            skipped["unreadable"] += 1
            continue
        if kind == "transcript":
            skipped["spoken_register"] += 1
            continue
        features = extract_linguistic_features(text)
        document_words = int(features["word_count"])
        if document_words < minimum_document_words:
            skipped["too_short"] += 1
            continue
        words_for_shingles = text.lower().split()
        shingles = {
            tuple(words_for_shingles[index : index + 5])
            for index in range(max(len(words_for_shingles) - 4, 0))
        }
        if any(
            len(shingles & prior) / max(len(shingles | prior), 1) >= 0.85
            for prior in shingle_profiles
        ):
            skipped["near_duplicate"] += 1
            continue
        shingle_profiles.append(shingles)
        hashes.append(content_hash(text))
        rows.append(_feature_row(features))
        words += document_words
    return rows, words, {"skipped": skipped, "content_hashes": sorted(hashes)}


def training_reliability(
    author_documents: int,
    author_words: int,
    comparison_documents: int,
    comparison_words: int,
) -> Dict[str, Any]:
    hard_failures = []
    warnings = []
    for label, documents, words in (
        ("author", author_documents, author_words),
        ("comparison", comparison_documents, comparison_words),
    ):
        if documents < HARD_MINIMUM_DOCUMENTS_PER_CLASS:
            hard_failures.append(
                "{} corpus has {} documents; at least {} are required to train.".format(
                    label, documents, HARD_MINIMUM_DOCUMENTS_PER_CLASS
                )
            )
        elif documents < RELIABLE_MINIMUM_DOCUMENTS_PER_CLASS:
            warnings.append(
                "{} corpus has {} documents; {} are recommended for a reliable model.".format(
                    label, documents, RELIABLE_MINIMUM_DOCUMENTS_PER_CLASS
                )
            )
        if words < HARD_MINIMUM_WORDS_PER_CLASS:
            hard_failures.append(
                "{} corpus has {} words; at least {} are required to train.".format(
                    label, words, HARD_MINIMUM_WORDS_PER_CLASS
                )
            )
        elif words < RELIABLE_MINIMUM_WORDS_PER_CLASS:
            warnings.append(
                "{} corpus has {} words; {} are recommended for a reliable model.".format(
                    label, words, RELIABLE_MINIMUM_WORDS_PER_CLASS
                )
            )
    smaller = min(author_documents, comparison_documents)
    larger = max(author_documents, comparison_documents)
    if smaller and larger / smaller > 2:
        warnings.append(
            "The class sizes differ by more than 2:1; use a better-matched comparison corpus."
        )
    if hard_failures:
        status = "insufficient_data"
    elif warnings:
        status = "low_confidence"
    else:
        status = "reliable"
    return {
        "status": status,
        "can_train": not hard_failures,
        "requires_low_confidence_acceptance": bool(warnings and not hard_failures),
        "hard_failures": hard_failures,
        "warnings": warnings,
        "thresholds": {
            "hard_minimum_documents_per_class": HARD_MINIMUM_DOCUMENTS_PER_CLASS,
            "hard_minimum_words_per_class": HARD_MINIMUM_WORDS_PER_CLASS,
            "reliable_minimum_documents_per_class": (
                RELIABLE_MINIMUM_DOCUMENTS_PER_CLASS
            ),
            "reliable_minimum_words_per_class": RELIABLE_MINIMUM_WORDS_PER_CLASS,
        },
    }


def _require_sklearn():
    try:
        import sklearn
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import balanced_accuracy_score, roc_auc_score
        from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:
        raise MLDependencyError(
            "ML training requires the optional dependency. Install "
            "content-creator[ml] and retry."
        ) from exc
    return {
        "sklearn": sklearn,
        "LogisticRegression": LogisticRegression,
        "balanced_accuracy_score": balanced_accuracy_score,
        "roc_auc_score": roc_auc_score,
        "StratifiedKFold": StratifiedKFold,
        "cross_validate": cross_validate,
        "train_test_split": train_test_split,
        "Pipeline": Pipeline,
        "StandardScaler": StandardScaler,
    }


def train_voice_ml_model(
    root: Path,
    voice_id: str,
    voice_version: Optional[str],
    comparison_paths: Iterable[Path],
    *,
    accept_low_confidence: bool = False,
    replace: bool = False,
) -> Dict[str, Any]:
    resolved, signature = load_voice_signature(root, voice_id, voice_version)
    author_rows, author_words = _author_rows(signature)
    comparison_rows, comparison_words, comparison_audit = _comparison_rows(
        comparison_paths
    )
    reliability = training_reliability(
        len(author_rows), author_words, len(comparison_rows), comparison_words
    )
    preflight = {
        "author": {"documents": len(author_rows), "weighted_words": author_words},
        "comparison": {
            "documents": len(comparison_rows),
            "words": comparison_words,
            "skipped": comparison_audit["skipped"],
        },
        "reliability": reliability,
    }
    if not reliability["can_train"]:
        return {
            "status": "insufficient_data",
            "trained": False,
            "voice_id": voice_id,
            "voice_version": resolved["version"],
            "preflight": preflight,
        }
    if reliability["requires_low_confidence_acceptance"] and not accept_low_confidence:
        return {
            "status": "warning_confirmation_required",
            "trained": False,
            "voice_id": voice_id,
            "voice_version": resolved["version"],
            "preflight": preflight,
            "next_step": (
                "Add more independent matched documents, or repeat with "
                "--accept-low-confidence after reviewing the warnings."
            ),
        }

    path = ml_model_path(root, voice_id, resolved["version"])
    if path.exists() and not replace:
        raise StorageError(
            "An ML model already exists for {}@{}. Use --replace to retrain it.".format(
                voice_id, resolved["version"]
            )
        )

    ml = _require_sklearn()
    X = author_rows + comparison_rows
    y = [1] * len(author_rows) + [0] * len(comparison_rows)
    pipeline = ml["Pipeline"](
        [
            ("scaler", ml["StandardScaler"]()),
            (
                "classifier",
                ml["LogisticRegression"](
                    class_weight="balanced",
                    max_iter=2000,
                    random_state=42,
                    solver="liblinear",
                ),
            ),
        ]
    )
    train_X, test_X, train_y, test_y = ml["train_test_split"](
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    pipeline.fit(train_X, train_y)
    test_scores = pipeline.predict_proba(test_X)[:, 1]
    test_predictions = pipeline.predict(test_X)
    folds = min(5, len(author_rows), len(comparison_rows))
    cv = ml["StratifiedKFold"](
        n_splits=folds, shuffle=True, random_state=42
    )
    cross_validation = ml["cross_validate"](
        pipeline,
        X,
        y,
        cv=cv,
        scoring={"balanced_accuracy": "balanced_accuracy", "roc_auc": "roc_auc"},
    )
    pipeline.fit(X, y)
    scaler = pipeline.named_steps["scaler"]
    classifier = pipeline.named_steps["classifier"]
    artifact = {
        "schema_version": "1.0",
        "framework": ML_FRAMEWORK,
        "framework_version": ML_FRAMEWORK_VERSION,
        "voice_id": voice_id,
        "voice_version": resolved["version"],
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "feature_schema": {
            "linguistic_framework_version": signature.get("framework_version"),
            "feature_names": list(MODEL_FEATURE_NAMES),
        },
        "preprocessing": {
            "type": "standard-scaler",
            "mean": [round(float(value), 12) for value in scaler.mean_],
            "scale": [round(float(value), 12) for value in scaler.scale_],
        },
        "classifier": {
            "type": "logistic-regression",
            "class_weight": "balanced",
            "intercept": round(float(classifier.intercept_[0]), 12),
            "coefficients": [
                round(float(value), 12) for value in classifier.coef_[0]
            ],
            "decision_threshold": 0.5,
            "sklearn_version": ml["sklearn"].__version__,
        },
        "training_data": {
            "author_documents": len(author_rows),
            "author_weighted_words": author_words,
            "author_feature_fingerprint": _fingerprint(author_rows),
            "comparison_documents": len(comparison_rows),
            "comparison_words": comparison_words,
            "comparison_feature_fingerprint": _fingerprint(comparison_rows),
            "comparison_content_fingerprint": "sha256:"
            + hashlib.sha256(
                "\n".join(comparison_audit["content_hashes"]).encode("utf-8")
            ).hexdigest(),
        },
        "evaluation": {
            "holdout_fraction": 0.2,
            "holdout_balanced_accuracy": round(
                float(ml["balanced_accuracy_score"](test_y, test_predictions)), 4
            ),
            "holdout_roc_auc": round(
                float(ml["roc_auc_score"](test_y, test_scores)), 4
            ),
            "cross_validation_folds": folds,
            "cross_validation_balanced_accuracy_mean": round(
                float(cross_validation["test_balanced_accuracy"].mean()), 4
            ),
            "cross_validation_balanced_accuracy_std": round(
                float(cross_validation["test_balanced_accuracy"].std()), 4
            ),
            "cross_validation_roc_auc_mean": round(
                float(cross_validation["test_roc_auc"].mean()), 4
            ),
            "cross_validation_roc_auc_std": round(
                float(cross_validation["test_roc_auc"].std()), 4
            ),
            "claim_limit": (
                "Random held-out and cross-validation results are indicative. "
                "A separately sealed, topic- and time-aware evaluation remains "
                "necessary before treating the model as dependable."
            ),
        },
        "reliability": reliability,
        "claim_limit": (
            "The classifier score is an advisory comparison with the supplied "
            "corpora, not an authorship probability or identity determination."
        ),
    }
    RunStore._atomic_text(path, json.dumps(artifact, indent=2))
    return {
        "status": "trained",
        "trained": True,
        "voice_id": voice_id,
        "voice_version": resolved["version"],
        "model_path": str(path.relative_to(root.resolve())),
        "preflight": preflight,
        "evaluation": artifact["evaluation"],
        "activation": (
            "Training does not enable ML assessment. Set voice_assessment.mode to ml "
            "and voice_assessment.enabled to true after reviewing the evaluation."
        ),
    }


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
            "framework": ML_FRAMEWORK,
            "framework_version": ML_FRAMEWORK_VERSION,
            "status": "ml_model_unavailable",
            "voice_id": voice_id,
            "voice_version": voice_version,
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
            "framework": ML_FRAMEWORK,
            "framework_version": ML_FRAMEWORK_VERSION,
            "status": "insufficient_draft",
            "voice_id": voice_id,
            "voice_version": voice_version,
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
        for value, mean, scale in zip(row, means, scales)
    ]
    contributions = [
        value * float(coefficient)
        for value, coefficient in zip(standardised, coefficients)
    ]
    logit = float(artifact["classifier"]["intercept"]) + sum(contributions)
    score = 1.0 / (1.0 + math.exp(-max(min(logit, 709), -709)))
    threshold = float(artifact["classifier"]["decision_threshold"])
    ranked = sorted(
        zip(names, contributions), key=lambda item: abs(item[1]), reverse=True
    )[:5]
    return {
        "schema_version": "1.0",
        "framework": ML_FRAMEWORK,
        "framework_version": ML_FRAMEWORK_VERSION,
        "status": "ml_above_threshold" if score >= threshold else "ml_below_threshold",
        "voice_id": voice_id,
        "voice_version": voice_version,
        "draft": {"word_count": word_count},
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
