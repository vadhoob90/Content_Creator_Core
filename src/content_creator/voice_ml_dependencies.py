"""Load optional statistical voice-score training dependencies."""

from __future__ import annotations

from typing import Any, Dict


class MLDependencyError(RuntimeError):
    pass


def require_sklearn() -> Dict[str, Any]:
    try:
        import sklearn
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import balanced_accuracy_score, roc_auc_score
        from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:
        raise MLDependencyError(
            "ML training requires the optional dependency. Install content-creator[ml] and retry."
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
