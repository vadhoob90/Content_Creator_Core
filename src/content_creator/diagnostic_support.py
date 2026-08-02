from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .diagnostic_models import DiagnosticEvent, SupportCandidate
from .diagnostic_recording import DiagnosticRecorder
from .domain import RunState, utc_now


class DiagnosticSupport(DiagnosticRecorder):
    def preflight(self, run_id: str) -> Dict[str, Any]:
        state = self.store.load(run_id)
        events = list(self._session_events(state.work_order.content_session_id))
        candidates = self._candidates(state, events)
        summary = self._summary(state, events, candidates)
        self.store.write_artifact(run_id, "diagnostic-summary.json", summary)
        self._write_candidates(run_id, candidates)
        return {
            "schema_version": "1.0",
            "run_id": run_id,
            "content_session_id": state.work_order.content_session_id,
            "status": (
                "awaiting_diagnostic_decision"
                if any(item.status in {"deferred", "presented"} for item in candidates)
                else "clear"
            ),
            "requires_diagnostic_decision": any(
                item.status in {"deferred", "presented"} for item in candidates
            ),
            "diagnostic_summary": "runs/{}/diagnostic-summary.json".format(run_id),
            "support_candidate": (
                "runs/{}/support-candidate.json".format(run_id) if candidates else None
            ),
            "candidates": [item.model_dump(mode="json") for item in candidates],
        }

    def decide(self, run_id: str, decision: str) -> Dict[str, Any]:
        if decision not in {"publish-only", "prepare-issue"}:
            raise ValueError("Unknown diagnostic decision: {}".format(decision))
        preflight = self.preflight(run_id)
        path = self.store.run_dir(run_id) / "support-candidate.json"
        candidates = [SupportCandidate.model_validate(item) for item in preflight["candidates"]]
        status = "dismissed" if decision == "publish-only" else "issue_requested"
        for candidate in candidates:
            if candidate.status in {"deferred", "presented"}:
                candidate.status = status
                candidate.updated_at = utc_now().isoformat()
        self._write_candidates(run_id, candidates)
        return {
            **preflight,
            "status": "decision_recorded",
            "requires_diagnostic_decision": False,
            "decision": decision,
            "support_candidate": (str(path.relative_to(self.root)) if path.exists() else None),
            "candidates": [item.model_dump(mode="json") for item in candidates],
        }

    def link_issue(self, run_id: str, issue_url: str) -> Dict[str, Any]:
        if not re.fullmatch(
            r"https://(?:www\.)?github\.com/[^/\s]+/[^/\s]+/issues/\d+",
            issue_url,
        ):
            raise ValueError("issue_url must identify a GitHub issue")
        path = self.store.run_dir(run_id) / "support-candidate.json"
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
        self._write_candidates(run_id, candidates)
        return {
            "run_id": run_id,
            "status": "issue_raised",
            "issue_url": issue_url,
        }

    def _summary(
        self,
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
            "attention_required": any(
                item.status in {"deferred", "presented"} for item in candidates
            ),
        }

    def _candidates(self, state: RunState, events: List[DiagnosticEvent]) -> List[SupportCandidate]:
        grouped: Dict[str, List[DiagnosticEvent]] = {}
        support_events = [item for item in events if item.support_worthy]
        if any(item.event == "agent_attempt_failed" for item in support_events):
            support_events = [item for item in support_events if item.event != "run_failed"]
        for event in support_events:
            if event.support_worthy and event.fingerprint:
                grouped.setdefault(event.fingerprint, []).append(event)
        existing = self._existing_candidates(state.work_order.content_session_id)
        candidates = []
        for fingerprint, items in sorted(grouped.items()):
            latest = items[-1]
            prior = existing.get(fingerprint)
            recovered_pairs = {
                (event.run_id, event.role)
                for event in events
                if event.event == "agent_attempt_recovered"
            }
            recovered = all(
                item.outcome == "retrying" or (item.run_id, item.role) in recovered_pairs
                for item in items
            )
            occurrence_keys = {item.run_id or item.invocation_id or item.id for item in items}
            candidate = SupportCandidate(
                content_session_id=state.work_order.content_session_id,
                fingerprint=fingerprint,
                title=self._title(latest),
                summary=self._candidate_summary(latest, recovered),
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
            candidates.append(candidate)
        return candidates

    def _existing_candidates(self, content_session_id: str) -> Dict[str, SupportCandidate]:
        result: Dict[str, SupportCandidate] = {}
        for state in self._session_states(content_session_id):
            path = self.store.run_dir(state.id) / "support-candidate.json"
            if not path.exists():
                continue
            try:
                items = json.loads(path.read_text(encoding="utf-8"))
                for item in items:
                    candidate = SupportCandidate.model_validate(item)
                    current = result.get(candidate.fingerprint)
                    if current is None or candidate.updated_at > current.updated_at:
                        result[candidate.fingerprint] = candidate
            except (OSError, ValueError):
                continue
        return result

    def _session_states(self, content_session_id: str) -> Iterable[RunState]:
        for path in self.store.runs_dir.glob("*/state.json"):
            try:
                state = RunState.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if state.work_order.content_session_id == content_session_id:
                yield state

    def _session_events(self, content_session_id: str) -> Iterable[DiagnosticEvent]:
        for state in self._session_states(content_session_id):
            path = self.store.run_dir(state.id) / "diagnostics.jsonl"
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    yield DiagnosticEvent.model_validate_json(line)
                except ValueError:
                    continue

    def _write_candidates(self, run_id: str, candidates: List[SupportCandidate]) -> None:
        if not candidates:
            return
        self.store.write_artifact(
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
        self.store.write_artifact(run_id, "support-candidate.md", "\n".join(sections))

    def _record(self, event: DiagnosticEvent) -> None:
        if not self.enabled:
            return
        try:
            payload = event.model_dump_json() + "\n"
            path = (
                self.store.run_dir(self.run_id) / "diagnostics.jsonl"
                if self.run_id
                else self._invocation_dir() / "diagnostics.jsonl"
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(str(path), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
            try:
                os.write(descriptor, payload.encode("utf-8"))
            finally:
                os.close(descriptor)
        except OSError:
            # Diagnostics must never become the reason a content run fails.
            return

    def _invocation_dir(self) -> Path:
        invocation = self.invocation_id or "unknown"
        return self.root / ".content-creator" / "invocations" / invocation

    def sanitise(self, detail: str) -> str:
        value = detail.replace(str(self.root), "<workspace>")
        value = self.SENSITIVE_PATTERNS[0].sub(r"\1=<redacted>", value)
        for pattern in self.SENSITIVE_PATTERNS[1:]:
            value = pattern.sub("<home>", value)
        return value[:800]

    def _safe_error_detail(self, exc: Exception, classification: Dict[str, Any]) -> str:
        if classification["issue_type"] == "invalid_structured_output":
            return "Structured response did not match the required schema."
        if classification["issue_type"] == "provider_failure":
            return "Provider request failed; raw provider output was omitted."
        return self.sanitise(str(exc))

    @staticmethod
    def _fingerprint(component: str, issue_type: str, error_type: str) -> str:
        source = "{}|{}|{}".format(component, issue_type, error_type)
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]
        return "{}.{}.{}".format(component, issue_type, digest)

    @staticmethod
    def _phase(role: str) -> str:
        return {
            "researcher": "researching",
            "writer": "drafting",
            "critic": "reviewing",
            "learning-extractor": "publication",
            "perspective-extractor": "publication",
            "briefing-agent": "planning",
        }.get(role, role)

    @staticmethod
    def _title(event: DiagnosticEvent) -> str:
        labels = {
            "invalid_structured_output": "Structured agent output failed validation",
            "orchestration_failure": "Core orchestration failed",
            "unexpected_exception": "Unexpected Core exception",
        }
        return labels.get(event.issue_type or "", "Core runtime issue")

    @staticmethod
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
