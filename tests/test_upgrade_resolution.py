"""Verify approved chat-first upgrade decisions."""

import json

from conftest import passing_critique, valid_draft

from content_creator.domain import RoutePlan, RunState, RunStatus, WorkOrder
from content_creator.orchestrator import Orchestrator
from content_creator.providers import FakeProvider, ProviderRegistry


def test_adopt_current_pack_revalidates_historical_final_draft(project):
    """Adopt current policy, preserve the decision, and refresh final checks."""
    pack = project / "packs" / "legacy-resolution"
    pack.mkdir()
    (pack / "pack.json").write_text(
        json.dumps(
            {
                "id": "legacy-resolution",
                "version": "1.0.0",
                "extends": "general-text",
                "format": "text",
                "destination": "content/general-text/published",
                "defaults": {"banned_phrases": ["current policy"]},
            }
        ),
        encoding="utf-8",
    )
    orchestrator = Orchestrator(
        project,
        registry=ProviderRegistry({"anthropic": FakeProvider({"critic": [passing_critique()]})}),
    )
    state = RunState(
        id="resolve-current-pack",
        status=RunStatus.READY,
        work_order=WorkOrder(
            request="Draft",
            topic="Draft",
            content_pack="legacy-resolution",
            pack_options={
                "length": "1:600",
                "banned_phrases": ["legacy policy"],
            },
        ),
        route_plan=RoutePlan(
            route="text-none-none",
            stages=["writer"],
            model_profiles={"writer": "balanced", "critic": "balanced"},
        ),
    )
    orchestrator.store.create(state)
    orchestrator.store.write_artifact(state.id, "final.md", valid_draft())
    orchestrator.store.write_artifact(state.id, "claim-provenance.json", {})

    resolved = orchestrator.adopt_current_pack(state.id)

    run = orchestrator.store.run_dir(state.id)
    assert resolved.status == RunStatus.READY
    assert resolved.revision == 1
    assert "banned_phrases" not in resolved.work_order.pack_options
    assert (run / "pack-migration-decision.json").exists()
    assert (run / "validation-01.json").exists()
    assert (run / "critique-01.json").exists()
    assert (run / "quality-01.json").exists()
    assert any(event.name == "current_pack_policy_adopted" for event in resolved.events)
