"""Provide voice ml training capabilities."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .ingestion import content_hash, read_source
from .linguistics import extract_linguistic_features
from .storage import RunStore, StorageError
from .voice_ml_dependencies import require_sklearn
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


@dataclass(frozen=True)
class TrainingCorpus:
    """Collect labelled rows and metadata for voice-model training."""

    signature: Dict[str, Any]
    author_rows: List[List[float]]
    author_words: int
    comparison_rows: List[List[float]]
    comparison_words: int
    comparison_audit: Dict[str, Any]
    reliability: Dict[str, Any]


HARD_MINIMUM_DOCUMENTS_PER_CLASS = 10
HARD_MINIMUM_WORDS_PER_CLASS = 5000
RELIABLE_MINIMUM_DOCUMENTS_PER_CLASS = 40
RELIABLE_MINIMUM_WORDS_PER_CLASS = 20000


def _signature_path(root: Path, resolved: Dict[str, Any]) -> Path:
    """Return the signature path.

    Args:
        root (Path): The workspace root directory.
        resolved (Dict[str, Any]): The resolved collection consumed while signature
            path.

    Returns:
        Path: The resolved filesystem path for signature path.
    """
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
    """Load the voice signature.

    Args:
        root (Path): The workspace root directory.
        voice_id (str): The stable identifier for the selected voice.
        voice_version (Optional[str]): The immutable version of the selected voice
            profile.

    Returns:
        Tuple[Dict[str, Any], Dict[str, Any]]: The loaded voice signature values in
            their documented order.

    Raises:
        StorageError: If the storage operation cannot complete.
    """
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
    """Return the ml model path.

    Args:
        root (Path): The workspace root directory.
        voice_id (str): The stable identifier for the selected voice.
        voice_version (str): The immutable version of the selected voice profile.

    Returns:
        Path: The resolved filesystem path for ml model path.
    """
    return (
        root.resolve()
        / "profiles"
        / voice_id
        / "models"
        / voice_version
        / "logistic-regression.json"
    )


def _feature_row(features: Dict[str, Any]) -> List[float]:
    """Return the feature row.

    Args:
        features (Dict[str, Any]): The features collection consumed while feature row.

    Returns:
        List[float]: The resulting feature row values in their documented order.

    Raises:
        StorageError: If the storage operation cannot complete.
    """
    missing = [name for name in MODEL_FEATURE_NAMES if name not in features]
    if missing:
        raise StorageError(
            "Linguistic feature schema is not ML-compatible; missing: {}".format(", ".join(missing))
        )
    return [float(features[name]) for name in MODEL_FEATURE_NAMES]


def _fingerprint(rows: Iterable[List[float]]) -> str:
    """Return the fingerprint.

    Args:
        rows (Iterable[List[float]]): The rows value passed to fingerprint.

    Returns:
        str: The resulting text for fingerprint.
    """
    encoded = json.dumps(list(rows), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _author_rows(signature: Dict[str, Any]) -> Tuple[List[List[float]], int]:
    """Return the author rows.

    Args:
        signature (Dict[str, Any]): The statistical voice signature used for comparison.

    Returns:
        Tuple[List[List[float]], int]: The resulting author rows values in their
            documented order.
    """
    written = [
        item
        for item in signature.get("source_profiles", [])
        if item.get("context", {}).get("mode") == "written"
    ]
    rows = [_feature_row(item["features"]) for item in written]
    words = round(
        sum(
            float(item["features"].get("word_count", 0)) * max(float(item.get("weight", 1.0)), 0.0)
            for item in written
        )
    )
    return rows, words


def _comparison_rows(
    paths: Iterable[Path], minimum_document_words: int = 100
) -> Tuple[List[List[float]], int, Dict[str, Any]]:
    """Return the comparison rows.

    Build labelled comparison rows from eligible documents, rejecting samples that do
    not meet the minimum word threshold and retaining audit metadata for
    reproducibility.

    Args:
        paths (Iterable[Path]): The filesystem path for the paths.
        minimum_document_words (int): The minimum document words value that controls
            comparison rows. Defaults to ``100``.

    Returns:
        Tuple[List[List[float]], int, Dict[str, Any]]: The resulting comparison rows
            values in their documented order.
    """
    rows: List[List[float]] = []
    shingle_profiles: List[Set[tuple[str, ...]]] = []
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
    """Return the training reliability.

    Assess corpus balance, sample volume, and class representation to determine whether
    model training is statistically credible.

    Args:
        author_documents (int): The author documents value that controls training
            reliability.
        author_words (int): The author words value that controls training reliability.
        comparison_documents (int): The comparison documents value that controls
            training reliability.
        comparison_words (int): The comparison words value that controls training
            reliability.

    Returns:
        Dict[str, Any]: The structured resulting data for training reliability.
    """
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
            "reliable_minimum_documents_per_class": (RELIABLE_MINIMUM_DOCUMENTS_PER_CLASS),
            "reliable_minimum_words_per_class": RELIABLE_MINIMUM_WORDS_PER_CLASS,
        },
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
    """Train the voice ml model.

    Validate the training corpus, derive deterministic features, train the classifier,
    and persist its versioned artifact with reliability evidence.

    Args:
        root (Path): The workspace root directory.
        voice_id (str): The stable identifier for the selected voice.
        voice_version (Optional[str]): The immutable version of the selected voice
            profile.
        comparison_paths (Iterable[Path]): The filesystem path for the comparison paths.
        accept_low_confidence (bool): Whether accept low confidence behavior is enabled.
            Defaults to ``False``.
        replace (bool): Whether replace behavior is enabled. Defaults to ``False``.

    Returns:
        Dict[str, Any]: The structured trained data for voice ml model.

    Raises:
        StorageError: If the storage operation cannot complete.
    """
    resolved, signature = load_voice_signature(root, voice_id, voice_version)
    author_rows, author_words = _author_rows(signature)
    comparison_rows, comparison_words, comparison_audit = _comparison_rows(comparison_paths)
    reliability = training_reliability(
        len(author_rows), author_words, len(comparison_rows), comparison_words
    )
    preflight = _training_preflight(
        author_rows,
        author_words,
        comparison_rows,
        comparison_words,
        comparison_audit,
        reliability,
    )
    blocked = _blocked_training_result(
        voice_id,
        resolved["version"],
        preflight,
        reliability,
        accept_low_confidence,
    )
    if blocked:
        return blocked
    path = ml_model_path(root, voice_id, resolved["version"])
    if path.exists() and not replace:
        raise StorageError(
            f"An ML model already exists for {voice_id}@{resolved['version']}. "
            "Use --replace to retrain it."
        )
    trained = _train_classifier(author_rows, comparison_rows)
    artifact = _training_artifact(
        voice_id,
        resolved["version"],
        TrainingCorpus(
            signature=signature,
            author_rows=author_rows,
            author_words=author_words,
            comparison_rows=comparison_rows,
            comparison_words=comparison_words,
            comparison_audit=comparison_audit,
            reliability=reliability,
        ),
        trained,
    )
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
            "Training does not enable ML scoring. Run voice score-config for this "
            "voice with --enable --method ml after reviewing the evaluation."
        ),
    }


def _training_preflight(
    author_rows: List[List[float]],
    author_words: int,
    comparison_rows: List[List[float]],
    comparison_words: int,
    comparison_audit: Dict[str, Any],
    reliability: Dict[str, Any],
) -> Dict[str, Any]:
    """Return the training preflight.

    Args:
        author_rows (List[List[float]]): The author rows collection consumed while
            training preflight.
        author_words (int): The author words value that controls training preflight.
        comparison_rows (List[List[float]]): The comparison rows collection consumed
            while training preflight.
        comparison_words (int): The comparison words value that controls training
            preflight.
        comparison_audit (Dict[str, Any]): The comparison audit collection consumed
            while training preflight.
        reliability (Dict[str, Any]): The reliability collection consumed while training
            preflight.

    Returns:
        Dict[str, Any]: The structured resulting data for training preflight.
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


def _blocked_training_result(
    voice_id: str,
    voice_version: str,
    preflight: Dict[str, Any],
    reliability: Dict[str, Any],
    accept_low_confidence: bool,
) -> Optional[Dict[str, Any]]:
    """Return the blocked training result.

    Args:
        voice_id (str): The stable identifier for the selected voice.
        voice_version (str): The immutable version of the selected voice profile.
        preflight (Dict[str, Any]): The preflight collection consumed while blocked
            training result.
        reliability (Dict[str, Any]): The reliability collection consumed while blocked
            training result.
        accept_low_confidence (bool): Whether accept low confidence behavior is enabled.

    Returns:
        Optional[Dict[str, Any]]: The resulting blocked training result when available;
            otherwise ``None``.
    """
    if not reliability["can_train"]:
        return {
            "status": "insufficient_data",
            "trained": False,
            "voice_id": voice_id,
            "voice_version": voice_version,
            "preflight": preflight,
        }
    if reliability["requires_low_confidence_acceptance"] and not accept_low_confidence:
        return {
            "status": "warning_confirmation_required",
            "trained": False,
            "voice_id": voice_id,
            "voice_version": voice_version,
            "preflight": preflight,
            "next_step": (
                "Add more independent matched documents, or repeat with "
                "--accept-low-confidence after reviewing the warnings."
            ),
        }
    return None


def _train_classifier(
    author_rows: List[List[float]],
    comparison_rows: List[List[float]],
) -> Dict[str, Any]:
    """Train the classifier.

    Fit and evaluate the classifier with deterministic preprocessing, then return the
    model components and held-out performance metrics.

    Args:
        author_rows (List[List[float]]): The author rows collection consumed while train
            classifier.
        comparison_rows (List[List[float]]): The comparison rows collection consumed
            while train classifier.

    Returns:
        Dict[str, Any]: The structured trained data for classifier.
    """
    ml = require_sklearn()
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
    cv = ml["StratifiedKFold"](n_splits=folds, shuffle=True, random_state=42)
    cross_validation = ml["cross_validate"](
        pipeline,
        X,
        y,
        cv=cv,
        scoring={"balanced_accuracy": "balanced_accuracy", "roc_auc": "roc_auc"},
    )
    pipeline.fit(X, y)
    return {
        "ml": ml,
        "pipeline": pipeline,
        "test_y": test_y,
        "test_scores": test_scores,
        "test_predictions": test_predictions,
        "folds": folds,
        "cross_validation": cross_validation,
    }


def _training_artifact(
    voice_id: str,
    voice_version: str,
    corpus: TrainingCorpus,
    trained: Dict[str, Any],
) -> Dict[str, Any]:
    """Return the training artifact.

    Args:
        voice_id (str): The stable identifier for the selected voice.
        voice_version (str): The immutable version of the selected voice profile.
        corpus (TrainingCorpus): The source corpus used for analysis or training.
        trained (Dict[str, Any]): The trained collection consumed while training
            artifact.

    Returns:
        Dict[str, Any]: The structured resulting data for training artifact.
    """
    ml = trained["ml"]
    pipeline = trained["pipeline"]
    scaler = pipeline.named_steps["scaler"]
    classifier = pipeline.named_steps["classifier"]
    return {
        "schema_version": "1.0",
        "framework": ML_FRAMEWORK,
        "framework_version": ML_FRAMEWORK_VERSION,
        "voice_id": voice_id,
        "voice_version": voice_version,
        "trained_at": datetime.now(UTC).isoformat(),
        "feature_schema": {
            "linguistic_framework_version": corpus.signature.get("framework_version"),
            "feature_names": list(MODEL_FEATURE_NAMES),
        },
        "preprocessing": _preprocessing(scaler),
        "classifier": {
            "type": "logistic-regression",
            "class_weight": "balanced",
            "intercept": round(float(classifier.intercept_[0]), 12),
            "coefficients": [round(float(value), 12) for value in classifier.coef_[0]],
            "decision_threshold": 0.5,
            "sklearn_version": ml["sklearn"].__version__,
        },
        "training_data": _training_data(corpus),
        "evaluation": _evaluation(ml, trained),
        "reliability": corpus.reliability,
        "claim_limit": (
            "The classifier score is an advisory comparison with the supplied "
            "corpora, not an authorship probability or identity determination."
        ),
    }


def _preprocessing(scaler: Any) -> Dict[str, Any]:
    """Return the preprocessing.

    Args:
        scaler (Any): The scaler value passed to preprocessing.

    Returns:
        Dict[str, Any]: The structured resulting data for preprocessing.
    """
    return {
        "type": "standard-scaler",
        "mean": [round(float(value), 12) for value in scaler.mean_],
        "scale": [round(float(value), 12) for value in scaler.scale_],
    }


def _training_data(corpus: TrainingCorpus) -> Dict[str, Any]:
    """Return the training data.

    Args:
        corpus (TrainingCorpus): The source corpus used for analysis or training.

    Returns:
        Dict[str, Any]: The structured resulting data for training data.
    """
    comparison_digest = hashlib.sha256(
        "\n".join(corpus.comparison_audit["content_hashes"]).encode("utf-8")
    ).hexdigest()
    return {
        "author_documents": len(corpus.author_rows),
        "author_weighted_words": corpus.author_words,
        "author_feature_fingerprint": _fingerprint(corpus.author_rows),
        "comparison_documents": len(corpus.comparison_rows),
        "comparison_words": corpus.comparison_words,
        "comparison_feature_fingerprint": _fingerprint(corpus.comparison_rows),
        "comparison_content_fingerprint": "sha256:" + comparison_digest,
    }


def _evaluation(ml: Dict[str, Any], trained: Dict[str, Any]) -> Dict[str, Any]:
    """Return the evaluation.

    Args:
        ml (Dict[str, Any]): The ml collection consumed while evaluation.
        trained (Dict[str, Any]): The trained collection consumed while evaluation.

    Returns:
        Dict[str, Any]: The structured resulting data for evaluation.
    """
    cross_validation = trained["cross_validation"]
    return {
        "holdout_fraction": 0.2,
        "holdout_balanced_accuracy": round(
            float(ml["balanced_accuracy_score"](trained["test_y"], trained["test_predictions"])),
            4,
        ),
        "holdout_roc_auc": round(
            float(ml["roc_auc_score"](trained["test_y"], trained["test_scores"])), 4
        ),
        "cross_validation_folds": trained["folds"],
        "cross_validation_balanced_accuracy_mean": round(
            float(cross_validation["test_balanced_accuracy"].mean()), 4
        ),
        "cross_validation_balanced_accuracy_std": round(
            float(cross_validation["test_balanced_accuracy"].std()), 4
        ),
        "cross_validation_roc_auc_mean": round(float(cross_validation["test_roc_auc"].mean()), 4),
        "cross_validation_roc_auc_std": round(float(cross_validation["test_roc_auc"].std()), 4),
        "claim_limit": (
            "Random held-out and cross-validation results are indicative. "
            "A separately sealed, topic- and time-aware evaluation remains "
            "necessary before treating the model as dependable."
        ),
    }
