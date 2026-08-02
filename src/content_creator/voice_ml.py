"""Statistical voice scoring public façade.

Training/preflight and inference are separated so callers can depend on the
smallest responsibility while legacy imports remain stable.
"""

from .voice_ml_inference import assess_with_ml_artifact as assess_with_ml_artifact
from .voice_ml_training import (
    HARD_MINIMUM_DOCUMENTS_PER_CLASS as HARD_MINIMUM_DOCUMENTS_PER_CLASS,
)
from .voice_ml_training import (
    HARD_MINIMUM_WORDS_PER_CLASS as HARD_MINIMUM_WORDS_PER_CLASS,
)
from .voice_ml_training import (
    ML_FRAMEWORK as ML_FRAMEWORK,
)
from .voice_ml_training import (
    ML_FRAMEWORK_VERSION as ML_FRAMEWORK_VERSION,
)
from .voice_ml_training import (
    MODEL_FEATURE_NAMES as MODEL_FEATURE_NAMES,
)
from .voice_ml_training import (
    RELIABLE_MINIMUM_DOCUMENTS_PER_CLASS as RELIABLE_MINIMUM_DOCUMENTS_PER_CLASS,
)
from .voice_ml_training import (
    RELIABLE_MINIMUM_WORDS_PER_CLASS as RELIABLE_MINIMUM_WORDS_PER_CLASS,
)
from .voice_ml_training import (
    MLDependencyError as MLDependencyError,
)
from .voice_ml_training import (
    load_voice_signature as load_voice_signature,
)
from .voice_ml_training import (
    ml_model_path as ml_model_path,
)
from .voice_ml_training import (
    train_voice_ml_model as train_voice_ml_model,
)
from .voice_ml_training import (
    training_reliability as training_reliability,
)
