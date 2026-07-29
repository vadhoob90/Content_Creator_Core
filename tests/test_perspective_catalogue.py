import json

import pytest
import yaml
from conftest import passing_critique, valid_draft

from content_creator.domain import RunStatus, WorkOrder
from content_creator.orchestrator import Orchestrator
from content_creator.perspectives import (
    PerspectiveCatalogueStore,
    PerspectiveEntry,
    PerspectiveError,
    PerspectiveProvenance,
    PerspectiveRegistry,
)
from content_creator.providers import FakeProvider, ProviderRegistry


def _activate(project, context_id, statement, entry_id):
    registry = PerspectiveRegistry(project, "default")
    registry.stage(
        context_id,
        [
            PerspectiveEntry(
                id=entry_id,
                statement=statement,
                provenance=[
                    PerspectiveProvenance(
                        kind="direct_author_input",
                        reference="author review",
                    )
                ],
            )
        ],
    )
    registry.activate(context_id, "Owner")


def _automatic_workspace(project):
    (project / "content-creator.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "perspective": {
                    "mode": "automatic",
                    "allow_multiple": True,
                    "ask_when_ambiguous": True,
                    "show_resolution": True,
                    "conflict_policy": "propose-update",
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _catalogue(project):
    path = project / "profiles" / "default" / "perspectives" / "catalogue.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "routing_only": True,
                "contexts": [
                    {
                        "context_id": "professional-training",
                        "display_name": "Professional training",
                        "summary": "Positions about training design.",
                        "use_when": ["training design"],
                        "avoid_when": ["scheduling"],
                        "related_contexts": ["organisational-change"],
                    },
                    {
                        "context_id": "organisational-change",
                        "display_name": "Organisational change",
                        "summary": "Positions about sustainable change.",
                        "use_when": ["organisational adoption"],
                        "avoid_when": [],
                        "related_contexts": ["professional-training"],
                    },
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def test_automatic_catalogue_resolution_loads_only_model_selected_contexts(project):
    _activate(
        project,
        "professional-training",
        "Training should teach recognition and escalation.",
        "training-001",
    )
    _activate(
        project,
        "organisational-change",
        "Change requires sustained organisational capability.",
        "change-001",
    )
    _automatic_workspace(project)
    _catalogue(project)
    fake = FakeProvider(
        {
            "briefing-agent": [
                {
                    "mode": "automatic",
                    "selected": [
                        {
                            "context_id": "professional-training",
                            "reason": "The brief concerns training design.",
                            "confidence": 0.96,
                        },
                        {
                            "context_id": "organisational-change",
                            "reason": "The brief concerns adoption.",
                            "confidence": 0.87,
                        },
                    ],
                }
            ],
            "writer": [valid_draft()],
            "critic": [passing_critique()],
        }
    )
    orchestrator = Orchestrator(
        project,
        registry=ProviderRegistry({"anthropic": fake}),
    )

    state = orchestrator.start(
        WorkOrder(
            request="Explain how training supports organisational adoption.",
            topic="Training and adoption",
            content_pack="general-text",
            format="text",
            provider="anthropic",
            pack_options={"length": "50:600"},
        )
    )

    assert state.status == RunStatus.READY
    assert [
        item.context_id for item in state.work_order.perspective_selections
    ] == ["professional-training", "organisational-change"]
    assert all(
        item.version == "1.0.0"
        for item in state.work_order.perspective_selections
    )
    run = project / "runs" / state.id
    resolution = json.loads(
        (run / "perspective-resolution.json").read_text(encoding="utf-8")
    )
    context = json.loads(
        (run / "resolved-context.json").read_text(encoding="utf-8")
    )
    assert resolution["mode"] == "automatic"
    assert len(context["perspectives"]) == 2
    writer_request = next(item for item in fake.requests if item.role == "writer")
    assert "recognition and escalation" in writer_request.system
    assert "sustained organisational capability" in writer_request.system
    resolver_request = next(
        item for item in fake.requests if item.role == "briefing-agent"
    )
    assert "Training should teach" not in resolver_request.user
    assert '"routing_only": true' in resolver_request.user


def test_catalogue_verification_rejects_unknown_or_inactive_contexts(project):
    _activate(
        project,
        "professional-training",
        "Training should teach recognition.",
        "training-001",
    )
    _catalogue(project)

    result = PerspectiveCatalogueStore(project, "default").verify()

    assert not result["valid"]
    assert result["unknown_contexts"] == ["organisational-change"]


def test_automatic_resolver_rejects_model_selected_unknown_context(project):
    _activate(
        project,
        "professional-training",
        "Training should teach recognition.",
        "training-001",
    )
    _automatic_workspace(project)
    _catalogue(project)
    fake = FakeProvider(
        {
            "briefing-agent": [
                {
                    "mode": "automatic",
                    "selected": [
                        {
                            "context_id": "invented-context",
                            "reason": "Unsupported model selection.",
                            "confidence": 0.9,
                        }
                    ],
                }
            ]
        }
    )
    orchestrator = Orchestrator(
        project,
        registry=ProviderRegistry({"anthropic": fake}),
    )

    with pytest.raises(PerspectiveError, match="unavailable contexts"):
        orchestrator.start(
            WorkOrder(
                request="Write about training.",
                topic="Training",
                provider="anthropic",
            )
        )

    assert not list((project / "runs").glob("*/state.json"))
