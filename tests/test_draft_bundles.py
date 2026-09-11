import json
from pathlib import Path

import pytest
from conftest import passing_critique, valid_draft

from content_creator.author_edits import AuthorEditRequest, AuthorEditWorkflow
from content_creator.domain import WorkOrder
from content_creator.draft_bundles.service import DraftBundleWorkflow
from content_creator.orchestrator import Orchestrator
from content_creator.providers import FakeProvider, ProviderRegistry
from content_creator.storage import StorageError
from content_creator.versioned_artifacts import hash_file


@pytest.fixture
def bundle_runs(project):
    fake = FakeProvider(
        {
            "writer": [valid_draft(), valid_draft()],
            "critic": [passing_critique(), passing_critique()],
        }
    )
    core = Orchestrator(project, registry=ProviderRegistry({"anthropic": fake}))
    article = core.start(
        WorkOrder(
            request="Article",
            topic="Article",
            content_pack="linkedin-article",
            format="article",
            pack_options={"length": "50:600"},
        )
    )
    hook = core.start(
        WorkOrder(request="Hook", topic="Hook", content_pack="linkedin-post", format="post")
    )
    return article, hook


def build_bundle(project, bundle_runs):
    article, hook = bundle_runs
    bundles = DraftBundleWorkflow(project)
    bundles.create("launch", "Launch review")
    bundles.add("launch", "article", article.id)
    bundles.add("launch", "hook", hook.id)
    return bundles


def test_bundle_pins_separate_lineages_without_mutating_runs(project, bundle_runs):
    article, hook = bundle_runs
    before = {str(p): p.read_bytes() for p in (project / "runs").rglob("*") if p.is_file()}
    bundles = build_bundle(project, bundle_runs)
    bundle = bundles.show("launch")
    assert [member.name for member in bundle.members] == ["article", "hook"]
    assert [member.content_pack for member in bundle.members] == [
        "linkedin-article",
        "linkedin-post",
    ]
    assert bundle.members[0].content_session_id != bundle.members[1].content_session_id
    assert bundle.members[0].sha256 == hash_file(project / article.final_draft_path)
    assert bundle.members[1].run_id == hook.id
    assert bundles.review("launch").stale is False
    assert before == {str(p): p.read_bytes() for p in (project / "runs").rglob("*") if p.is_file()}


def test_changed_member_requires_explicit_update_before_export(project, bundle_runs):
    article, _ = bundle_runs
    bundles = build_bundle(project, bundle_runs)
    final = project / article.final_draft_path
    AuthorEditWorkflow(project).adopt(
        article.id,
        AuthorEditRequest(
            draft=final.read_text() + "\nChanged claim.",
            expected_sha256=hash_file(final),
            idempotency_key="bundle-edit",
        ),
    )
    review = bundles.review("launch")
    assert review.stale
    assert review.members[0].stale
    with pytest.raises(StorageError, match="stale"):
        bundles.export("launch", "drafts/launch")
    bundles.update("launch", "article")
    assert not bundles.review("launch").stale
    manifest = bundles.export("launch", "drafts/launch")
    assert manifest.members[0].claim_review_required
    assert manifest.purpose == "draft-review"


def test_export_is_deterministic_idempotent_and_has_no_publication_side_effects(
    project, bundle_runs
):
    bundles = build_bundle(project, bundle_runs)
    before = {str(p): p.read_bytes() for p in project.rglob("*") if p.is_file()}
    preview = bundles.export("launch", "drafts/launch", preview=True)
    assert not (project / "drafts").exists()
    first = bundles.export("launch", "drafts/launch")
    second = bundles.export("launch", "drafts/launch")
    assert first == second == preview
    assert {f.exported_path for f in first.artifacts} == {"article.md", "hook.md"}
    assert first.bundle_id == "launch"
    assert (
        json.loads((project / "drafts/launch/package-manifest.json").read_text())["purpose"]
        == "draft-review"
    )
    for name, content in before.items():
        assert Path(name).read_bytes() == content
    assert not (project / "publication-receipts").exists()


def test_membership_changes_are_explicit_and_order_is_stable(project, bundle_runs):
    article, hook = bundle_runs
    bundles = build_bundle(project, bundle_runs)
    old = bundles.show("launch")
    repeated = bundles.add("launch", "article", article.id)
    assert repeated == old
    with pytest.raises(StorageError, match="exists"):
        bundles.add("launch", "article", hook.id)
    unchanged = bundles.update("launch", "article")
    assert unchanged == old
    updated = bundles.remove("launch", "article")
    assert [m.name for m in updated.members] == ["hook"]
    assert updated.revision == old.revision + 1


@pytest.mark.parametrize(
    "destination",
    [
        "../drafts/escape",
        "content/linkedin-post/published/drafts/launch",
        "runs/drafts/launch",
        "drafts",
    ],
)
def test_export_rejects_non_draft_and_unsafe_destinations(project, bundle_runs, destination):
    bundles = build_bundle(project, bundle_runs)
    with pytest.raises(StorageError):
        bundles.export("launch", destination)


def test_selected_visual_export_rewrites_markdown_and_preserves_provenance(project, bundle_runs):
    from content_creator.visual_requests import VisualRenderRequest, VisualRequestWorkflow

    article, _ = bundle_runs
    core = Orchestrator(project)
    pack = core.packs.resolve(article.work_order.content_pack)
    visual = (
        VisualRequestWorkflow(project, workflow=core.visuals)
        .render(
            profile=pack.visuals,
            request=VisualRenderRequest(
                run_id=article.id,
                pack_id=pack.id,
                pack_version=pack.version,
                request="A diagram for the article",
            ),
        )
        .assets[0]
    )
    from content_creator.visual_contracts import VisualCritique

    core.visuals.record_critique(article.id, visual.asset_id, VisualCritique(summary="Clear"))
    core.visuals.select(article.id, visual.asset_id)
    final = project / article.final_draft_path
    AuthorEditWorkflow(project).adopt(
        article.id,
        AuthorEditRequest(
            draft=final.read_text() + f"\n![Old alt]({visual.relative_path})\n",
            expected_sha256=hash_file(final),
            idempotency_key="visual-link",
        ),
    )
    bundles = build_bundle(project, bundle_runs)
    manifest = bundles.export("launch", "drafts/launch")
    media = next(a for a in manifest.artifacts if a.kind == "visual")
    assert media.visual.asset_id == visual.asset_id
    assert media.visual.approval_state != "approved"
    assert media.source_sha256 == media.exported_sha256
    assert media.source_sha256 == hash_file(project / media.source_path)
    assert (project / "drafts/launch" / media.exported_path).read_bytes() == (
        project / media.source_path
    ).read_bytes()
    assert media.exported_path in (project / "drafts/launch/article.md").read_text()
    assert visual.alt_text in (project / "drafts/launch/article.md").read_text()
    assert any("visual requires" in f for f in bundles.review("launch").members[0].findings)
    core.visuals.select(article.id, visual.asset_id)
    assert not bundles.review("launch").stale
    (project / media.source_path).write_bytes(b"tampered")
    assert bundles.review("launch").stale
    with pytest.raises(StorageError, match="hash changed"):
        bundles.export("launch", "drafts/other")


def test_single_run_export_and_cli_membership(project, bundle_runs, capsys):
    from content_creator.cli import main

    article, hook = bundle_runs
    base = ["--root", str(project)]
    commands = [
        ["bundle", "create", "cli", "--title", "CLI draft"],
        ["bundle", "add", "cli", "article", article.id],
        ["bundle", "update", "cli", "article", "--run-id", hook.id],
        ["bundle", "show", "cli"],
        ["bundle", "review", "cli"],
        ["bundle", "export", "cli", "drafts/cli", "--preview"],
        ["bundle", "remove", "cli", "article"],
        ["export-draft", article.id, "drafts/single"],
    ]
    for command in commands:
        assert main(base + command) == 0
        result = json.loads(capsys.readouterr().out)
    assert result["bundle_id"] is None
    assert result["artifacts"][0]["exported_path"] == "content.md"
    assert not (project / "drafts/cli").exists()
    assert (project / "drafts/single/content.md").exists()
    assert main(base + ["bundle", "create", "bad", "--title", " "]) != 0


@pytest.mark.parametrize("conflict", ["modified", "extra", "incomplete", "symlink", "file"])
def test_existing_destination_never_overwritten(project, bundle_runs, conflict):
    bundles = build_bundle(project, bundle_runs)
    target = project / "drafts/launch"
    bundles.export("launch", "drafts/launch")
    if conflict == "modified":
        (target / "article.md").write_text("Author changed the exported draft")
    elif conflict == "extra":
        (target / "notes.md").write_text("Keep")
    elif conflict == "incomplete":
        (target / "package-manifest.json").unlink()
    elif conflict == "symlink":
        (target / "notes.md").symlink_to(target / "article.md")
    else:
        import shutil

        shutil.rmtree(target)
        target.write_text("Keep")
    before = {str(p): p.read_bytes() for p in target.rglob("*") if p.is_file()}
    with pytest.raises(StorageError):
        bundles.export("launch", "drafts/launch")
    assert before == {str(p): p.read_bytes() for p in target.rglob("*") if p.is_file()}


def test_failed_package_write_rolls_back_and_can_retry(project, bundle_runs, monkeypatch):
    import content_creator.draft_bundles.exporting as exporting

    bundles = build_bundle(project, bundle_runs)
    original = exporting.os.link

    def fail_manifest(source, target):
        if target.name == "package-manifest.json":
            raise OSError("Injected disk failure")
        original(source, target)

    with monkeypatch.context() as patch:
        patch.setattr(exporting.os, "link", fail_manifest)
        with pytest.raises(OSError, match="Injected"):
            bundles.export("launch", "drafts/launch")
    assert not (project / "drafts/launch").exists()
    assert not list((project / "drafts").glob(".draft-export-*"))
    bundles.export("launch", "drafts/launch")


def test_rejects_symlink_and_member_publication_destinations(project, bundle_runs):
    bundles = build_bundle(project, bundle_runs)
    (project / "drafts").symlink_to(project / "runs", target_is_directory=True)
    with pytest.raises(StorageError, match="symlink"):
        bundles.export("launch", "drafts/launch")
    (project / "drafts").unlink()
    from content_creator.draft_bundles.paths import export_destination

    with pytest.raises(StorageError, match="publication"):
        export_destination(project, "drafts/launch", ("drafts/launch",))
    with pytest.raises(StorageError, match="publication"):
        export_destination(project, "drafts/launch", ("drafts/launch/media",))


def test_bundle_identity_validation_and_empty_export(project):
    bundles = DraftBundleWorkflow(project)
    for name in ("../escape", "Mixed-Case", "con", "a/b"):
        with pytest.raises(StorageError):
            bundles.create(name, "Draft")
    created = bundles.create("empty", "Empty")
    repeated = bundles.create("empty", "Empty")
    assert repeated == created
    with pytest.raises(StorageError, match="different title"):
        bundles.create("empty", "Changed")
    with pytest.raises(StorageError, match="empty"):
        bundles.export("empty", "drafts/empty")
    unchanged = bundles.remove("empty", "absent")
    assert unchanged == created
    with pytest.raises(StorageError, match="Unknown bundle member"):
        bundles.update("empty", "absent")
    path = project / "draft-bundles/empty.json"
    path.write_text(created.model_dump_json().replace('"1.0"', '"99.0"'))
    with pytest.raises(StorageError, match="unsupported"):
        bundles.show("empty")


def test_unadopted_text_and_interrupted_edit_are_rejected(project, bundle_runs):
    article, _ = bundle_runs
    bundles = build_bundle(project, bundle_runs)
    final = project / article.final_draft_path
    original = final.read_bytes()
    final.write_bytes(original + b"Unadopted")
    with pytest.raises(StorageError, match="Adopt"):
        bundles.update("launch", "article")
    final.write_bytes(original)
    (final.parent / "author-edit-transaction.json").write_text("{}")
    with pytest.raises(StorageError, match="Recover"):
        bundles.export("launch", "drafts/launch")


def test_legacy_text_run_uses_available_hash_without_inventing_evidence(project, bundle_runs):
    article, _ = bundle_runs
    final = project / article.final_draft_path
    (final.parent / "draft-integrity.json").unlink()
    bundles = build_bundle(project, bundle_runs)
    preview = bundles.export_run(article.id, "drafts/legacy", preview=True)
    assert "draft-integrity.json" not in preview.members[0].evidence_hashes
    assert "context-composition.json" in preview.members[0].evidence_hashes
    final.write_bytes(final.read_bytes() + b"Changed legacy bytes")
    with pytest.raises(StorageError, match="legacy"):
        bundles.update("launch", "article")


def test_review_context_change_invalidates_bundle_pin(project, bundle_runs):
    article, _ = bundle_runs
    bundles = build_bundle(project, bundle_runs)
    context = project / "runs" / article.id / "context-composition.json"
    context.write_bytes(context.read_bytes() + b"\n")
    assert bundles.review("launch").members[0].stale
    with pytest.raises(StorageError, match="stale"):
        bundles.export("launch", "drafts/changed-context")
