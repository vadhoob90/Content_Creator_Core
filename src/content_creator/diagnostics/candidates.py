"""Build, persist, and resolve sanitised Core support candidates."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List

from ..domain import RunState, utc_now
from ..storage import RunStore
from .models import DiagnosticEvent, SupportCandidate


def preflight(store: RunStore, run_id: str) -> Dict[str, Any]:
    """Create the publication-boundary diagnostic summary for a run."""
    state = store.load(run_id)
    events = list(_session_events(store, state.work_order.content_session_id))
    candidates = _candidates(store, state, events)
    store.write_artifact(run_id, "diagnostic-summary.json", _summary(state, events, candidates))
    _write_candidates(store, run_id, candidates)
    requires_decision = any(item.status in {"deferred", "presented"} for item in candidates)
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "content_session_id": state.work_order.content_session_id,
        "status": "awaiting_diagnostic_decision" if requires_decision else "clear",
        "requires_diagnostic_decision": requires_decision,
        "diagnostic_summary": "runs/{}/diagnostic-summary.json".format(run_id),
        "support_candidate": (
            "runs/{}/support-candidate.json".format(run_id) if candidates else None
        ),
        "candidates": [item.model_dump(mode="json") for item in candidates],
    }


def decide(store: RunStore, run_id: str, decision: str) -> Dict[str, Any]:
    """Record the author's publication-boundary diagnostic decision."""
    if decision not in {"publish-only", "prepare-issue"}:
        raise ValueError("Unknown diagnostic decision: {}".format(decision))
    result = preflight(store, run_id)
    path = store.run_dir(run_id) / "support-candidate.json"
    candidates = [SupportCandidate.model_validate(item) for item in result["candidates"]]
    status = "dismissed" if decision == "publish-only" else "issue_requested"
    for candidate in candidates:
        if candidate.status in {"deferred", "presented"}:
            candidate.status = status
            candidate.updated_at = utc_now().isoformat()
    _write_candidates(store, run_id, candidates)
    return {
        **result,
        "status": "decision_recorded",
        "requires_diagnostic_decision": False,
        "decision": decision,
        "support_candidate": (str(path.relative_to(store.root)) if path.exists() else None),
        "candidates": [item.model_dump(mode="json") for item in candidates],
    }


def link_issue(store: RunStore, run_id: str, issue_url: str) -> Dict[str, Any]:
    """Attach a created GitHub issue to an issue-requested candidate."""
    if not re.fullmatch(r"https://(?:www\.)?github\.com/[^/\s]+/[^/\s]+/issues/\d+", issue_url):
        raise ValueError("issue_url must identify a GitHub issue")
    path = store.run_dir(run_id) / "support-candidate.json"
    if not path.exists():
        raise ValueError("Run has no support candidate")
    candidates = [
        SupportCandidate.model_validate(item)
        for item in json.loads(path.read_text(encoding="utf-8"))
    ]
    linked = False
    for candidate in candidates:
        if candidate.status == "issue_requested":
            candidate.status = "issue_raised"
            candidate.issue_url = issue_url
            candidate.updated_at = utc_now().isoformat()
            linked = True
    if not linked:
        raise ValueError("Run has no issue-requested support candidate")
    _write_candidates(store, run_id, candidates)
    return {"run_id": run_id, "status": "issue_raised", "issue_url": issue_url}


def _summary(
    state: RunState,
    events: List[DiagnosticEvent],
    candidates: List[SupportCandidate],
) -> Dict[str, Any]:
    failures = [item for item in events if item.event.endswith("failed")]
    recovered_roles = {item.role for item in events if item.event == "agent_attempt_recovered"}
    return {
        "schema_version": "1.0",
        "run_id": state.id,
        "content_session_id": state.work_order.content_session_id,
        "run_status": state.status.value,
        "operational_issue_count": len(failures),
        "recovered_issue_count": sum(
            1 for item in failures if item.role in recovered_roles or item.outcome == "retrying"
        ),
        "fatal_issue_count": sum(1 for item in failures if item.event == "run_failed"),
        "support_candidate_count": len(candidates),
        "attention_required": any(item.status in {"deferred", "presented"} for item in candidates),
    }


def _candidates(
    store: RunStore,
    state: RunState,
    events: List[DiagnosticEvent],
) -> List[SupportCandidate]:
    grouped: Dict[str, List[DiagnosticEvent]] = {}
    support_events = [item for item in events if item.support_worthy]
    if any(item.event == "agent_attempt_failed" for item in support_events):
        support_events = [item for item in support_events if item.event != "run_failed"]
    for event in support_events:
        if event.fingerprint:
            grouped.setdefault(event.fingerprint, []).append(event)
    existing = _existing_candidates(store, state.work_order.content_session_id)
    recovered_pairs = {
        (event.run_id, event.role) for event in events if event.event == "agent_attempt_recovered"
    }
    return [
        _candidate(state, fingerprint, items, existing.get(fingerprint), recovered_pairs)
        for fingerprint, items in sorted(grouped.items())
    ]


def _candidate(
    state: RunState,
    fingerprint: str,
    items: List[DiagnosticEvent],
    prior: SupportCandidate | None,
    recovered_pairs: set[tuple[str | None, str | None]],
) -> SupportCandidate:
    latest = items[-1]
    recovered = all(
        item.outcome == "retrying" or (item.run_id, item.role) in recovered_pairs for item in items
    )
    occurrence_keys = {item.run_id or item.invocation_id or item.id for item in items}
    return SupportCandidate(
        content_session_id=state.work_order.content_session_id,
        fingerprint=fingerprint,
        title=_title(latest),
        summary=_candidate_summary(latest, recovered),
        severity=latest.severity or "warning",
        recovered=recovered,
        occurrences=len(occurrence_keys),
        run_ids=sorted({item.run_id for item in items if item.run_id}),
        status=prior.status if prior else "deferred",
        issue_url=prior.issue_url if prior else None,
        safe_evidence={
            "phase": latest.phase,
            "role": latest.role,
            "attempts": max((item.attempt or 1 for item in items), default=1),
            "error_type": latest.error_type,
            "issue_type": latest.issue_type,
        },
        created_at=prior.created_at if prior else utc_now().isoformat(),
    )


def _existing_candidates(store: RunStore, content_session_id: str) -> Dict[str, SupportCandidate]:
    result: Dict[str, SupportCandidate] = {}
    for state in _session_states(store, content_session_id):
        path = store.run_dir(state.id) / "support-candidate.json"
        if not path.exists():
            continue
        try:
            for item in json.loads(path.read_text(encoding="utf-8")):
                candidate = SupportCandidate.model_validate(item)
                current = result.get(candidate.fingerprint)
                if current is None or candidate.updated_at > current.updated_at:
                    result[candidate.fingerprint] = candidate
        except (OSError, ValueError):
            continue
    return result


def _session_states(store: RunStore, content_session_id: str) -> Iterable[RunState]:
    for path in store.runs_dir.glob("*/state.json"):
        try:
            state = RunState.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if state.work_order.content_session_id == content_session_id:
            yield state


def _session_events(store: RunStore, content_session_id: str) -> Iterable[DiagnosticEvent]:
    for state in _session_states(store, content_session_id):
        path = store.run_dir(state.id) / "diagnostics.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                yield DiagnosticEvent.model_validate_json(line)
            except ValueError:
                continue


def _write_candidates(store: RunStore, run_id: str, candidates: List[SupportCandidate]) -> None:
    if not candidates:
        return
    store.write_artifact(
        run_id,
        "support-candidate.json",
        [item.model_dump(mode="json") for item in candidates],
    )
    sections = [
        "# Core support candidates",
        "",
        "This report is sanitised and contains no draft or prompt content.",
    ]
    for candidate in candidates:
        sections.extend(
            [
                "",
                "## {}".format(candidate.title),
                "",
                "- Fingerprint: `{}`".format(candidate.fingerprint),
                "- Severity: `{}`".format(candidate.severity),
                "- Recovered: `{}`".format(str(candidate.recovered).lower()),
                "- Occurrences: `{}`".format(candidate.occurrences),
                "- Status: `{}`".format(candidate.status),
                "",
                candidate.summary,
            ]
        )
    store.write_artifact(run_id, "support-candidate.md", "\n".join(sections))


def _title(event: DiagnosticEvent) -> str:
    labels = {
        "invalid_structured_output": "Structured agent output failed validation",
        "orchestration_failure": "Core orchestration failed",
        "unexpected_exception": "Unexpected Core exception",
    }
    return labels.get(event.issue_type or "", "Core runtime issue")


def _candidate_summary(event: DiagnosticEvent, recovered: bool) -> str:
    outcome = (
        "The run recovered and continued."
        if recovered
        else "The issue prevented or degraded the requested operation."
    )
    return "{} encountered {} during {}. {}".format(
        event.role or "Core",
        event.issue_type or "an operational issue",
        event.phase,
        outcome,
    )
