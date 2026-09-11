import json
from io import BytesIO

import pytest
from PIL import Image
from test_visual_slots import define_slot, register_slot
from test_visual_slots import slot_run as slot_run

from content_creator.cli import main
from content_creator.storage import RunStore
from content_creator.versioned_artifacts import ActivationLock
from content_creator.visual_contracts import VisualCritique, VisualError
from content_creator.visual_imports import inspect_image
from content_creator.visual_migration import migrate_slots
from content_creator.visual_placement import place_visuals
from content_creator.visual_requests import VisualRenderRequest, VisualRequestWorkflow
from content_creator.visual_slots import slot_for


def test_migration_preserves_legacy_history_and_approval(project, slot_run, tmp_path):
    core, state = slot_run
    pack = core.packs.resolve("linkedin-article")
    asset = (
        VisualRequestWorkflow(project, workflow=core.visuals)
        .render(
            pack.visuals,
            VisualRenderRequest(
                run_id=state.id,
                pack_id=pack.id,
                pack_version=pack.version,
                request="Article cover",
                variants=2,
            ),
        )
        .assets[0]
    )
    core.visuals.record_critique(state.id, asset.asset_id, VisualCritique(summary="Clear cover"))
    core.visuals.select(state.id, asset.asset_id)
    core.visuals.approve(state.id, asset.asset_id)
    path = project / f"runs/{state.id}/visuals/manifest.json"
    before = path.read_bytes()
    migrated = migrate_slots(project, state.id)
    assert len(migrated.assets) == 2
    assert slot_for(migrated, "legacy").selected_asset_id == asset.asset_id
    assert slot_for(migrated, "legacy").approval_sha256
    assert (path.parent / "legacy-manifest.json").read_bytes() == before
    assert migrate_slots(project, state.id) == migrated
    define_slot(core, state, "inline")
    register_slot(core, state, "inline", tmp_path)
    assert len(core.visuals.ensure_publication_assets(state.id, pack.visuals)) == 2
    with pytest.raises(VisualError, match="complete visual collection"):
        core.visuals.ensure_publication_ready(state.id, pack.visuals)
    with pytest.raises(VisualError, match="Specify a slot"):
        core.visuals.execute(state.id)
    unchanged = path.read_bytes()
    with pytest.raises(VisualError, match="Specify --slot"):
        VisualRequestWorkflow(project, workflow=core.visuals).render(
            pack.visuals,
            VisualRenderRequest(
                run_id=state.id, pack_id=pack.id, pack_version=pack.version, request="A new cover"
            ),
        )
    assert path.read_bytes() == unchanged


def test_collection_publication_rolls_back_all_files_and_manifest(
    project, slot_run, tmp_path, monkeypatch
):
    core, state = slot_run
    for name in ["first", "second"]:
        define_slot(core, state, name)
        register_slot(core, state, name, tmp_path)
    manifest = project / f"runs/{state.id}/visuals/manifest.json"
    before = manifest.read_bytes()

    def fail_issue(*_args, **_kwargs):
        raise OSError("Injected receipt failure")

    monkeypatch.setattr(core.publications, "issue", fail_issue)
    with pytest.raises(OSError, match="Injected"):
        core.publish(state.id)
    assert manifest.read_bytes() == before
    assert not list((project / "content/linkedin-article/published").glob("*.md"))
    assert not list((project / "content/linkedin-article/visuals").glob("*.svg"))
    assert not list((project / "content").rglob(".publication-staging-*"))
    assert core.store.load(state.id).published_path is None


def test_slot_replacement_failure_preserves_current_publication(
    project, slot_run, tmp_path, monkeypatch
):
    core, state = slot_run
    define_slot(core, state, "chart")
    original = register_slot(core, state, "chart", tmp_path)
    published = core.publish(state.id)
    replacement = register_slot(core, published, "chart", tmp_path, parent=original.asset_id)
    before = {str(p): p.read_bytes() for p in (project / "content").rglob("*") if p.is_file()}
    atomic = RunStore.atomic_bytes

    def fail_receipt(path, content):
        if ".receipt" in path.name:
            raise OSError("Injected receipt failure")
        atomic(path, content)

    monkeypatch.setattr(RunStore, "atomic_bytes", fail_receipt)
    with pytest.raises(OSError, match="Injected"):
        core.replace_visual(state.id, replacement.asset_id)
    assert core.store.load(state.id).published_path == published.published_path
    assert before == {
        str(p): p.read_bytes() for p in (project / "content").rglob("*") if p.is_file()
    }


def test_slot_mutations_respect_author_edit_lock_and_journal(project, slot_run):
    core, state = slot_run
    run = project / "runs" / state.id
    with ActivationLock(run / ".author-edit.lock", "locked"):
        with pytest.raises(VisualError, match="Another run"):
            define_slot(core, state, "blocked")
    (run / "author-edit-transaction.json").write_text("{}")
    with pytest.raises(VisualError, match="Recover"):
        define_slot(core, state, "blocked")
    assert not (run / "visuals/slots").exists()


@pytest.mark.parametrize("count", [0, 2])
def test_missing_or_ambiguous_anchors_rejected(count):
    anchor = "<!-- visual:chart -->"
    with pytest.raises(VisualError, match="ambiguous"):
        place_visuals(
            (anchor + "\n") * count,
            "runs/example/final.md",
            [
                {
                    "source_path": "runs/example/visuals/chart.svg",
                    "anchor": anchor,
                    "alt_text": "Chart",
                }
            ],
        )


def test_unsupported_and_unresolved_anchor_rejected():
    for anchor in ["Heading", None]:
        with pytest.raises(VisualError):
            place_visuals(
                "<!-- visual:chart -->",
                "runs/example/final.md",
                [
                    {
                        "source_path": "runs/example/visuals/chart.svg",
                        "anchor": anchor,
                        "alt_text": "Chart",
                    }
                ],
            )


@pytest.mark.parametrize("format_name", ["PNG", "JPEG", "WEBP"])
def test_raster_import_decodes_real_bytes_and_rejects_corruption(format_name):
    stream = BytesIO()
    Image.new("RGB", (160, 90), "blue").save(stream, format=format_name)
    content = stream.getvalue()
    result = inspect_image(content)
    assert (result.width, result.height) == (160, 90)
    assert result.content == content
    with pytest.raises(VisualError, match="malformed"):
        inspect_image(content[:25])


@pytest.mark.parametrize(
    "content",
    [
        b'<svg width="100" height="100"><script/></svg>',
        b'<svg width="100" height="100"><image href="remote.png"/></svg>',
        b'<svg width="100" height="100"><style>external</style></svg>',
        b"<svg/>",
        b'<!DOCTYPE svg><svg width="100" height="100"/>',
        b"not an image",
    ],
)
def test_invalid_or_external_svg_not_registered(content):
    with pytest.raises(VisualError):
        inspect_image(content)


def test_cli_slot_brief_import_review_and_projection(project, slot_run, tmp_path, capsys):
    core, state = slot_run
    brief = define_slot(core, state, "chart")
    path = tmp_path / "brief.json"
    path.write_text(brief.model_dump_json())
    base = ["--root", str(project)]
    assert main(base + ["visual", "brief", state.id, str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["brief_revision"] == 2
    image = tmp_path / "image.svg"
    image.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080"/>')
    request = tmp_path / "import.json"
    request.write_text(
        json.dumps(
            {
                "run_id": state.id,
                "slot_id": "chart",
                "path": str(image),
                "source": {"uri": image.as_uri(), "rights_status": "owned", "creator": "Author"},
            }
        )
    )
    assert main(base + ["visual", "import", state.id, str(request)]) == 0
    asset = json.loads(capsys.readouterr().out)
    assert asset["validation"]["passed"]
    assert asset["status"] == "draft"
    production = json.loads((project / f"runs/{state.id}/production-manifest.json").read_text())
    assert production["visual_slots"][0]["slot_id"] == "chart"
    assert main(base + ["coordinator", "next-actions", state.id]) == 0
    assert json.loads(capsys.readouterr().out)["visual_slots"][0]["requires_review"]


def test_slot_render_retains_each_invocation(project, slot_run):
    from content_creator.visual_contracts import VisualBrief

    core, state = slot_run
    profile = core.packs.resolve("linkedin-article").visuals
    core.visuals.create_brief(
        VisualBrief(
            run_id=state.id,
            slot_id="cover",
            role="article-cover",
            objective="Recognisable editorial cover",
            content_connection="Article cover",
            platform_profile="linkedin-article:article-cover",
            aspect_ratios=["16:9"],
            output_formats=["svg"],
            output_width=1920,
            output_height=1080,
            alt_text="The article headline",
            exact_copy=["The article headline"],
        ),
        profile,
    )
    request = VisualRenderRequest(
        run_id=state.id,
        pack_id="linkedin-article",
        pack_version="1.0",
        slot_id="cover",
        request="Render the reviewed slot brief",
    )
    workflow = VisualRequestWorkflow(project, workflow=core.visuals)
    first = workflow.render(profile, request)
    second = workflow.render(profile, request)
    assert first.invocation.slot_id == "cover"
    assert first.invocation.brief_sha256 == second.invocation.brief_sha256
    assert first.assets[0].validation.passed
    assert (
        len(
            list(
                (project / f"runs/{state.id}/visuals/slots/cover/r0001/invocations").glob("*.json")
            )
        )
        == 2
    )
    with pytest.raises(VisualError, match="Update the slot brief"):
        workflow.render(profile, request.model_copy(update={"alt_text": "Changed"}))


def test_replacing_one_slot_preserves_another_slots_pending_selection(slot_run, tmp_path):
    core, state = slot_run
    define_slot(core, state, "first")
    original = register_slot(core, state, "first", tmp_path)
    define_slot(core, state, "second", 1)
    register_slot(core, state, "second", tmp_path)
    published = core.publish(state.id)
    old_second = published.published_media[1].model_dump()
    replacement = register_slot(core, state, "first", tmp_path, parent=original.asset_id)
    define_slot(core, state, "second", 1)
    pending = register_slot(core, state, "second", tmp_path, approve=False)
    replaced = core.replace_visual(state.id, replacement.asset_id)
    assert replaced.published_media[1].model_dump() == old_second
    assert (
        slot_for(core.visuals._load_manifest(state.id), "second").selected_asset_id
        == pending.asset_id
    )
    assert core.publications.verify(run_id=state.id)["status"] == "ok"


def test_replacement_cannot_bless_changed_published_text(project, slot_run, tmp_path):
    from content_creator.orchestrator import OrchestrationError

    core, state = slot_run
    define_slot(core, state, "chart")
    original = register_slot(core, state, "chart", tmp_path)
    published = core.publish(state.id)
    replacement = register_slot(core, state, "chart", tmp_path, parent=original.asset_id)
    text = project / published.published_path
    text.write_text("A changed published claim")
    with pytest.raises(OrchestrationError, match="failed verification"):
        core.replace_visual(state.id, replacement.asset_id)
    assert text.read_text() == "A changed published claim"


def test_code_example_anchors_are_preserved():
    anchor = "<!-- visual:chart -->"
    example = f"```markdown\n{anchor}\n```\n"
    placement = {
        "source_path": "runs/example/visuals/chart.svg",
        "anchor": anchor,
        "alt_text": "Chart",
    }
    with pytest.raises(VisualError, match="ambiguous"):
        place_visuals(example, "runs/example/final.md", [placement])
    assert place_visuals(example + anchor, "runs/example/final.md", [placement]).startswith(example)
