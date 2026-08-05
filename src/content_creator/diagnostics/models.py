"""Provide models contracts and behavior."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from ..domain import utc_now


class DiagnosticEvent(BaseModel):
    """Represent a diagnostic event."""

    schema_version: str = "1.0"
    id: str = Field(default_factory=lambda: uuid4().hex)
    at: str = Field(default_factory=lambda: utc_now().isoformat())
    run_id: Optional[str] = None
    invocation_id: Optional[str] = None
    content_session_id: Optional[str] = None
    event: str
    phase: str
    role: Optional[str] = None
    attempt: Optional[int] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    duration_ms: Optional[int] = None
    outcome: str
    classification: Optional[str] = None
    severity: Optional[str] = None
    issue_type: Optional[str] = None
    error_type: Optional[str] = None
    safe_detail: Optional[str] = None
    fingerprint: Optional[str] = None
    support_worthy: bool = False


class SupportCandidate(BaseModel):
    """Represent a support candidate."""

    schema_version: str = "1.0"
    content_session_id: str
    fingerprint: str
    title: str
    summary: str
    classification: str = "core"
    severity: str
    recovered: bool
    occurrences: int
    run_ids: List[str] = Field(default_factory=list)
    status: str = "deferred"
    issue_url: Optional[str] = None
    safe_evidence: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: utc_now().isoformat())
    updated_at: str = Field(default_factory=lambda: utc_now().isoformat())


class DiagnosticDecisionRequired(RuntimeError):
    """Represent a diagnostic decision required."""

    def __init__(self, preflight: Dict[str, Any]):
        """Initialize the diagnostic decision required.

        Args:
            preflight (Dict[str, Any]): The preflight collection consumed while init.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        super().__init__("Recovered Core issues require a publication decision")
        self.preflight = preflight
