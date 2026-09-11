import json

import pytest
from conftest import passing_critique, research_brief, valid_draft

from content_creator.author_edits import AuthorEditRequest, AuthorEditWorkflow, ClaimReviewDecision
from content_creator.domain import ResearchBrief, RunStatus, WorkOrder
from content_creator.orchestrator import Orchestrator
from content_creator.providers import FakeProvider, ProviderRegistry
from content_creator.storage import StorageError
from content_creator.versioned_artifacts import hash_file


@pytest.fixture
def reviewed(project):
    fake = FakeProvider({"writer": [valid_draft()], "critic": [passing_critique()]})
    core = Orchestrator(project, registry=ProviderRegistry({"anthropic": fake}))
    state = core.start(
        WorkOrder(request="Explain writing", topic="Writing", pack_options={"length": "50:600"})
    )
    return core, state, fake


def request_for(project, state, draft, **changes):
    return AuthorEditRequest(
        draft=draft,
        expected_sha256=hash_file(project / state.final_draft_path),
        idempotency_key="first-edit",
        **changes,
    )


def test_adopt_editorial_whitespace_without_provider_and_preserve_history(project, reviewed):
    _, state, fake = reviewed
    run = project / "runs" / state.id
    original = (run / "final.md").read_text()
    old_manifest = (run / "production-manifest.json").read_bytes()
    request = request_for(project, state, original + "\n")
    calls = len(fake.requests)
    edits = AuthorEditWorkflow(project)
    adopted = edits.adopt(state.id, request)
    repeated = edits.adopt(state.id, request)
    assert adopted.status == RunStatus.READY
    assert adopted.revision == repeated.revision == state.revision + 1
    assert len(fake.requests) == calls
    assert (run / "final.md").read_text() == request.draft
    assert (run / "accepted" / "r0001.md").read_text() == original
    assert (run / "accepted" / "r0001.manifest.json").read_bytes() == old_manifest
    assert (run / "revision-02.diff").exists()
    assert json.loads((run / "validation-02.json").read_text())["errors"] == []
    assert not (run / "quality-02.json").exists()
    manifest = json.loads((run / "production-manifest.json").read_text())
    assert next(a for a in manifest["artifacts"] if a["kind"] == "final-draft")[
        "content_hash"
    ] == hash_file(run / "final.md")


def test_claim_change_reopens_review_and_approval_keeps_exact_text(project, reviewed):
    _, state, fake = reviewed
    run = project / "runs" / state.id
    draft = (run / "final.md").read_text() + "\nUsing agents for writing is not new.\n"
    request = request_for(project, state, draft, research=ResearchBrief(**research_brief()))
    edits = AuthorEditWorkflow(project)
    adopted = edits.adopt(state.id, request)
    assert adopted.status == RunStatus.NEEDS_AUTHOR
    evidence = json.loads((run / "draft-integrity.json").read_text())
    assert evidence["claim_review_status"] == "required"
    before = len(fake.requests)
    decision = ClaimReviewDecision(
        draft_sha256=hash_file(run / "final.md"),
        research_sha256=hash_file(run / "research.json"),
        approved_by="Author",
        notes="Reviewed changed claim against the supplied research.",
    )
    approved = edits.approve_claims(state.id, decision)
    assert approved.status == RunStatus.READY
    assert (run / "final.md").read_text() == draft
    assert len(fake.requests) == before
    (run / "final.md").write_text(draft.replace("not new", "unique"))
    with pytest.raises(StorageError, match="hash"):
        edits.approve_claims(state.id, decision)


def test_adopt_in_place_edit_recovers_verified_snapshot(project, reviewed):
    _, state, _ = reviewed
    final = project / state.final_draft_path
    original = final.read_text()
    request = request_for(project, state, original + "\nA new assertion.\n")
    final.write_text(request.draft)
    adopted = AuthorEditWorkflow(project).adopt(state.id, request)
    baseline = project / "runs" / state.id / "revision-baseline-02.md"
    assert baseline.read_text() == original
    assert adopted.status == RunStatus.NEEDS_AUTHOR


def test_concurrent_edit_is_not_overwritten(project, reviewed):
    _, state, _ = reviewed
    final = project / state.final_draft_path
    request = request_for(project, state, final.read_text() + "\n")
    final.write_text("A different concurrent edit")
    with pytest.raises(StorageError, match="changed"):
        AuthorEditWorkflow(project).adopt(state.id, request)
    assert final.read_text() == "A different concurrent edit"


def test_publication_rejects_unadopted_file_change(project, reviewed):
    core, state, _ = reviewed
    final = project / state.final_draft_path
    final.write_text(final.read_text() + "\nAn unreviewed claim.\n")
    with pytest.raises(StorageError, match="hash"):
        core.publish(state.id)
    assert not list((project / "publication-receipts").rglob("*.json"))


def test_adoption_preserves_crlf_and_no_final_newline(project, reviewed):
    _, state, _ = reviewed
    final = project / state.final_draft_path
    edited = final.read_text().rstrip().replace("\n", "\r\n")
    adopted = AuthorEditWorkflow(project).adopt(state.id, request_for(project, state, edited))
    assert adopted.status == RunStatus.NEEDS_AUTHOR
    assert final.read_bytes() == edited.encode()
    run = final.parent
    assert (run / "accepted/r0002.md").read_bytes() == edited.encode()


def test_pack_update_does_not_replace_generation_inputs(project, reviewed):
    _, state, _ = reviewed
    from content_creator.packs import PackRegistry

    pack = PackRegistry(project).get(state.work_order.content_pack)
    pack.version = "99.0.0"
    pack.validators = ["no-em-dash"]
    destination = project / "packs" / pack.id / "pack.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(pack.model_dump_json())
    final = project / state.final_draft_path
    adopted = AuthorEditWorkflow(project).adopt(
        state.id, request_for(project, state, final.read_text() + "\n")
    )
    manifest = json.loads((final.parent / "production-manifest.json").read_text())
    assert adopted.status == RunStatus.READY
    assert manifest["content_pack"]["version"] == "1.0.0"


def test_missing_original_is_reported_and_supplied_hash_matching_original_recovers(
    project, reviewed
):
    import shutil

    _, state, _ = reviewed
    final = project / state.final_draft_path
    original = final.read_text()
    request = request_for(project, state, original + "\nNew claim.")
    shutil.rmtree(final.parent / "accepted")
    for path in final.parent.glob("draft-*.md"):
        path.unlink()
    final.write_text(request.draft)
    workflow = AuthorEditWorkflow(project)
    with pytest.raises(StorageError, match="Missing verified baseline"):
        workflow.adopt(state.id, request)
    adopted = workflow.adopt(state.id, request.model_copy(update={"baseline": original}))
    assert adopted.revision == 2
    assert (final.parent / "accepted/r0001.md").read_text() == original


def test_failed_save_restores_all_changed_bytes_and_retry_succeeds(project, reviewed, monkeypatch):
    _, state, _ = reviewed
    final = project / state.final_draft_path
    request = request_for(project, state, final.read_text() + "\n")
    workflow = AuthorEditWorkflow(project)
    before = {
        str(p.relative_to(final.parent)): p.read_bytes()
        for p in final.parent.rglob("*")
        if p.is_file()
    }
    original_save = workflow.store.save_state

    def fail_after_save(updated):
        original_save(updated)
        raise OSError("simulated failure after state save")

    monkeypatch.setattr(workflow.store, "save_state", fail_after_save)
    with pytest.raises(OSError, match="simulated"):
        workflow.adopt(state.id, request)
    after = {
        str(p.relative_to(final.parent)): p.read_bytes()
        for p in final.parent.rglob("*")
        if p.is_file()
    }
    assert before == after
    monkeypatch.setattr(workflow.store, "save_state", original_save)
    assert workflow.adopt(state.id, request).revision == 2


def test_changed_input_cannot_reuse_adoption_key(project, reviewed):
    _, state, _ = reviewed
    final = project / state.final_draft_path
    request = request_for(project, state, final.read_text() + "\n")
    workflow = AuthorEditWorkflow(project)
    workflow.adopt(state.id, request)
    with pytest.raises(StorageError, match="idempotency"):
        workflow.adopt(state.id, request.model_copy(update={"draft": "Different input"}))
    with pytest.raises(StorageError, match="baseline hash"):
        workflow.adopt(state.id, request.model_copy(update={"idempotency_key": "second-edit"}))


def test_pending_claim_review_cannot_be_cleared_by_whitespace_edit(project, reviewed):
    core, state, _ = reviewed
    final = project / state.final_draft_path
    workflow = AuthorEditWorkflow(project)
    first = workflow.adopt(state.id, request_for(project, state, final.read_text() + "\nA claim."))
    second = AuthorEditRequest(
        draft=final.read_text() + "\n", expected_sha256=hash_file(final), idempotency_key="second"
    )
    assert workflow.adopt(first.id, second).status == RunStatus.NEEDS_AUTHOR
    with pytest.raises(StorageError, match="claims require"):
        core.publish(state.id)


def test_stale_research_approval_cannot_be_reused(project, reviewed):
    core, state, _ = reviewed
    final = project / state.final_draft_path
    workflow = AuthorEditWorkflow(project)
    workflow.adopt(state.id, request_for(project, state, final.read_text() + "\nA claim."))
    decision = ClaimReviewDecision(
        draft_sha256=hash_file(final), approved_by="Author", notes="Reviewed evidence"
    )
    (final.parent / "research.json").write_text(json.dumps(research_brief()))
    with pytest.raises(StorageError, match="research hash"):
        workflow.approve_claims(state.id, decision)
    with pytest.raises(StorageError, match="Research hash"):
        core.publish(state.id)


def test_adoption_and_claim_review_do_not_override_validation(project, reviewed):
    core, state, _ = reviewed
    final = project / state.final_draft_path
    workflow = AuthorEditWorkflow(project)
    adopted = workflow.adopt(state.id, request_for(project, state, "Too short."))
    assert adopted.status == RunStatus.NEEDS_AUTHOR
    with pytest.raises(StorageError, match="validation errors"):
        workflow.approve_claims(
            state.id,
            ClaimReviewDecision(
                draft_sha256=hash_file(final), approved_by="Author", notes="Please approve"
            ),
        )
    with pytest.raises(StorageError, match="claims require"):
        core.publish(state.id)


def test_review_rejects_blank_decision_and_unedited_run(project, reviewed):
    _, state, _ = reviewed
    final = project / state.final_draft_path
    workflow = AuthorEditWorkflow(project)
    decision = ClaimReviewDecision(
        draft_sha256=hash_file(final), approved_by="Author", notes="Reviewed"
    )
    with pytest.raises(StorageError, match="no author-edit"):
        workflow.approve_claims(state.id, decision)
    with pytest.raises(StorageError, match="reviewer"):
        workflow.approve_claims(state.id, decision.model_copy(update={"approved_by": " "}))


def test_invalid_research_is_rejected_without_mutation(project, reviewed):
    _, state, _ = reviewed
    final = project / state.final_draft_path
    original = final.read_bytes()
    research = ResearchBrief(**{**research_brief(), "sources": []})
    request = request_for(project, state, final.read_text() + "\nA claim.", research=research)
    with pytest.raises(StorageError, match="research fails"):
        AuthorEditWorkflow(project).adopt(state.id, request)
    assert final.read_bytes() == original


def test_cli_adoption_and_claim_review(project, reviewed, capsys):
    from content_creator.cli import main

    _, state, _ = reviewed
    final = project / state.final_draft_path
    supplied = project / "edited.md"
    supplied.write_text(final.read_text() + "\nA claim.")
    assert (
        main(
            [
                "--root",
                str(project),
                "adopt-edit",
                state.id,
                "--draft-file",
                str(supplied),
                "--expected-sha256",
                hash_file(final),
                "--idempotency-key",
                "cli-edit",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "needs_author"
    assert (
        main(
            [
                "--root",
                str(project),
                "approve-edit-claims",
                state.id,
                "--draft-sha256",
                hash_file(final),
                "--approved-by",
                "Author",
                "--notes",
                "Reviewed",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "ready"
    assert (
        main(
            [
                "--root",
                str(project),
                "adopt-edit",
                state.id,
                "--draft-file",
                str(project / "absent.md"),
                "--expected-sha256",
                hash_file(final),
                "--idempotency-key",
                "missing-file",
            ]
        )
        == 8
    )


def test_change_during_validation_is_preserved(project, reviewed, monkeypatch):
    import content_creator.author_edits as adoption

    _, state, _ = reviewed
    final = project / state.final_draft_path
    request = request_for(project, state, final.read_text() + "\n")
    validate = adoption.validate_author_edit

    def concurrent_change(root, current, draft):
        result = validate(root, current, draft)
        final.write_text("Concurrent author changes")
        return result

    monkeypatch.setattr(adoption, "validate_author_edit", concurrent_change)
    with pytest.raises(StorageError, match="changed concurrently"):
        AuthorEditWorkflow(project).adopt(state.id, request)
    assert final.read_text() == "Concurrent author changes"


def test_coordinator_surfaces_claim_review_instead_of_publication(project, reviewed):
    from content_creator.coordinator import ContentCoordinator

    _, state, _ = reviewed
    final = project / state.final_draft_path
    AuthorEditWorkflow(project).adopt(
        state.id, request_for(project, state, final.read_text() + "\nA claim.")
    )
    actions = ContentCoordinator(project).next_actions(state.id)["actions"]
    assert actions[0]["id"] == "review-changed-claims"
    assert not any(a["id"].startswith("publish") for a in actions)
