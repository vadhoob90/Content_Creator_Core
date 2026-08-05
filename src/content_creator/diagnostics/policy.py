"""Classify and sanitise runtime failures without persisting state."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Dict

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


def is_retryable(exc: Exception) -> bool:
    """Return whether the diagnostics retry policy permits another attempt."""
    if exc.__class__.__name__ == "AgentOutputError":
        return True
    if exc.__class__.__name__ != "ProviderError":
        return False
    detail = str(exc).lower()
    return any(item in detail for item in RETRYABLE_PROVIDER_PATTERNS)


def classify(exc: Exception) -> Dict[str, Any]:
    """Return the privacy-safe operational classification for an exception."""
    name = exc.__class__.__name__
    detail = str(exc).lower()
    if name == "AgentOutputError":
        return _classification("core", "warning", "invalid_structured_output", True)
    if name == "ProviderError":
        configuration_failure = any(
            item in detail
            for item in ("auth", "login", "api key", "not installed", "not available on path")
        )
        if configuration_failure:
            return _classification(
                "workspace_configuration", "blocking", "provider_configuration", False
            )
        return _classification("provider", "blocking", "provider_failure", False)
    if name in {"ConfigurationError", "PackError", "RoutingError"}:
        return _classification(
            "workspace_configuration", "blocking", "invalid_configuration", False
        )
    if name in {"OrchestrationError", "IdempotencyError"}:
        return _classification("content_workflow", "blocking", "workflow_validation", False)
    if name == "StorageError":
        return _classification("core", "blocking", "storage_failure", True)
    return _classification("core", "blocking", "unexpected_exception", True)


def _classification(
    classification: str,
    severity: str,
    issue_type: str,
    support_worthy: bool,
) -> Dict[str, Any]:
    """Return the classification."""
    return {
        "classification": classification,
        "severity": severity,
        "issue_type": issue_type,
        "support_worthy": support_worthy,
    }


def sanitise(root: Path, detail: str) -> str:
    """Remove workspace paths, home paths, and common secret assignments."""
    value = detail.replace(str(root), "<workspace>")
    value = SENSITIVE_PATTERNS[0].sub(r"\1=<redacted>", value)
    for pattern in SENSITIVE_PATTERNS[1:]:
        value = pattern.sub("<home>", value)
    return value[:800]


def safe_error_detail(root: Path, exc: Exception, classification: Dict[str, Any]) -> str:
    """Return a bounded safe detail suitable for diagnostic persistence."""
    if classification["issue_type"] == "invalid_structured_output":
        return "Structured response did not match the required schema."
    if classification["issue_type"] == "provider_failure":
        return "Provider request failed; raw provider output was omitted."
    return sanitise(root, str(exc))


def fingerprint(component: str, issue_type: str, error_type: str) -> str:
    """Create a stable privacy-safe failure fingerprint."""
    source = "{}|{}|{}".format(component, issue_type, error_type)
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]
    return "{}.{}.{}".format(component, issue_type, digest)


def phase(role: str) -> str:
    """Map an agent role to its user-facing lifecycle phase."""
    return {
        "researcher": "researching",
        "writer": "drafting",
        "critic": "reviewing",
        "learning-extractor": "publication",
        "perspective-extractor": "publication",
        "briefing-agent": "planning",
    }.get(role, role)
