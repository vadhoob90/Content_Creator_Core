import json

import pytest
from conftest import passing_critique, valid_draft

from content_creator.domain import (
    PerspectiveSelection,
    RoutePlan,
    RunEvent,
    RunState,
    WorkOrder,
)
from content_creator.orchestrator import Orchestrator
from content_creator.production_manifest import ProductionManifest
from content_creator.production_store import production_run_store
from content_creator.providers import FakeProvider, ProviderRegistry
from content_creator.version import VERSION
from content_creator.versioned_artifacts import hash_file


def _orchestrator(project):
    return Orchestrator(
        project,
        registry=ProviderRegistry(
            {
                "anthropic": FakeProvider(
                    {
                        "writer": [valid_draft()],
                        "critic": [passing_critique(), passing_critique()],
                        "learning-extractor": [{"candidates": []}],
                    }
                )
            }
        ),
    )


def test_review_copy_has_generated_table_while_final_draft_stays_clean(project):
    state = _orchestrator(project).start(
        WorkOrder(
            request="Explain a useful system.",
            topic="Useful system",
            pack_options={"length": "50:600"},
        )
    )
    run = project / "runs" / state.id
    manifest = json.loads((run / "production-manifest.json").read_text(encoding="utf-8"))
    review = (run / "review.md").read_text(encoding="utf-8")
    final = (run / "final.md").read_text(encoding="utf-8")

    assert state.production_manifest_path == f"runs/{state.id}/production-manifest.json"
    assert state.review_draft_path == f"runs/{state.id}/review.md"
    assert manifest["content_pack"]["id"] == "general-text"
    assert manifest["content_pack"]["version"] == "1.0.0"
    assert manifest["core_version"] == VERSION
    assert manifest["core_version_status"] == "captured"
    assert manifest["voice"]["id"] == "default"
    assert manifest["voice"]["version"] == "placeholder"
    assert manifest["voice"]["source_kind"] == "legacy-placeholder"
    assert manifest["voice"]["provenance_status"] == "partial"
    assert manifest["perspectives"] == []
    assert manifest["status"] == "ready"
    assert {item["role"] for item in manifest["invocations"]} == {"writer", "critic"}
    assert "## Production details" in review
    assert f"| Core | v{VERSION} |" in review
    assert "| Content pack | general-text v1.0.0 |" in review
    assert "| Voice governance | active; epoch unavailable; evidence digest unavailable |" in review
    assert final.strip() in review
    assert "Production details" not in final


@pytest.mark.parametrize("perspective_count", [0, 1, 2])
def test_manifest_renders_zero_one_or_multiple_perspectives(project, perspective_count):
    selections = [
        PerspectiveSelection(
            context_id=f"context-{index}",
            version=f"{index}.0.0",
            reason="test selection",
            confidence=0.9,
        )
        for index in range(1, perspective_count + 1)
    ]
    state = RunState(
        work_order=WorkOrder(
            request="write",
            topic="topic",
            voice_version="1.0.0",
            resolved_voice=True,
            perspective_selections=selections,
        ),
        route_plan=RoutePlan(route="test", stages=[]),
    )
    production_run_store(project).create(state)
    run = project / "runs" / state.id
    manifest = json.loads((run / "production-manifest.json").read_text(encoding="utf-8"))
    summary = (run / "production-manifest.md").read_text(encoding="utf-8")

    assert len(manifest["perspectives"]) == perspective_count
    if perspective_count:
        assert "context-1 v1.0.0" in summary
    else:
        assert "| Perspectives | None |" in summary
    if perspective_count == 2:
        assert "context-2 v2.0.0" in summary


def test_revision_and_publication_refresh_manifest_without_decorating_publication(project):
    orchestrator = _orchestrator(project)
    state = orchestrator.start(
        WorkOrder(
            request="Explain a useful system.",
            topic="Useful system",
            pack_options={"length": "50:600"},
        )
    )
    edited = valid_draft().replace("useful writing system", "reviewed writing system", 1)
    revised = orchestrator.revise(
        state.id,
        feedback="Use the reviewed wording.",
        draft=edited,
        idempotency_key="production-manifest-revision",
    )
    published = orchestrator.publish(revised.id, filename="manifest-test.md")
    run = project / "runs" / state.id
    manifest = json.loads((run / "production-manifest.json").read_text(encoding="utf-8"))
    receipt = json.loads(
        (
            project
            / "publication-receipts/content/general-text/published/manifest-test.md.receipt.json"
        ).read_text(encoding="utf-8")
    )
    publication = project / str(published.published_path)

    assert manifest["status"] == "published"
    assert manifest["revision"] == 2
    assert manifest["publication"]["path"] == str(published.published_path)
    assert [item["role"] for item in manifest["invocations"]] == [
        "writer",
        "critic",
        "critic",
        "learning-extractor",
    ]
    assert receipt["content_pack_id"] == "general-text"
    assert receipt["content_pack_version"] == "1.0.0"
    assert "Production details" not in publication.read_text(encoding="utf-8")
    assert "reviewed writing system" in publication.read_text(encoding="utf-8")


def test_legacy_run_is_backfilled_on_next_state_save(project):
    store = production_run_store(project)
    state = RunState(
        work_order=WorkOrder(request="write", topic="legacy"),
        route_plan=RoutePlan(route="legacy", stages=[]),
    )
    run = store.run_dir(state.id)
    run.mkdir(parents=True)
    (run / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")

    loaded = store.load(state.id)
    assert not (run / "production-manifest.json").exists()

    store.save_state(loaded)

    assert (run / "production-manifest.json").is_file()
    assert store.load(state.id).production_manifest_path == (
        f"runs/{state.id}/production-manifest.json"
    )
    manifest = json.loads((run / "production-manifest.json").read_text(encoding="utf-8"))
    assert manifest["core_version"] is None
    assert manifest["core_version_status"] == "unavailable"
    assert manifest["voice"]["version"] is None
    assert manifest["voice"]["artifact_digest"] is None
    assert manifest["voice"]["learning_epoch"] is None
    assert manifest["voice"]["provenance_status"] == "unavailable"


def _governed_context(version="1.0.0", epoch_id="activation-1", epoch_hash="sha256:epoch-1"):
    return {
        "schema_version": "1.1",
        "engine_version": VERSION,
        "voice": {
            "id": "governed-author",
            "version": version,
            "status": "active",
            "version_status": "active",
            "manifest_hash": f"sha256:voice-{version}",
            "evidence_baseline_hash": f"sha256:evidence-{version}",
            "learning_epoch_id": epoch_id,
            "learning_epoch_status": "active",
            "learning_epoch_hash": epoch_hash,
            "private_prompt": "must never enter production metadata",
        },
        "perspectives": [
            {
                "context_id": "operating-model",
                "version": "2.0.0",
                "status": "active",
                "manifest_hash": "sha256:perspective-2",
                "private_text": "must also remain private",
            }
        ],
        "private_payload": "not production provenance",
    }


def test_manifest_uses_persisted_governance_snapshot_with_privacy_safe_hashes(project):
    store = production_run_store(project)
    state = RunState(
        work_order=WorkOrder(
            request="write",
            topic="governed provenance",
            voice_id="governed-author",
            voice_version="1.0.0",
            resolved_voice=True,
            perspective_selections=[
                PerspectiveSelection(
                    context_id="operating-model",
                    version="2.0.0",
                    reason="selected",
                    confidence=0.95,
                )
            ],
        ),
        route_plan=RoutePlan(route="test", stages=[]),
    )
    store.create(state)
    store.write_artifact(state.id, "resolved-context.json", _governed_context())
    store.save_state(state)

    path = store.run_dir(state.id) / "production-manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(manifest)

    assert manifest["core_version"] == VERSION
    assert manifest["voice"] == {
        "id": "governed-author",
        "version": "1.0.0",
        "source_kind": "approved-version",
        "artifact_digest": "sha256:voice-1.0.0",
        "lifecycle_status_at_generation": "active",
        "version_status_at_generation": "active",
        "evidence_baseline_digest": "sha256:evidence-1.0.0",
        "learning_epoch": {
            "id": "activation-1",
            "status": "active",
            "digest": "sha256:epoch-1",
        },
        "provenance_status": "complete",
        "provenance_reason": None,
    }
    assert manifest["perspectives"][0]["manifest_digest"] == "sha256:perspective-2"
    assert manifest["perspectives"][0]["provenance_status"] == "complete"
    assert "must never" not in serialized
    assert "private_payload" not in serialized


def test_existing_run_keeps_generation_snapshot_after_voice_epoch_transition(project):
    store = production_run_store(project)
    state = RunState(
        work_order=WorkOrder(
            request="write",
            topic="stable provenance",
            voice_id="governed-author",
            voice_version="1.0.0",
            resolved_voice=True,
        ),
        route_plan=RoutePlan(route="test", stages=[]),
    )
    store.create(state)
    store.write_artifact(state.id, "resolved-context.json", _governed_context())
    store.save_state(state)
    path = store.run_dir(state.id) / "production-manifest.json"
    before = json.loads(path.read_text(encoding="utf-8"))

    # Simulate a later active voice version and epoch without touching the run snapshot.
    # The production builder must not use lifecycle events as current voice state.
    state.events.append(RunEvent(name="voice_upgraded", detail="2.0.0"))
    store.save_state(state)
    after = json.loads(path.read_text(encoding="utf-8"))

    assert after["governance_hash"] == before["governance_hash"]
    assert after["voice"] == before["voice"]


def test_revision_links_the_immediate_predecessor_manifest(project):
    store = production_run_store(project)
    state = RunState(
        work_order=WorkOrder(request="write", topic="revision provenance"),
        route_plan=RoutePlan(route="test", stages=[]),
    )
    store.create(state)
    store.write_artifact(state.id, "resolved-context.json", _governed_context())
    store.save_state(state)
    path = store.run_dir(state.id) / "production-manifest.json"
    predecessor = hash_file(path)

    state.revision = 1
    store.save_state(state)
    revised = json.loads(path.read_text(encoding="utf-8"))

    assert revised["previous_revision_manifest_hash"] == predecessor
    preserved = revised["previous_revision_manifest_hash"]
    store.save_state(state)
    assert (
        json.loads(path.read_text(encoding="utf-8"))["previous_revision_manifest_hash"] == preserved
    )


def test_separate_runs_capture_pre_and_post_upgrade_governance(project):
    store = production_run_store(project)
    manifests = []
    for version, epoch_id, epoch_digest in (
        ("1.0.0", "activation-1", "sha256:epoch-1"),
        ("2.0.0", "activation-2", "sha256:epoch-2"),
    ):
        state = RunState(
            work_order=WorkOrder(
                request="write",
                topic="upgrade boundary",
                voice_id="governed-author",
                voice_version=version,
                resolved_voice=True,
            ),
            route_plan=RoutePlan(route="test", stages=[]),
        )
        store.create(state)
        store.write_artifact(
            state.id,
            "resolved-context.json",
            _governed_context(version, epoch_id, epoch_digest),
        )
        store.save_state(state)
        manifests.append(
            json.loads(
                (store.run_dir(state.id) / "production-manifest.json").read_text(encoding="utf-8")
            )
        )

    assert manifests[0]["voice"]["version"] == "1.0.0"
    assert manifests[1]["voice"]["version"] == "2.0.0"
    assert manifests[0]["voice"]["learning_epoch"]["id"] == "activation-1"
    assert manifests[1]["voice"]["learning_epoch"]["id"] == "activation-2"
    assert manifests[0]["governance_hash"] != manifests[1]["governance_hash"]


def test_candidate_preview_uses_one_discriminated_artifact_digest(project):
    store = production_run_store(project)
    state = RunState(
        work_order=WorkOrder(
            request="preview",
            topic="candidate provenance",
            voice_id="governed-author",
            voice_version="candidate",
        ),
        route_plan=RoutePlan(route="preview", stages=[]),
    )
    context = _governed_context()
    context["voice"].pop("manifest_hash")
    context["voice"]["version"] = "candidate"
    context["voice"]["candidate_hash"] = "sha256:candidate"
    store.create(state)
    store.write_artifact(state.id, "resolved-context.json", context)
    store.save_state(state)

    manifest = json.loads(
        (store.run_dir(state.id) / "production-manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["voice"]["source_kind"] == "candidate-preview"
    assert manifest["voice"]["artifact_digest"] == "sha256:candidate"
    assert "manifest_digest" not in manifest["voice"]
    assert "candidate_digest" not in manifest["voice"]


def test_schema_reads_pre_governance_manifest_without_inventing_fields(project):
    store = production_run_store(project)
    state = RunState(
        work_order=WorkOrder(request="write", topic="old schema"),
        route_plan=RoutePlan(route="legacy", stages=[]),
    )
    store.create(state)
    path = store.run_dir(state.id) / "production-manifest.json"
    legacy = json.loads(path.read_text(encoding="utf-8"))
    for field in (
        "previous_revision_manifest_hash",
        "core_version",
        "core_version_status",
        "governance_hash",
    ):
        legacy.pop(field)
    legacy["voice"] = {"id": "default", "version": "placeholder"}
    legacy["perspectives"] = []

    parsed = ProductionManifest.model_validate(legacy)

    assert parsed.schema_version == "1.0"
    assert parsed.core_version is None
    assert parsed.core_version_status == "unavailable"
    assert parsed.governance_hash is None
    assert parsed.voice.provenance_status == "unavailable"
