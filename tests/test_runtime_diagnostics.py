import json
import logging

import pytest
from conftest import passing_critique, valid_draft

from content_creator.diagnostics import DiagnosticDecisionRequired, RuntimeDiagnostics
from content_creator.diagnostics.candidates import decide, link_issue
from content_creator.diagnostics.policy import classify, is_retryable
from content_creator.domain import RunState, RunStatus, WorkOrder
from content_creator.orchestrator import Orchestrator
from content_creator.providers import FakeProvider, ProviderRegistry
from content_creator.providers.base import ProviderError
from content_creator.runner import AgentOutputError
from content_creator.storage import RunStore, StorageError


def orchestrator_for(project, responses):
    return Orchestrator(
        project,
        registry=ProviderRegistry({"anthropic": FakeProvider(responses)}),
    )


def test_recovered_core_issue_is_deferred_until_publication(project):
    orchestrator = orchestrator_for(
        project,
        {
            "writer": [valid_draft()],
            "critic": ["not-json", passing_critique()],
            "learning-extractor": [{"candidates": []}],
        },
    )
    state = orchestrator.start(
        WorkOrder(
            request="write",
            topic="Recovered issue",
            content_pack="linkedin-post",
            format="post",
        )
    )

    assert state.status == RunStatus.READY
    assert state.pending_support_count == 0
    assert not (project / "runs" / state.id / "support-candidate.json").exists()
    diagnostic_text = (project / "runs" / state.id / "diagnostics.jsonl").read_text()
    assert "not-json" not in diagnostic_text
    assert "Structured response did not match" in diagnostic_text

    with pytest.raises(DiagnosticDecisionRequired) as raised:
        orchestrator.publish(state.id, filename="recovered.md")

    preflight = raised.value.preflight
    assert preflight["requires_diagnostic_decision"] is True
    assert preflight["candidates"][0]["recovered"] is True
    assert preflight["candidates"][0]["occurrences"] == 1
    assert not (project / "content" / "linkedin-post" / "published" / "recovered.md").exists()

    state = orchestrator.publish(
        state.id,
        filename="recovered.md",
        diagnostic_decision="prepare-issue",
    )
    candidates = json.loads((project / "runs" / state.id / "support-candidate.json").read_text())
    assert state.status == RunStatus.PUBLISHED
    assert state.pending_support_count == 0
    assert candidates[0]["status"] == "issue_requested"


def test_fatal_core_issue_is_surfaced_immediately(project):
    orchestrator = orchestrator_for(
        project,
        {
            "writer": [valid_draft()],
            "critic": ["not-json", "still-not-json"],
        },
    )

    with pytest.raises(AgentOutputError):
        orchestrator.start(
            WorkOrder(
                request="write",
                topic="Fatal issue",
                content_pack="linkedin-post",
                format="post",
            )
        )

    state_path = next((project / "runs").glob("*/state.json"))
    state = json.loads(state_path.read_text())
    assert state["status"] == "failed"
    assert state["pending_support_count"] == 1
    assert state["support_candidate_path"].endswith("support-candidate.json")


def test_content_lineage_aggregates_and_deduplicates_occurrences(project):
    session_id = "shared-session"
    first = orchestrator_for(
        project,
        {
            "writer": [valid_draft()],
            "critic": ["bad-json", passing_critique()],
        },
    ).start(
        WorkOrder(
            request="first",
            topic="First revision",
            content_pack="linkedin-post",
            format="post",
            content_session_id=session_id,
        )
    )
    second_orchestrator = orchestrator_for(
        project,
        {
            "writer": [valid_draft()],
            "critic": ["bad-again", passing_critique()],
        },
    )
    second = second_orchestrator.start(
        WorkOrder(
            request="second",
            topic="Second revision",
            content_pack="linkedin-post",
            format="post",
            content_session_id=session_id,
            parent_run_id=first.id,
        )
    )

    preflight = second_orchestrator.diagnostic_preflight(second.id)
    assert len(preflight["candidates"]) == 1
    assert preflight["candidates"][0]["occurrences"] == 2
    assert preflight["candidates"][0]["run_ids"] == sorted([first.id, second.id])


def test_provider_failure_does_not_become_core_candidate(project):
    diagnostics = RuntimeDiagnostics(project)
    diagnostics.begin_invocation("provider-session")
    detail = diagnostics.classify(type("ProviderError", (RuntimeError,), {})("service unavailable"))
    assert detail["classification"] == "provider"
    assert detail["support_worthy"] is False


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ValueError("bad input"), False),
        (ProviderError("service timed out"), True),
        (ProviderError("request denied"), False),
    ],
)
def test_retry_policy_distinguishes_transient_provider_failures(error, expected):
    assert is_retryable(error) is expected


@pytest.mark.parametrize(
    ("error", "expected_classification", "support_worthy"),
    [
        (ProviderError("authentication login required"), "workspace_configuration", False),
        (StorageError("disk failed"), "core", True),
        (RuntimeError("unexpected"), "core", True),
    ],
)
def test_diagnostic_policy_classifies_configuration_storage_and_unknown_failures(
    error, expected_classification, support_worthy
):
    result = classify(error)

    assert result["classification"] == expected_classification
    assert result["support_worthy"] is support_worthy


def test_diagnostic_sanitiser_removes_secrets_and_user_paths(project):
    diagnostics = RuntimeDiagnostics(project)
    value = diagnostics.sanitise(
        "API_KEY=super-secret at /Users/example/private/file " + str(project / "draft.md")
    )
    assert "super-secret" not in value
    assert "/Users/example" not in value
    assert str(project) not in value
    assert "<workspace>" in value


def test_linking_issue_completes_candidate_lifecycle(project):
    orchestrator = orchestrator_for(
        project,
        {
            "writer": [valid_draft()],
            "critic": ["not-json", passing_critique()],
            "learning-extractor": [{"candidates": []}],
        },
    )
    state = orchestrator.start(
        WorkOrder(
            request="write",
            topic="Link issue",
            content_pack="linkedin-post",
            format="post",
        )
    )
    with pytest.raises(DiagnosticDecisionRequired):
        orchestrator.publish(state.id, filename="linked.md")
    orchestrator.publish(
        state.id,
        filename="linked.md",
        diagnostic_decision="prepare-issue",
    )

    result = orchestrator.link_diagnostic_issue(
        state.id,
        "https://github.com/vadhoob90/Content_Creator_Core/issues/123",
    )
    candidates = json.loads((project / "runs" / state.id / "support-candidate.json").read_text())
    assert result["status"] == "issue_raised"
    assert candidates[0]["status"] == "issue_raised"
    assert candidates[0]["issue_url"].endswith("/123")

    with pytest.raises(ValueError, match="no issue-requested"):
        orchestrator.link_diagnostic_issue(
            state.id,
            "https://github.com/vadhoob90/Content_Creator_Core/issues/124",
        )
    repeated = decide(RunStore(project), state.id, "publish-only")
    assert repeated["candidates"][0]["status"] == "issue_raised"


def test_diagnostic_decisions_reject_unknown_values_and_invalid_issue_links(project):
    store = RunStore(project)
    state = RunState(
        id="no-candidate-run",
        status=RunStatus.READY,
        work_order=WorkOrder(request="Draft", topic="Draft"),
        route_plan={"route": "text-none-none", "stages": ["writer"]},
    )
    store.create(state)

    with pytest.raises(ValueError, match="Unknown diagnostic decision"):
        decide(store, state.id, "ignore")
    with pytest.raises(ValueError, match="must identify a GitHub issue"):
        link_issue(store, state.id, "https://example.com/issues/1")
    with pytest.raises(ValueError, match="no support candidate"):
        link_issue(store, state.id, "https://github.com/example/repository/issues/1")


def test_failure_before_run_creation_preserves_invocation_summary(project):
    orchestrator = orchestrator_for(project, {})

    with pytest.raises(ValueError) as raised:
        orchestrator.start(
            WorkOrder(
                request="write",
                topic="Missing pack",
                content_pack="missing-pack",
                format="post",
            )
        )

    diagnostic_path = project / raised.value.diagnostic_path
    summary = json.loads(diagnostic_path.read_text())
    latest = json.loads((project / ".content-creator" / "latest-invocation.json").read_text())
    assert summary["status"] == "failed_before_run"
    assert summary["classification"] == "workspace_configuration"
    assert latest["diagnostic_summary"] == raised.value.diagnostic_path


def test_failed_invocation_summary_is_not_advertised(project, monkeypatch, caplog):
    orchestrator = orchestrator_for(project, {})

    def fail_write(_path, _text):
        raise OSError("disk unavailable")

    monkeypatch.setattr(RunStore, "_atomic_text", staticmethod(fail_write))

    with caplog.at_level(logging.WARNING), pytest.raises(ValueError) as raised:
        orchestrator.start(
            WorkOrder(
                request="write",
                topic="Missing pack",
                content_pack="missing-pack",
                format="post",
            )
        )

    assert not hasattr(raised.value, "diagnostic_path")
    assert "Unable to persist invocation diagnostic summary (OSError)" in caplog.text


def test_corrupt_diagnostic_records_are_skipped_with_warnings(project, caplog):
    store = RunStore(project)
    state = RunState(
        id="warning-run",
        status=RunStatus.READY,
        work_order=WorkOrder(
            request="Draft",
            topic="Warning visibility",
            content_session_id="warning-session",
        ),
        route_plan={"route": "text-none-none", "stages": ["writer"]},
    )
    store.create(state)
    run_directory = store.run_dir(state.id)
    (run_directory / "diagnostics.jsonl").write_text("not-json\n", encoding="utf-8")
    (run_directory / "support-candidate.json").write_text("not-json", encoding="utf-8")
    corrupt_directory = store.run_dir("corrupt-run")
    corrupt_directory.mkdir(parents=True)
    (corrupt_directory / "state.json").write_text("not-json", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        result = RuntimeDiagnostics(project).preflight(state.id)

    assert result["candidates"] == []
    assert "Skipping 1 invalid diagnostic event(s)" in caplog.text
    assert "Skipping unreadable support candidates" in caplog.text
    assert "Skipping unreadable run state" in caplog.text


def test_legacy_run_uses_run_id_as_stable_content_session(project):
    path = project / "runs" / "legacy-run"
    path.mkdir(parents=True)
    (path / "state.json").write_text(
        json.dumps(
            {
                "id": "legacy-run",
                "status": "ready",
                "work_order": {
                    "request": "Draft",
                    "topic": "Legacy draft",
                },
                "route_plan": {
                    "route": "text-none-none",
                    "stages": ["writer"],
                },
            }
        ),
        encoding="utf-8",
    )

    first = RuntimeDiagnostics(project).store.load("legacy-run")
    second = RuntimeDiagnostics(project).store.load("legacy-run")
    assert first.work_order.content_session_id == "legacy-run"
    assert second.work_order.content_session_id == "legacy-run"
