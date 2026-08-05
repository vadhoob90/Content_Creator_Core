"""Public stateful façade for runtime diagnostics."""

from __future__ import annotations

from pathlib import Path
from time import monotonic
from typing import Any, Dict, Optional
from uuid import uuid4

from ..storage import RunStore
from .candidates import decide as decide_candidates
from .candidates import link_issue as link_candidate_issue
from .candidates import preflight as candidate_preflight
from .models import DiagnosticEvent
from .policy import classify as classify_exception
from .policy import fingerprint as failure_fingerprint
from .policy import is_retryable as is_retryable_exception
from .policy import phase as lifecycle_phase
from .policy import safe_error_detail
from .policy import sanitise as sanitise_detail
from .recording import append_event, invocation_directory, write_invocation_summary


class RuntimeDiagnostics:
    """Collect runtime evidence and prepare sanitised support candidates."""

    def __init__(self, root: Path, enabled: bool = True):
        """Initialize the runtime diagnostics."""
        self.root = root.resolve()
        self.store = RunStore(self.root)
        self.enabled = enabled
        self.run_id: Optional[str] = None
        self.invocation_id: Optional[str] = None
        self.content_session_id: Optional[str] = None

    def begin_invocation(self, content_session_id: Optional[str] = None) -> str:
        """Begin invocation."""
        self.run_id = None
        self.invocation_id = uuid4().hex[:12]
        self.content_session_id = content_session_id
        return self.invocation_id

    def bind_run(self, run_id: str, content_session_id: str) -> None:
        """Return the bind run."""
        self.run_id = run_id
        self.content_session_id = content_session_id

    @staticmethod
    def timer() -> float:
        """Return the timer."""
        return monotonic()

    def attempt_started(
        self,
        *,
        role: str,
        attempt: int,
        provider: str,
        model: str,
    ) -> None:
        """Return the attempt started."""
        self._record(
            DiagnosticEvent(
                run_id=self.run_id,
                invocation_id=self.invocation_id,
                content_session_id=self.content_session_id,
                event="agent_attempt_started",
                phase=lifecycle_phase(role),
                role=role,
                attempt=attempt,
                provider=provider,
                model=model,
                outcome="started",
            )
        )

    def attempt_completed(
        self,
        *,
        role: str,
        attempt: int,
        provider: str,
        model: str,
        started_at: float,
    ) -> None:
        """Return the attempt completed."""
        self._record(
            DiagnosticEvent(
                run_id=self.run_id,
                invocation_id=self.invocation_id,
                content_session_id=self.content_session_id,
                event="agent_attempt_recovered" if attempt > 1 else "agent_attempt_completed",
                phase=lifecycle_phase(role),
                role=role,
                attempt=attempt,
                provider=provider,
                model=model,
                duration_ms=max(0, int((monotonic() - started_at) * 1000)),
                outcome="recovered" if attempt > 1 else "succeeded",
            )
        )

    def attempt_failed(
        self,
        exc: Exception,
        *,
        role: str,
        attempt: int,
        provider: str,
        model: str,
        started_at: float,
        retrying: bool,
    ) -> Dict[str, Any]:
        """Return the attempt failed."""
        classification = classify_exception(exc)
        event = DiagnosticEvent(
            run_id=self.run_id,
            invocation_id=self.invocation_id,
            content_session_id=self.content_session_id,
            event="agent_attempt_failed",
            phase=lifecycle_phase(role),
            role=role,
            attempt=attempt,
            provider=provider,
            model=model,
            duration_ms=max(0, int((monotonic() - started_at) * 1000)),
            outcome="retrying" if retrying else "failed",
            error_type=exc.__class__.__name__,
            safe_detail=safe_error_detail(self.root, exc, classification),
            fingerprint=failure_fingerprint(
                role, classification["issue_type"], exc.__class__.__name__
            ),
            **classification,
        )
        self._record(event)
        return event.model_dump(mode="json")

    def record_terminal_failure(self, exc: Exception, *, phase: str = "orchestration") -> None:
        """Record terminal failure."""
        classification = classify_exception(exc)
        self._record(
            DiagnosticEvent(
                run_id=self.run_id,
                invocation_id=self.invocation_id,
                content_session_id=self.content_session_id,
                event="run_failed",
                phase=phase,
                outcome="failed",
                error_type=exc.__class__.__name__,
                safe_detail=safe_error_detail(self.root, exc, classification),
                fingerprint=failure_fingerprint(
                    phase, classification["issue_type"], exc.__class__.__name__
                ),
                **classification,
            )
        )

    def record_invocation_failure(self, exc: Exception) -> Path:
        """Record invocation failure."""
        self.record_terminal_failure(exc, phase="initialisation")
        classification = classify_exception(exc)
        return write_invocation_summary(
            self.root,
            self.invocation_id,
            exc,
            classification,
            safe_error_detail(self.root, exc, classification),
        )

    def is_retryable(self, exc: Exception) -> bool:
        """Return whether retryable."""
        return is_retryable_exception(exc)

    def classify(self, exc: Exception) -> Dict[str, Any]:
        """Classify runtime diagnostics."""
        return classify_exception(exc)

    def sanitise(self, detail: str) -> str:
        """Return the sanitise."""
        return sanitise_detail(self.root, detail)

    def preflight(self, run_id: str) -> Dict[str, Any]:
        """Return the preflight."""
        return candidate_preflight(self.store, run_id)

    def decide(self, run_id: str, decision: str) -> Dict[str, Any]:
        """Return the decide."""
        return decide_candidates(self.store, run_id, decision)

    def link_issue(self, run_id: str, issue_url: str) -> Dict[str, Any]:
        """Link issue."""
        return link_candidate_issue(self.store, run_id, issue_url)

    def _record(self, event: DiagnosticEvent) -> None:
        """Record runtime diagnostics."""
        append_event(
            self.store,
            enabled=self.enabled,
            run_id=self.run_id,
            invocation_dir=invocation_directory(self.root, self.invocation_id),
            event=event,
        )
