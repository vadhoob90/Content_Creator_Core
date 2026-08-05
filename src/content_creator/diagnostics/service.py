"""Provide service contracts and behavior."""

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
        """Initialize the runtime diagnostics with its required state and collaborators.

        Args:
            root (Path): The workspace root directory.
            enabled (bool): Whether enabled behavior is enabled. Defaults to ``True``.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        self.root = root.resolve()
        self.store = RunStore(self.root)
        self.enabled = enabled
        self.run_id: Optional[str] = None
        self.invocation_id: Optional[str] = None
        self.content_session_id: Optional[str] = None

    def begin_invocation(self, content_session_id: Optional[str] = None) -> str:
        """Begin a diagnostic invocation for a content session.

        Args:
            content_session_id (Optional[str]): The stable identifier for the content
                session. Defaults to ``None``.

        Returns:
            str: The resulting text for begin invocation.
        """
        self.run_id = None
        self.invocation_id = uuid4().hex[:12]
        self.content_session_id = content_session_id
        return self.invocation_id

    def bind_run(self, run_id: str, content_session_id: str) -> None:
        """Bind a content run to the current diagnostic invocation.

        Args:
            run_id (str): The stable identifier for the content run.
            content_session_id (str): The stable identifier for the content session.

        Returns:
            None: The callable updates bind run state and returns no value.
        """
        self.run_id = run_id
        self.content_session_id = content_session_id

    @staticmethod
    def timer() -> float:
        """Return a monotonic timestamp for duration measurements.

        Returns:
            float: The resulting numeric value for timer.
        """
        return monotonic()

    def attempt_started(
        self,
        *,
        role: str,
        attempt: int,
        provider: str,
        model: str,
    ) -> None:
        """Record the start of an agent execution attempt.

        Args:
            role (str): The repository-owned agent role to execute.
            attempt (int): The one-based execution attempt number.
            provider (str): The provider implementation used for generation.
            model (str): The provider model identifier to use.

        Returns:
            None: The callable updates attempt started state and returns no value.
        """
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
        """Record successful completion of an agent execution attempt.

        Args:
            role (str): The repository-owned agent role to execute.
            attempt (int): The one-based execution attempt number.
            provider (str): The provider implementation used for generation.
            model (str): The provider model identifier to use.
            started_at (float): The started at value that controls attempt completed.

        Returns:
            None: The callable updates attempt completed state and returns no value.
        """
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
        """Record and classify a failed agent execution attempt.

        Args:
            exc (Exception): The exception raised by the failed operation.
            role (str): The repository-owned agent role to execute.
            attempt (int): The one-based execution attempt number.
            provider (str): The provider implementation used for generation.
            model (str): The provider model identifier to use.
            started_at (float): The started at value that controls attempt failed.
            retrying (bool): Whether retrying behavior is enabled.

        Returns:
            Dict[str, Any]: The structured resulting data for attempt failed.
        """
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
        """Record the terminal failure.

        Args:
            exc (Exception): The exception raised by the failed operation.
            phase (str): The phase text processed when record terminal failure. Defaults to
                ``'orchestration'``.

        Returns:
            None: The callable updates record terminal failure state and returns no value.
        """
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

    def record_invocation_failure(self, exc: Exception) -> Optional[Path]:
        """Record the invocation failure.

        Args:
            exc (Exception): The exception raised by the failed operation.

        Returns:
            Optional[Path]: The persisted diagnostic summary path, or ``None`` when the
                summary could not be written.
        """
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
        """Return whether retryable satisfies the required condition.

        Args:
            exc (Exception): The exception raised by the failed operation.

        Returns:
            bool: Whether is retryable satisfies the documented condition.
        """
        return is_retryable_exception(exc)

    def classify(self, exc: Exception) -> Dict[str, Any]:
        """Classify the runtime diagnostics workflow.

        Args:
            exc (Exception): The exception raised by the failed operation.

        Returns:
            Dict[str, Any]: The structured classified data for value.
        """
        return classify_exception(exc)

    def sanitise(self, detail: str) -> str:
        """Sanitise the runtime diagnostics workflow.

        Args:
            detail (str): The detail text processed when sanitise.

        Returns:
            str: The resulting text for sanitise.
        """
        return sanitise_detail(self.root, detail)

    def preflight(self, run_id: str) -> Dict[str, Any]:
        """Return the preflight.

        Args:
            run_id (str): The stable identifier for the content run.

        Returns:
            Dict[str, Any]: The structured resulting data for preflight.
        """
        return candidate_preflight(self.store, run_id)

    def decide(self, run_id: str, decision: str) -> Dict[str, Any]:
        """Return the decide.

        Args:
            run_id (str): The stable identifier for the content run.
            decision (str): The decision text processed when decide.

        Returns:
            Dict[str, Any]: The structured resulting data for decide.
        """
        return decide_candidates(self.store, run_id, decision)

    def link_issue(self, run_id: str, issue_url: str) -> Dict[str, Any]:
        """Link the issue.

        Args:
            run_id (str): The stable identifier for the content run.
            issue_url (str): The issue url text processed when link issue.

        Returns:
            Dict[str, Any]: The structured resulting data for link issue.
        """
        return link_candidate_issue(self.store, run_id, issue_url)

    def _record(self, event: DiagnosticEvent) -> None:
        """Record the runtime diagnostics workflow.

        Args:
            event (DiagnosticEvent): The diagnostic or lifecycle event to record.

        Returns:
            None: The callable updates record state and returns no value.
        """
        append_event(
            self.store,
            enabled=self.enabled,
            run_id=self.run_id,
            invocation_dir=invocation_directory(self.root, self.invocation_id),
            event=event,
        )
