"""Runtime diagnostics public façade."""

from .diagnostic_models import DiagnosticDecisionRequired as DiagnosticDecisionRequired
from .diagnostic_models import DiagnosticEvent as DiagnosticEvent
from .diagnostic_models import SupportCandidate as SupportCandidate
from .diagnostic_support import DiagnosticSupport


class RuntimeDiagnostics(DiagnosticSupport):
    """Collect runtime evidence and prepare sanitised support candidates."""
