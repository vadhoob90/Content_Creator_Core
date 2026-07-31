import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import passing_critique, valid_draft

from content_creator.cli import build_parser, main
from content_creator.domain import RoutePlan, RunState, RunStatus, WorkOrder
from content_creator.orchestrator import Orchestrator
from content_creator.providers import FakeProvider, ProviderRegistry
from content_creator.storage import IdempotencyError, RunStore


def _orchestrator(project, responses):
    return Orchestrator(
        project,
        registry=ProviderRegistry({"anthropic": FakeProvider(responses)}),
    )


def _order(request="write", topic="topic", **changes):
    return WorkOrder(
        request=request,
        topic=topic,
        content_pack="linkedin-post",
        format="post",
        **changes,
    )


def test_equivalent_submission_returns_existing_run_without_execution(project):
    first = _orchestrator(
        project,
        {"writer": [valid_draft()], "critic": [passing_critique()]},
    ).start(_order(), idempotency_key="linkedin-post:topic:v1")
    duplicate_provider = FakeProvider({})
    duplicate = Orchestrator(
        project,
        registry=ProviderRegistry({"anthropic": duplicate_provider}),
    ).start(_order(), idempotency_key="linkedin-post:topic:v1")

    assert duplicate.id == first.id
    assert duplicate.status == RunStatus.READY
    assert duplicate.idempotency_reused is True
    assert duplicate_provider.requests == []
    assert len(list((project / "runs").glob("*/state.json"))) == 1
    persisted = (project / "runs" / first.id / "state.json").read_text()
    assert "linkedin-post:topic:v1" not in persisted
    assert first.idempotency_key_hash in persisted


def test_conflicting_idempotency_key_fails_without_second_run(project):
    _orchestrator(
        project,
        {"writer": [valid_draft()], "critic": [passing_critique()]},
    ).start(_order(), idempotency_key="shared-key")

    with pytest.raises(IdempotencyError, match="different work order") as raised:
        _orchestrator(project, {}).start(
            _order(request="different", topic="different"),
            idempotency_key="shared-key",
        )

    assert len(list((project / "runs").glob("*/state.json"))) == 1
    summary = json.loads(
        (project / raised.value.diagnostic_path).read_text(encoding="utf-8")
    )
    assert summary["classification"] == "content_workflow"
    assert summary["support_worthy"] is False


def test_distinct_revision_key_preserves_content_lineage(project):
    first = _orchestrator(
        project,
        {"writer": [valid_draft()], "critic": [passing_critique()]},
    ).start(_order(), idempotency_key="piece:first")
    second = _orchestrator(
        project,
        {"writer": [valid_draft()], "critic": [passing_critique()]},
    ).start(
        _order(
            request="revise",
            topic="topic revision",
            parent_run_id=first.id,
            content_session_id=first.work_order.content_session_id,
        ),
        idempotency_key="piece:revision-2",
    )

    assert second.id != first.id
    assert second.work_order.parent_run_id == first.id
    assert (
        second.work_order.content_session_id
        == first.work_order.content_session_id
    )


def test_duplicate_terminal_submission_does_not_repeat_publication(project):
    orchestrator = _orchestrator(
        project,
        {
            "writer": [valid_draft()],
            "critic": [passing_critique()],
            "learning-extractor": [{"candidates": []}],
        },
    )
    first = orchestrator.start(
        _order(), idempotency_key="published-piece"
    )
    published = orchestrator.publish(first.id, filename="published-piece.md")

    duplicate = _orchestrator(project, {}).start(
        _order(), idempotency_key="published-piece"
    )

    assert duplicate.id == published.id
    assert duplicate.status == RunStatus.PUBLISHED
    assert duplicate.idempotency_reused is True
    assert list(
        (project / "content" / "linkedin-post" / "published").glob("*.md")
    ) == [
        project
        / "content"
        / "linkedin-post"
        / "published"
        / "published-piece.md"
    ]


def test_atomic_index_allows_one_concurrent_submission(project):
    key = "concurrent-key"
    fingerprint = "fingerprint"

    def submit(index):
        state = RunState(
            id="concurrent-{}".format(index),
            work_order=WorkOrder(request="write", topic="topic"),
            route_plan=RoutePlan(route="text-none-none", stages=["writer"]),
        )
        return RunStore(project).create_idempotent(
            state, key, fingerprint
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(submit, [1, 2]))

    assert sum(created for _, created in outcomes) == 1
    assert len({state.id for state, _ in outcomes}) == 1
    assert len(list((project / "runs").glob("*/state.json"))) == 1


def test_submission_status_resolves_key_without_execution(project, capsys):
    state = RunState(
        id="observable-run",
        status=RunStatus.DRAFTING,
        work_order=WorkOrder(request="write", topic="topic"),
        route_plan=RoutePlan(route="text-none-none", stages=["writer"]),
    )
    RunStore(project).create_idempotent(state, "observable-key", "fingerprint")

    assert (
        main(
            [
                "--root",
                str(project),
                "submission",
                "status",
                "observable-key",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["id"] == "observable-run"
    assert result["status"] == "drafting"
    assert result["idempotency_reused"] is True


def test_run_parser_accepts_idempotency_key():
    args = build_parser().parse_args(
        ["run", "write", "--idempotency-key", "request-123"]
    )
    assert args.idempotency_key == "request-123"
