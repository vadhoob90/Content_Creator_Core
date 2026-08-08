"""Provide voice ML contracts and behavior.

Training/preflight and inference are separated so callers can depend on the smallest
responsibility while legacy imports remain stable.
"""

from .dependencies import MLDependencyError as MLDependencyError
from .inference import assess_with_ml_artifact as assess_with_ml_artifact
from .training import (
    HARD_MINIMUM_DOCUMENTS_PER_CLASS as HARD_MINIMUM_DOCUMENTS_PER_CLASS,
)
from .training import (
    HARD_MINIMUM_WORDS_PER_CLASS as HARD_MINIMUM_WORDS_PER_CLASS,
)
from .training import (
    ML_FRAMEWORK as ML_FRAMEWORK,
)
from .training import (
    ML_FRAMEWORK_VERSION as ML_FRAMEWORK_VERSION,
)
from .training import (
    MODEL_FEATURE_NAMES as MODEL_FEATURE_NAMES,
)
from .training import (
    RELIABLE_MINIMUM_DOCUMENTS_PER_CLASS as RELIABLE_MINIMUM_DOCUMENTS_PER_CLASS,
)
from .training import (
    RELIABLE_MINIMUM_WORDS_PER_CLASS as RELIABLE_MINIMUM_WORDS_PER_CLASS,
)
from .training import (
    load_voice_signature as load_voice_signature,
)
from .training import (
    ml_model_path as ml_model_path,
)
from .training import (
    train_voice_ml_model as train_voice_ml_model,
)
from .training import (
    training_reliability as training_reliability,
)

__all__ = [
    "HARD_MINIMUM_DOCUMENTS_PER_CLASS",
    "HARD_MINIMUM_WORDS_PER_CLASS",
    "MLDependencyError",
    "ML_FRAMEWORK",
    "ML_FRAMEWORK_VERSION",
    "MODEL_FEATURE_NAMES",
    "RELIABLE_MINIMUM_DOCUMENTS_PER_CLASS",
    "RELIABLE_MINIMUM_WORDS_PER_CLASS",
    "assess_with_ml_artifact",
    "load_voice_signature",
    "ml_model_path",
    "train_voice_ml_model",
    "training_reliability",
]
