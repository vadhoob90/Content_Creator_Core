import pytest
from conftest import passing_critique, research_brief, valid_draft

from content_creator.author_edits import AuthorEditRequest, AuthorEditWorkflow
from content_creator.coordinator import ContentCoordinator
from content_creator.domain import ResearchBrief, WorkOrder
from content_creator.draft_bundles.service import DraftBundleWorkflow
from content_creator.edit_contracts import ClaimReviewDecision
from content_creator.orchestrator import Orchestrator
from content_creator.providers import FakeProvider, ProviderRegistry
from content_creator.versioned_artifacts import hash_file
from content_creator.visual_contracts import (
    RightsStatus,
    VisualBrief,
    VisualCritique,
    VisualError,
    VisualManifest,
    VisualSource,
)
from content_creator.visual_imports import VisualImportRequest, import_visual
from content_creator.visual_slots import slot_for


@pytest.fixture
def slot_run(project):
    fake = FakeProvider(
        {
            "writer": [valid_draft(), valid_draft()],
            "critic": [passing_critique(), passing_critique()],
            "learning-extractor": [{"candidates": []}],
        }
    )
    core = Orchestrator(project, registry=ProviderRegistry({"anthropic": fake}))
    state = core.start(
        WorkOrder(
            request="Article",
            topic="Visual slots",
            content_pack="linkedin-article",
            format="article",
            pack_options={"length": "50:600"},
        )
    )
    return core, state


def define_slot(core, state, name, index=0, anchor=False):
    pack = core.packs.resolve(state.work_order.content_pack)
    role = "article-inline-diagram" if index % 2 else "comparison"
    brief = VisualBrief(
        run_id=state.id,
        slot_id=name,
        objective=f"Explain {name}",
        content_connection="Explain the article without adding claims",
        role=role,
        platform_profile=f"{pack.id}:{role}",
        aspect_ratios=["16:9"],
        output_formats=["svg"],
        output_width=1920,
        output_height=1080,
        alt_text=f"Diagram showing {name}",
        display_order=index,
        insertion_anchor=f"<!-- visual:{name} -->" if anchor else None,
        revision_invariants=["Preserve labelled connections"],
    )
    return core.visuals.create_brief(brief, pack.visuals)


def register_slot(core, state, name, tmp_path, parent=None, approve=True):
    path = tmp_path / f"{name}.svg"
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080">'
        f'<text x="10" y="30">{name}</text></svg>'
    )
    profile = core.packs.resolve(state.work_order.content_pack).visuals
    asset = import_visual(
        core.root,
        profile,
        VisualImportRequest(
            run_id=state.id,
            slot_id=name,
            path=str(path),
            parent_asset_id=parent,
            source=VisualSource(
                uri=path.as_uri(), creator="Author", rights_status=RightsStatus.OWNED
            ),
        ),
    )
    assert asset.validation.passed
    core.visuals.record_critique(
        state.id,
        asset.asset_id,
        VisualCritique(summary="Meaningful connections and accurate labels"),
    )
    core.visuals.select(state.id, asset.asset_id)
    return (
        core.visuals.approve(state.id, asset.asset_id)
        if approve
        else core.visuals.asset(state.id, asset.asset_id)
    )


def test_five_slots_bundle_export_and_publication_replacement(project, slot_run, tmp_path):
    core, state = slot_run
    final = project / state.final_draft_path
    names = [f"diagram-{i}" for i in range(5)]
    edited = (
        final.read_text()
        + "\nUsing agents for writing is not new.\n"
        + "\n".join(f"<!-- visual:{name} -->" for name in names)
    )
    edits = AuthorEditWorkflow(project)
    state = edits.adopt(
        state.id,
        AuthorEditRequest(
            draft=edited,
            expected_sha256=hash_file(final),
            idempotency_key="anchors",
            research=ResearchBrief(**research_brief()),
        ),
    )
    assets = []
    for index, name in enumerate(names):
        define_slot(core, state, name, index, anchor=True)
        assets.append(register_slot(core, state, name, tmp_path))
    hook = core.start(
        WorkOrder(request="Hook", topic="Visual hook", content_pack="linkedin-post", format="post")
    )
    bundles = DraftBundleWorkflow(project)
    bundles.create("launch", "Five visual review")
    bundles.add("launch", "article", state.id)
    bundles.add("launch", "hook", hook.id)
    before = {str(p): p.read_bytes() for p in (project / "runs").rglob("*") if p.is_file()}
    exported = bundles.export("launch", "drafts/launch")
    assert len(exported.artifacts) == 7
    assert len({a.exported_path for a in exported.artifacts}) == 7
    assert exported.members[0].claim_review_required
    assert len(exported.members[0].visuals) == 5
    text = (project / "drafts/launch/article.md").read_text()
    assert "<!-- visual:" not in text
    for visual in exported.members[0].visuals:
        assert visual.alt_text in text
    assert before == {str(p): p.read_bytes() for p in (project / "runs").rglob("*") if p.is_file()}
    assert len(ContentCoordinator(project).next_actions(state.id)["visual_slots"]) == 5
    edits.approve_claims(
        state.id,
        ClaimReviewDecision(
            draft_sha256=hash_file(final),
            research_sha256=hash_file(final.parent / "research.json"),
            approved_by="Author",
            notes="Reviewed all prose and placement edits",
        ),
    )
    published = core.publish(state.id)
    assert len(published.published_media) == 5
    original_text = project / published.published_path
    original_bytes = original_text.read_bytes()
    assert "<!-- visual:" not in original_text.read_text()
    assert core.publications.verify(run_id=state.id)["status"] == "ok"
    retained = {m.slot_id: m.model_dump() for m in published.published_media}
    replacement = register_slot(core, published, names[2], tmp_path, parent=assets[2].asset_id)
    replaced = core.replace_visual(state.id, replacement.asset_id)
    assert len(replaced.published_media) == 5
    assert original_text.read_bytes() == original_bytes
    assert replaced.published_path != published.published_path
    for media in replaced.published_media:
        if media.slot_id != names[2]:
            assert media.model_dump() == retained[media.slot_id]
    assert replacement.asset_id in (project / replaced.published_path).read_text()
    assert core.publications.verify(run_id=state.id)["status"] == "ok"


def test_slot_revisions_do_not_change_other_approvals(project, slot_run, tmp_path):
    core, state = slot_run
    define_slot(core, state, "first")
    first = register_slot(core, state, "first", tmp_path)
    define_slot(core, state, "second", 1)
    second = register_slot(core, state, "second", tmp_path)
    manifest = core.visuals._load_manifest(state.id)
    retained = slot_for(manifest, "second").model_dump()
    define_slot(core, state, "first")
    changed = core.visuals._load_manifest(state.id)
    assert slot_for(changed, "second").model_dump() == retained
    assert slot_for(changed, "first").selected_asset_id is None
    with pytest.raises(VisualError, match="brief revision"):
        core.visuals.select(state.id, first.asset_id)
    new = register_slot(core, state, "first", tmp_path, parent=first.asset_id)
    assert new.revision == 2
    assert core.visuals.asset(state.id, second.asset_id).status.value == "approved"
    assert (project / f"runs/{state.id}/visuals/slots/first/r0001/brief.json").exists()
    assert (project / f"runs/{state.id}/visuals/slots/first/r0002/brief.json").exists()


def test_changed_alt_or_text_invalidates_slot_approval(project, slot_run, tmp_path):
    core, state = slot_run
    define_slot(core, state, "chart")
    asset = register_slot(core, state, "chart", tmp_path)
    path = project / f"runs/{state.id}/visuals/manifest.json"
    original = path.read_bytes()
    manifest = VisualManifest.model_validate_json(original)
    manifest.assets[0].alt_text = "Different accessibility claim"
    path.write_text(manifest.model_dump_json())
    with pytest.raises(VisualError, match="approval"):
        core.visuals.ensure_publication_assets(
            state.id, core.packs.resolve("linkedin-article").visuals
        )
    path.write_bytes(original)
    final = project / state.final_draft_path
    AuthorEditWorkflow(project).adopt(
        state.id,
        AuthorEditRequest(
            draft=final.read_text() + "\nNew claim.",
            expected_sha256=hash_file(final),
            idempotency_key="late-claim",
        ),
    )
    with pytest.raises(VisualError, match="stale text"):
        core.visuals.approve(state.id, asset.asset_id)


def test_unsupported_diagram_renderer_and_unverified_import(project, slot_run, tmp_path):
    core, state = slot_run
    define_slot(core, state, "chart")
    with pytest.raises(VisualError, match="compatible adapter"):
        core.visuals.execute(state.id, "core-deterministic-svg", slot_id="chart")
    path = tmp_path / "unknown.svg"
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080"/>')
    asset = import_visual(
        project,
        core.packs.resolve("linkedin-article").visuals,
        VisualImportRequest(
            run_id=state.id, slot_id="chart", path=str(path), source=VisualSource(uri=path.as_uri())
        ),
    )
    assert not asset.validation.passed
    assert any(d.code == "unresolved-reuse-rights" for d in asset.validation.diagnostics)
    with pytest.raises(VisualError, match="validation"):
        core.visuals.select(state.id, asset.asset_id)


def test_multi_slot_schema_cannot_be_silently_downgraded(slot_run):
    core, state = slot_run
    define_slot(core, state, "chart")
    manifest = core.visuals._load_manifest(state.id).model_dump()
    assert manifest["schema_version"] == "1.1"
    manifest["schema_version"] = "1.0"
    with pytest.raises(ValueError, match="schema 1.1"):
        VisualManifest.model_validate(manifest)
