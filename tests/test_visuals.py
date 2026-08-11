import json

import pytest

from content_creator.cli import main
from content_creator.domain import RoutePlan, RunState, RunStatus, WorkOrder
from content_creator.packs import PackRegistry
from content_creator.storage import RunStore
from content_creator.visual_components import (
    VisualComponentKind,
    VisualComponentRegistry,
)
from content_creator.visual_requests import VisualRenderRequest, VisualRequestWorkflow
from content_creator.visuals import (
    BoundingBox,
    ExecutionClass,
    RightsStatus,
    VisualAdapter,
    VisualAdapterRegistry,
    VisualApprovalStatus,
    VisualBrief,
    VisualCritique,
    VisualError,
    VisualOutput,
    VisualSource,
    VisualWorkflow,
)


class FixtureRenderer(VisualAdapter):
    name = "fixture-renderer"
    execution_class = ExecutionClass.DETERMINISTIC
    model_or_renderer = "fixture-grid"
    prompt_or_template_version = "1.0"

    def __init__(self, *, copy=None, box=None):
        self.copy = copy
        self.box = box or BoundingBox(x=0.1, y=0.1, width=0.7, height=0.2, role="headline")

    def render(self, brief, parent=None):  # noqa: ARG002 - implements adapter contract
        return VisualOutput(
            content=b"fixture-image-bytes",
            width=1200,
            height=1500,
            format="png",
            extracted_copy=self.copy,
            content_boxes=[self.box],
            metadata={"template": "fixture"},
        )


def reviewed_run(project, pack="linkedin-post"):
    state = RunState(
        status=RunStatus.READY,
        work_order=WorkOrder(
            request="write",
            topic="visual workflow",
            content_pack=pack,
            format="post" if pack == "linkedin-post" else "text",
        ),
        route_plan=RoutePlan(route="no-research", stages=[]),
    )
    store = RunStore(project)
    store.create(state)
    store.write_artifact(state.id, "final.md", "Reviewed content")
    return state


def brief_for(run_id, *, rights=RightsStatus.OWNED):
    return VisualBrief(
        run_id=run_id,
        objective="Make the argument scannable",
        content_connection="Summarises the reviewed post",
        exact_copy=["Systems preserve judgment"],
        platform_profile="linkedin-post",
        aspect_ratios=["4:5"],
        output_formats=["png"],
        safe_area_profiles=["feed"],
        crop_profiles=["composer-thumbnail"],
        hierarchy=["headline", "supporting grid"],
        revision_invariants=["Preserve exact headline", "Preserve grid boundary"],
        sources=[
            VisualSource(
                source_id="source-one",
                uri="workspace://reference.png",
                rights_status=rights,
            )
        ],
        alt_text="A grid showing that systems preserve human judgment.",
        preferred_execution_class=ExecutionClass.DETERMINISTIC,
    )


def workflow_for(project, renderer):
    adapters = VisualAdapterRegistry()
    adapters.register(renderer)
    return VisualWorkflow(project, adapters)


def test_pack_declares_provider_independent_visual_capabilities(project):
    profile = PackRegistry(project).resolve("linkedin-post").visuals

    assert profile.supported is True
    assert profile.required is False
    assert profile.execution_classes == [
        ExecutionClass.DETERMINISTIC,
        ExecutionClass.GENERATIVE,
    ]
    assert profile.aspect_ratios == ["1:1", "4:5"]
    assert profile.destination == "content/linkedin-post/visuals"


def test_core_components_are_versioned_resolvable_and_installed_with_core():
    registry = VisualComponentRegistry.from_core()

    components = registry.resolve(
        role="article-cover",
        execution_class=ExecutionClass.DETERMINISTIC,
        output_format="svg",
        aspect_ratio="16:9",
    )

    assert {item.kind for item in components} >= {
        VisualComponentKind.CONTRACT,
        VisualComponentKind.LAYOUT,
        VisualComponentKind.RENDERER,
        VisualComponentKind.VALIDATOR,
    }
    assert all(item.version and item.provenance == "content-creator-core" for item in components)


def test_natural_language_visual_request_renders_and_records_component_provenance(project):
    state = reviewed_run(project, pack="linkedin-article")
    profile = PackRegistry(project).resolve("linkedin-article").visuals
    (project / "visual-brand.json").write_text(
        json.dumps(
            {
                "background": "#112233",
                "accent": "#ABCDEF",
                "font_family": "Inter",
            }
        ),
        encoding="utf-8",
    )

    result = VisualRequestWorkflow(project).render(
        profile=profile,
        request=VisualRenderRequest(
            run_id=state.id,
            pack_id="linkedin-article",
            pack_version="1.0.0",
            request="Create an image for this article.",
            role="article-cover",
            variants=2,
        ),
    )

    manifest = json.loads(
        (project / "runs" / state.id / "visuals" / "manifest.json").read_text(encoding="utf-8")
    )
    invocation = json.loads(
        (project / "runs" / state.id / "visuals" / "invocation.json").read_text(encoding="utf-8")
    )

    assert [asset.variant_name for asset in result.assets] == ["concept-1", "concept-2"]
    assert all(asset.validation and asset.validation.passed for asset in result.assets)
    assert all(asset.format == "svg" for asset in result.assets)
    assert all(
        (project / "runs" / state.id / asset.relative_path).exists() for asset in result.assets
    )
    rendered_svg = (project / "runs" / state.id / result.assets[0].relative_path).read_text(
        encoding="utf-8"
    )
    assert "#112233" in rendered_svg
    assert "#ABCDEF" in rendered_svg
    assert "Inter" in rendered_svg
    assert {item["id"] for item in manifest["components"]} >= {
        "core.visual-brief-contract",
        "core.editorial-card-layout",
        "core.deterministic-svg-renderer",
    }
    assert manifest["assets"][0]["components"] == manifest["components"]
    assert invocation["decision"] == "visual-workflow"
    assert invocation["request"] == "Create an image for this article."
    assert invocation["role"] == "article-cover"


def test_visual_request_reports_unsupported_role_and_pack_support(project):
    article = reviewed_run(project, pack="linkedin-article")
    article_pack = PackRegistry(project).resolve("linkedin-article")
    with pytest.raises(VisualError, match="does not support visual role 'banner'"):
        VisualRequestWorkflow(project).render(
            profile=article_pack.visuals,
            request=VisualRenderRequest(
                run_id=article.id,
                pack_id=article_pack.id,
                pack_version=article_pack.version,
                request="Create an image for this article.",
                role="banner",
            ),
        )

    text = reviewed_run(project, pack="general-text")
    text_pack = PackRegistry(project).resolve("general-text")
    with pytest.raises(VisualError, match="does not support visual assets"):
        VisualRequestWorkflow(project).render(
            profile=text_pack.visuals,
            request=VisualRenderRequest(
                run_id=text.id,
                pack_id=text_pack.id,
                pack_version=text_pack.version,
                request="Create an image for this text.",
            ),
        )


def test_visual_cli_lists_components_and_renders_a_review_variant(project, capsys):
    state = reviewed_run(project, pack="linkedin-article")

    assert (
        main(
            [
                "--root",
                str(project),
                "visual",
                "components",
                state.id,
                "--role",
                "article-cover",
            ]
        )
        == 0
    )
    components = json.loads(capsys.readouterr().out)
    assert "core.deterministic-svg-renderer" in {item["id"] for item in components}

    assert (
        main(
            [
                "--root",
                str(project),
                "visual",
                "render",
                state.id,
                "--role",
                "article-cover",
                "--request",
                "Create an image for this article.",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["assets"][0]["format"] == "svg"
    assert rendered["assets"][0]["validation"]["passed"] is True

    assert (
        main(
            [
                "--root",
                str(project),
                "visual",
                "render",
                state.id,
                "--role",
                "banner",
            ]
        )
        == 8
    )
    error = json.loads(capsys.readouterr().out)
    assert error["error_type"] == "VisualError"
    assert "available: article-cover" in error["error"]


def test_visual_lifecycle_persists_lineage_and_publishes_only_approved_asset(project):
    state = reviewed_run(project)
    renderer = FixtureRenderer(copy=["Systems preserve judgment"])
    workflow = workflow_for(project, renderer)
    profile = PackRegistry(project).resolve("linkedin-post").visuals
    workflow.create_brief(brief_for(state.id), profile)

    concept = workflow.execute(state.id)
    revision = workflow.execute(state.id, parent_asset_id=concept.asset_id)
    result = workflow.validate(state.id, revision.asset_id, profile)
    workflow.record_critique(
        state.id,
        revision.asset_id,
        VisualCritique(summary="Ready", strengths=["Clear hierarchy"]),
    )
    workflow.select(state.id, revision.asset_id)

    with pytest.raises(VisualError, match="not been approved"):
        workflow.publish(state.id, profile)

    approved = workflow.approve(state.id, revision.asset_id)
    target = workflow.publish(state.id, profile)

    assert concept.relative_path.startswith("visuals/concepts/")
    assert revision.parent_asset_id == concept.asset_id
    assert revision.revision == 2
    assert revision.alt_text == brief_for(state.id).alt_text
    assert revision.sources[0].rights_status == RightsStatus.OWNED
    assert result.passed is True
    assert approved.status == VisualApprovalStatus.APPROVED
    assert target and target.read_bytes() == b"fixture-image-bytes"


def test_exact_copy_mismatch_blocks_validation(project):
    state = reviewed_run(project)
    workflow = workflow_for(project, FixtureRenderer(copy=["Systems replace judgment"]))
    profile = PackRegistry(project).resolve("linkedin-post").visuals
    workflow.create_brief(brief_for(state.id), profile)
    asset = workflow.execute(state.id)

    validation = workflow.validate(state.id, asset.asset_id, profile)

    assert validation.passed is False
    assert "exact-copy-mismatch" in {item.code for item in validation.diagnostics}


def test_exact_copy_without_ocr_or_deterministic_evidence_does_not_silently_pass(project):
    state = reviewed_run(project)
    workflow = workflow_for(project, FixtureRenderer(copy=None))
    profile = PackRegistry(project).resolve("linkedin-post").visuals
    workflow.create_brief(brief_for(state.id), profile)
    asset = workflow.execute(state.id)

    validation = workflow.validate(state.id, asset.asset_id, profile)

    assert "exact-copy-unverified" in {item.code for item in validation.diagnostics}


def test_unsafe_crop_and_missing_rights_block_validation(project):
    state = reviewed_run(project)
    renderer = FixtureRenderer(
        copy=["Systems preserve judgment"],
        box=BoundingBox(x=0.1, y=0.7, width=0.7, height=0.2, role="headline"),
    )
    workflow = workflow_for(project, renderer)
    profile = PackRegistry(project).resolve("linkedin-post").visuals
    workflow.create_brief(brief_for(state.id, rights=RightsStatus.UNVERIFIED), profile)
    asset = workflow.execute(state.id)

    validation = workflow.validate(state.id, asset.asset_id, profile)
    codes = {item.code for item in validation.diagnostics}

    assert validation.passed is False
    assert "crop-risk" in codes
    assert "unresolved-reuse-rights" in codes


def test_text_only_pack_remains_compatible_and_visual_brief_is_rejected(project):
    state = reviewed_run(project, pack="general-text")
    workflow = workflow_for(project, FixtureRenderer(copy=[]))
    profile = PackRegistry(project).resolve("general-text").visuals
    incompatible = brief_for(state.id).model_copy(
        update={"platform_profile": "general-text", "exact_copy": []}
    )

    assert workflow.ensure_publication_ready(state.id, profile) is None
    with pytest.raises(VisualError, match="does not support"):
        workflow.create_brief(incompatible, profile)


def test_asset_with_unsupported_execution_class_is_not_selectable(project):
    state = reviewed_run(project)
    renderer = FixtureRenderer(copy=["Systems preserve judgment"])
    renderer.execution_class = ExecutionClass.GENERATIVE
    workflow = workflow_for(project, renderer)
    profile = (
        PackRegistry(project)
        .resolve("linkedin-post")
        .visuals.model_copy(update={"execution_classes": [ExecutionClass.DETERMINISTIC]})
    )
    workflow.create_brief(brief_for(state.id), profile)
    asset = workflow.execute(state.id, adapter_name=renderer.name)

    validation = workflow.validate(state.id, asset.asset_id, profile)

    assert "unsupported-execution-class" in {item.code for item in validation.diagnostics}
    with pytest.raises(VisualError, match="validated"):
        workflow.select(state.id, asset.asset_id)
