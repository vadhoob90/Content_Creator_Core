import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import passing_critique, valid_draft

from content_creator.cli import build_parser, main
from content_creator.domain import RoutePlan, RunState, RunStatus, WorkOrder
from content_creator.orchestrator import OrchestrationError, Orchestrator
from content_creator.providers import FakeProvider, ProviderRegistry
from content_creator.storage import IdempotencyError, RunStore, StorageError


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
    summary = json.loads((project / raised.value.diagnostic_path).read_text(encoding="utf-8"))
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
    assert second.work_order.content_session_id == first.work_order.content_session_id


def test_parent_revision_hydrates_reviewed_draft_and_preservation_context(project):
    parent_draft = valid_draft()
    first = _orchestrator(
        project,
        {"writer": [parent_draft], "critic": [passing_critique()]},
    ).start(_order(), idempotency_key="piece:parent")
    revision_provider = FakeProvider({"writer": [parent_draft], "critic": [passing_critique()]})
    revision = Orchestrator(
        project,
        registry=ProviderRegistry({"anthropic": revision_provider}),
    ).start(
        _order(
            request="Change only the final sentence.",
            parent_run_id=first.id,
        ),
        idempotency_key="piece:targeted-revision",
    )

    writer_request = next(
        request for request in revision_provider.requests if request.role == "writer"
    )
    writer_payload = json.loads(writer_request.user.split("\nINPUT\n", 1)[1])
    context = writer_payload["revision_context"]
    assert revision.work_order.content_session_id == first.work_order.content_session_id
    assert context["parent_run_id"] == first.id
    assert context["content_session_id"] == first.work_order.content_session_id
    assert context["parent_draft"].strip() == parent_draft
    assert "preserve all unaffected approved passages" in context["revision_instruction"]


def test_parent_revision_requires_reviewed_draft(project):
    parent = RunState(
        id="unfinished-parent",
        status=RunStatus.DRAFTING,
        work_order=_order(),
        route_plan=RoutePlan(route="post-none-none", stages=["writer"]),
    )
    RunStore(project).create(parent)

    with pytest.raises(OrchestrationError, match="no reviewed draft"):
        _orchestrator(project, {}).start(_order(request="revise", parent_run_id=parent.id))


def test_duplicate_terminal_submission_does_not_repeat_publication(project):
    orchestrator = _orchestrator(
        project,
        {
            "writer": [valid_draft()],
            "critic": [passing_critique()],
            "learning-extractor": [{"candidates": []}],
        },
    )
    first = orchestrator.start(_order(), idempotency_key="published-piece")
    published = orchestrator.publish(first.id, filename="published-piece.md")

    duplicate = _orchestrator(project, {}).start(_order(), idempotency_key="published-piece")

    assert duplicate.id == published.id
    assert duplicate.status == RunStatus.PUBLISHED
    assert duplicate.idempotency_reused is True
    assert list((project / "content" / "linkedin-post" / "published").glob("*.md")) == [
        project / "content" / "linkedin-post" / "published" / "published-piece.md"
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
        return RunStore(project).create_idempotent(state, key, fingerprint)

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
    args = build_parser().parse_args(["run", "write", "--idempotency-key", "request-123"])
    assert args.idempotency_key == "request-123"


def test_idempotent_creation_rolls_back_index_when_run_persistence_fails(project, monkeypatch):
    store = RunStore(project)
    state = RunState(
        id="failed-persistence",
        work_order=WorkOrder(request="write", topic="topic"),
        route_plan=RoutePlan(route="text-none-none", stages=["writer"]),
    )

    def fail_create(_state):
        raise OSError("disk unavailable")

    monkeypatch.setattr(store, "create", fail_create)

    with pytest.raises(StorageError, match="Could not persist idempotent run submission"):
        store.create_idempotent(state, "rollback-key", "fingerprint")

    assert store.load_by_idempotency_key("rollback-key") is None
    assert not store.run_dir(state.id).exists()


def test_idempotency_lookup_reports_corrupt_database(project):
    database = project / ".content-creator" / "idempotency.sqlite3"
    database.parent.mkdir(parents=True)
    database.write_text("not a sqlite database", encoding="utf-8")

    with pytest.raises(StorageError, match="Could not read idempotent run submission"):
        RunStore(project).load_by_idempotency_key("corrupt-index")


def test_idempotency_lookup_returns_none_for_missing_index_and_unknown_key(project):
    store = RunStore(project)

    assert store.load_by_idempotency_key("absent-database") is None

    state = RunState(
        id="known-run",
        work_order=WorkOrder(request="write", topic="topic"),
        route_plan=RoutePlan(route="text-none-none", stages=["writer"]),
    )
    store.create_idempotent(state, "known-key", "fingerprint")

    assert store.load_by_idempotency_key("unknown-key") is None


def test_idempotency_lookup_rejects_index_and_run_state_mismatch(project):
    store = RunStore(project)
    state = RunState(
        id="mismatched-run",
        work_order=WorkOrder(request="write", topic="topic"),
        route_plan=RoutePlan(route="text-none-none", stages=["writer"]),
    )
    store.create_idempotent(state, "mismatch-key", "fingerprint")
    state.idempotency_key_hash = "tampered"
    store.save_state(state)

    with pytest.raises(StorageError, match="index does not match persisted run"):
        store.load_by_idempotency_key("mismatch-key")


@pytest.mark.parametrize("key", ["", "space separated", "slash/value", 42])
def test_idempotency_keys_reject_ambiguous_or_non_text_values(key):
    with pytest.raises(IdempotencyError, match="Idempotency keys must be"):
        RunStore.idempotency_key_hash(key)


@pytest.mark.parametrize("run_id", ["../outside", "nested/run", "space separated"])
def test_run_store_rejects_unsafe_run_identifiers(project, run_id):
    with pytest.raises(StorageError, match="Invalid run id"):
        RunStore(project).run_dir(run_id)


def test_run_store_distinguishes_unknown_runs_and_missing_artifacts(project):
    store = RunStore(project)

    with pytest.raises(StorageError, match="Unknown run: absent-run"):
        store.load("absent-run")

    state = RunState(
        id="artifact-run",
        work_order=WorkOrder(request="write", topic="topic"),
        route_plan=RoutePlan(route="text-none-none", stages=["writer"]),
    )
    store.create(state)

    with pytest.raises(StorageError, match="Missing artifact"):
        store.read_artifact(state.id, "missing.json")
