from __future__ import annotations

import json
import re
from pathlib import Path
from time import monotonic
from typing import Any, Dict, Optional
from uuid import uuid4

from .diagnostic_models import DiagnosticEvent
from .storage import RunStore


class DiagnosticRecorder:
    """Record diagnostic events; support workflow supplies persistence helpers."""

    def _record(self, event: DiagnosticEvent) -> None:
        raise NotImplementedError

    def _safe_error_detail(self, exc: Exception, classification: Dict[str, Any]) -> str:
        raise NotImplementedError

    def _invocation_dir(self) -> Path:
        raise NotImplementedError

    @staticmethod
    def _fingerprint(component: str, issue_type: str, error_type: str) -> str:
        raise NotImplementedError

    @staticmethod
    def _phase(role: str) -> str:
        raise NotImplementedError

    """Fail-safe, workspace-local operational diagnostics."""

    RETRYABLE_PROVIDER_PATTERNS = (
        "timeout",
        "timed out",
        "rate limit",
        "temporar",
        "connection",
        "provider down",
        "service unavailable",
    )
    SENSITIVE_PATTERNS = (
        re.compile(r"(?i)(api[_ -]?key|token|secret|password)\s*[:=]\s*\S+"),
        re.compile(r"/Users/[^/\s]+"),
        re.compile(r"/home/[^/\s]+"),
    )

    def __init__(self, root: Path, enabled: bool = True):
        self.root = root.resolve()
        self.store = RunStore(self.root)
        self.enabled = enabled
        self.run_id: Optional[str] = None
        self.invocation_id: Optional[str] = None
        self.content_session_id: Optional[str] = None

    def begin_invocation(self, content_session_id: Optional[str] = None) -> str:
        self.run_id = None
        self.invocation_id = uuid4().hex[:12]
        self.content_session_id = content_session_id
        return self.invocation_id

    def bind_run(self, run_id: str, content_session_id: str) -> None:
        self.run_id = run_id
        self.content_session_id = content_session_id

    @staticmethod
    def timer() -> float:
        return monotonic()

    def attempt_started(
        self,
        *,
        role: str,
        attempt: int,
        provider: str,
        model: str,
    ) -> None:
        self._record(
            DiagnosticEvent(
                run_id=self.run_id,
                invocation_id=self.invocation_id,
                content_session_id=self.content_session_id,
                event="agent_attempt_started",
                phase=self._phase(role),
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
        self._record(
            DiagnosticEvent(
                run_id=self.run_id,
                invocation_id=self.invocation_id,
                content_session_id=self.content_session_id,
                event=("agent_attempt_recovered" if attempt > 1 else "agent_attempt_completed"),
                phase=self._phase(role),
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
        classification = self.classify(exc)
        fingerprint = self._fingerprint(role, classification["issue_type"], exc.__class__.__name__)
        event = DiagnosticEvent(
            run_id=self.run_id,
            invocation_id=self.invocation_id,
            content_session_id=self.content_session_id,
            event="agent_attempt_failed",
            phase=self._phase(role),
            role=role,
            attempt=attempt,
            provider=provider,
            model=model,
            duration_ms=max(0, int((monotonic() - started_at) * 1000)),
            outcome="retrying" if retrying else "failed",
            error_type=exc.__class__.__name__,
            safe_detail=self._safe_error_detail(exc, classification),
            fingerprint=fingerprint,
            **classification,
        )
        self._record(event)
        return event.model_dump(mode="json")

    def record_terminal_failure(self, exc: Exception, *, phase: str = "orchestration") -> None:
        classification = self.classify(exc)
        fingerprint = self._fingerprint(phase, classification["issue_type"], exc.__class__.__name__)
        self._record(
            DiagnosticEvent(
                run_id=self.run_id,
                invocation_id=self.invocation_id,
                content_session_id=self.content_session_id,
                event="run_failed",
                phase=phase,
                outcome="failed",
                error_type=exc.__class__.__name__,
                safe_detail=self._safe_error_detail(exc, classification),
                fingerprint=fingerprint,
                **classification,
            )
        )

    def record_invocation_failure(self, exc: Exception) -> Path:
        self.record_terminal_failure(exc, phase="initialisation")
        directory = self._invocation_dir()
        summary = directory / "diagnostic-summary.json"
        classification = self.classify(exc)
        try:
            RunStore._atomic_text(
                summary,
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "invocation_id": self.invocation_id,
                        "status": "failed_before_run",
                        "error_type": exc.__class__.__name__,
                        "safe_detail": self._safe_error_detail(exc, classification),
                        **classification,
                    },
                    indent=2,
                ),
            )
            RunStore._atomic_text(
                self.root / ".content-creator" / "latest-invocation.json",
                json.dumps(
                    {
                        "invocation_id": self.invocation_id,
                        "diagnostic_summary": str(summary.relative_to(self.root)),
                    },
                    indent=2,
                ),
            )
        except OSError:
            pass
        return summary

    def is_retryable(self, exc: Exception) -> bool:
        if exc.__class__.__name__ == "AgentOutputError":
            return True
        if exc.__class__.__name__ != "ProviderError":
            return False
        detail = str(exc).lower()
        return any(item in detail for item in self.RETRYABLE_PROVIDER_PATTERNS)

    def classify(self, exc: Exception) -> Dict[str, Any]:
        name = exc.__class__.__name__
        detail = str(exc).lower()
        if name == "AgentOutputError":
            return {
                "classification": "core",
                "severity": "warning",
                "issue_type": "invalid_structured_output",
                "support_worthy": True,
            }
        if name == "ProviderError":
            if any(
                item in detail
                for item in (
                    "auth",
                    "login",
                    "api key",
                    "not installed",
                    "not available on path",
                )
            ):
                return {
                    "classification": "workspace_configuration",
                    "severity": "blocking",
                    "issue_type": "provider_configuration",
                    "support_worthy": False,
                }
            return {
                "classification": "provider",
                "severity": "blocking",
                "issue_type": "provider_failure",
                "support_worthy": False,
            }
        if name in {"ConfigurationError", "PackError", "RoutingError"}:
            return {
                "classification": "workspace_configuration",
                "severity": "blocking",
                "issue_type": "invalid_configuration",
                "support_worthy": False,
            }
        if name in {"OrchestrationError", "IdempotencyError"}:
            return {
                "classification": "content_workflow",
                "severity": "blocking",
                "issue_type": "workflow_validation",
                "support_worthy": False,
            }
        if name == "StorageError":
            return {
                "classification": "core",
                "severity": "blocking",
                "issue_type": "storage_failure",
                "support_worthy": True,
            }
        return {
            "classification": "core",
            "severity": "blocking",
            "issue_type": "unexpected_exception",
            "support_worthy": True,
        }
