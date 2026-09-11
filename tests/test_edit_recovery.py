import json

import pytest
from conftest import passing_critique, valid_draft

from content_creator.author_edits import AuthorEditRequest, AuthorEditWorkflow, ClaimReviewDecision
from content_creator.domain import RunStatus, WorkOrder
from content_creator.draft_integrity import ensure_draft_integrity
from content_creator.edit_transaction import JOURNAL, edit_transaction, restore_edit
from content_creator.orchestrator import Orchestrator
from content_creator.providers import FakeProvider, ProviderRegistry
from content_creator.storage import RunStore, StorageError
from content_creator.versioned_artifacts import ActivationLock, hash_file


def reviewed_run(project):
    fake = FakeProvider({"writer": [valid_draft()], "critic": [passing_critique()]})
    core = Orchestrator(project, registry=ProviderRegistry({"anthropic": fake}))
    return core, core.start(
        WorkOrder(request="Write", topic="Write", pack_options={"length": "50:600"})
    )


def test_interrupted_transaction_blocks_publication_and_recovery_restores_exact_bytes(project):
    core, state = reviewed_run(project)
    run = project / "runs" / state.id
    final = run / "final.md"
    before = final.read_bytes()
    try:
        with edit_transaction(run, ["final.md", "new.json"]):
            final.write_bytes(b"interrupted edit")
            (run / "new.json").write_text("new")
            raise KeyboardInterrupt
    except KeyboardInterrupt:
        assert final.read_bytes() == b"interrupted edit"
    assert (run / JOURNAL).exists()
    with pytest.raises(StorageError, match="recover-edit"):
        core.publish(state.id)
    recovered = AuthorEditWorkflow(project).recover(state.id)
    assert recovered.status == RunStatus.READY
    assert final.read_bytes() == before
    assert not (run / "new.json").exists()
    assert not (run / JOURNAL).exists()
    with pytest.raises(StorageError, match="no interrupted"):
        AuthorEditWorkflow(project).recover(state.id)


def test_conflicting_operations_share_a_run_lock(project):
    core, state = reviewed_run(project)
    run = project / "runs" / state.id
    with ActivationLock(run / ".author-edit.lock", "busy"):
        with pytest.raises(StorageError, match="Another edit"):
            core.publish(state.id)
        with pytest.raises(StorageError, match="Another edit"):
            core.revise(state.id, "Change wording")


@pytest.mark.parametrize("name", ["../outside", "/tmp/outside", JOURNAL, ".author-edit.lock"])
def test_recovery_rejects_unsafe_paths_without_touching_run(tmp_path, name):
    journal = tmp_path / JOURNAL
    journal.write_text(json.dumps({"schema_version": "1.0", "before": {name: None}}))
    with pytest.raises(StorageError, match="path"):
        restore_edit(tmp_path)
    assert journal.exists()


def test_recovery_rejects_unknown_journal_schema(tmp_path):
    (tmp_path / JOURNAL).write_text(json.dumps({"schema_version": "99", "before": {}}))
    with pytest.raises(StorageError, match="Invalid"):
        restore_edit(tmp_path)


def test_legacy_manifest_drift_is_not_silently_accepted(project):
    _, state = reviewed_run(project)
    run = project / "runs" / state.id
    (run / "draft-integrity.json").unlink()
    draft = (run / "final.md").read_text() + "different claim"
    with pytest.raises(StorageError, match="hash changed"):
        ensure_draft_integrity(run, draft)


def test_missing_or_tampered_context_is_actionable(project):
    _, state = reviewed_run(project)
    run = project / "runs" / state.id
    path = run / "resolved-context.json"
    original = path.read_text()
    request = AuthorEditRequest(
        draft=(run / "final.md").read_text() + "\n",
        expected_sha256=hash_file(run / "final.md"),
        idempotency_key="context-test",
    )
    path.unlink()
    with pytest.raises(StorageError, match="Historical pack inputs unavailable"):
        AuthorEditWorkflow(project).adopt(state.id, request)
    context = json.loads(original)
    context["effective_pack"]["version"] = "new"
    path.write_text(json.dumps(context))
    with pytest.raises(StorageError, match="effective pack hash"):
        AuthorEditWorkflow(project).adopt(state.id, request)


def test_published_run_rejects_author_adoption(project):
    _, state = reviewed_run(project)
    run = project / "runs" / state.id
    state.status = RunStatus.PUBLISHED
    RunStore(project).save_state(state)
    request = AuthorEditRequest(
        draft="New", expected_sha256=hash_file(run / "final.md"), idempotency_key="published-test"
    )
    with pytest.raises(StorageError, match="unpublished"):
        AuthorEditWorkflow(project).adopt(state.id, request)


def test_claim_approval_failure_restores_pending_decision(project, monkeypatch):
    _, state = reviewed_run(project)
    run = project / "runs" / state.id
    workflow = AuthorEditWorkflow(project)
    workflow.adopt(
        state.id,
        AuthorEditRequest(
            draft=(run / "final.md").read_text() + "\nA claim.",
            expected_sha256=hash_file(run / "final.md"),
            idempotency_key="claim-edit",
        ),
    )
    original = (run / "draft-integrity.json").read_bytes()

    def fail_save(_state):
        raise OSError("save failed")

    monkeypatch.setattr(workflow.store, "save_state", fail_save)
    with pytest.raises(OSError, match="save failed"):
        workflow.approve_claims(
            state.id,
            ClaimReviewDecision(
                draft_sha256=hash_file(run / "final.md"),
                approved_by="Author",
                notes="Reviewed",
            ),
        )
    assert (run / "draft-integrity.json").read_bytes() == original
    assert not (run / "claim-review-02.json").exists()
