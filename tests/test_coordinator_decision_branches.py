import pytest

from content_creator.coordinator import ContentCoordinator
from content_creator.coordinator_models import (
    CoordinatorAction,
    ProviderStatus,
    RunSummary,
    VoiceStatus,
    WorkspaceSnapshot,
)
from content_creator.domain import RoutePlan, RunState, RunStatus, WorkOrder
from content_creator.health import WorkspaceHealth


def _snapshot(**changes):
    values = {
        "workspace": "/workspace",
        "is_workspace": True,
        "coordinator": {},
        "provider_status": ProviderStatus(name="anthropic", status="configured"),
        "active_voice_ids": ["default"],
        "health": {"status": "ok"},
        "recommended_action": CoordinatorAction(id="pending", label="pending"),
    }
    values.update(changes)
    return WorkspaceSnapshot(**values)


def _run(status):
    return RunSummary(
        run_id="run-1",
        status=status,
        topic="Topic",
        content_pack="general-text",
        voice_id="default",
        updated_at="2026-08-08T00:00:00Z",
    )


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"is_workspace": False}, "create-workspace"),
        ({"runs": [_run("awaiting_research_approval")]}, "review-research"),
        ({"runs": [_run("ready")]}, "review-draft"),
        (
            {
                "voices": [
                    VoiceStatus(
                        voice_id="author", display_name="Author", onboarding_status="undecided"
                    )
                ]
            },
            "choose-voice-route",
        ),
        (
            {
                "voices": [
                    VoiceStatus(
                        voice_id="author", display_name="Author", candidate_decision="pending"
                    )
                ]
            },
            "review-voice-candidate",
        ),
        ({"provider_status": ProviderStatus(status="missing-credentials")}, "select-provider"),
        ({"active_voice_ids": []}, "create-voice"),
        ({}, "create-content"),
    ],
)
def test_coordinator_recommends_the_highest_priority_safe_action(changes, expected):
    assert ContentCoordinator._recommend(_snapshot(**changes)).id == expected


def _state(status, **changes):
    values = {
        "id": "branch-run",
        "status": status,
        "work_order": WorkOrder(request="Draft", topic="Draft"),
        "route_plan": RoutePlan(route="text-none-none", stages=["writer"]),
    }
    values.update(changes)
    return RunState(**values)


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (_state(RunStatus.READY), "publish-local"),
        (_state(RunStatus.NEEDS_AUTHOR), "provide-author-direction"),
        (_state(RunStatus.PUBLISHED, published_path="published.md"), "review-publication"),
        (
            _state(
                RunStatus.PUBLISHED,
                published_path="published.md",
                pending_support_count=1,
                support_candidate_path="support.json",
            ),
            "review-support-candidate",
        ),
        (_state(RunStatus.FAILED), "inspect-failure"),
        (
            _state(
                RunStatus.FAILED,
                pending_support_count=1,
                support_candidate_path="support.json",
            ),
            "review-support-candidate",
        ),
        (_state(RunStatus.DRAFTING), "inspect-status"),
    ],
)
def test_coordinator_routes_each_persisted_lifecycle_state(project, state, expected):
    actions = ContentCoordinator(project)._actions_for_state(state, state.id)

    assert expected in {action.id for action in actions}


def test_coordinator_surfaces_degraded_workspace_defaults_and_health(project, monkeypatch):
    (project / "content-creator.yaml").write_text(
        "coordinator:\n"
        "  default_voice: missing-voice\n"
        "  default_pack: missing-pack\n"
        "  external_publication: disabled\n",
        encoding="utf-8",
    )
    coordinator = ContentCoordinator(project)

    def no_voices():
        return []

    def failed_health(_self):
        return {"status": "failed"}

    def no_provider():
        return ProviderStatus()

    monkeypatch.setattr(coordinator, "_voices", no_voices)
    monkeypatch.setattr(WorkspaceHealth, "report", failed_health)
    monkeypatch.setattr(coordinator, "_provider_status", no_provider)

    snapshot = coordinator.snapshot()

    assert snapshot.recommended_action.id == "select-provider"
    assert snapshot.warnings == [
        "Configured default voice is not active: missing-voice",
        "Configured default pack is unavailable: missing-pack",
        "No active voice is available",
        "Workspace doctor checks require attention",
        "No provider is selected",
    ]
