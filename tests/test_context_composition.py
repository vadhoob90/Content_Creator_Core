"""Verify runtime context composition evidence and author-facing inspection."""

from __future__ import annotations

import json

from conftest import passing_critique, valid_draft

from content_creator.cli import main
from content_creator.commands.run_commands import _render_context_trace
from content_creator.context_composition import ContextCompositionStore
from content_creator.domain import WorkOrder
from content_creator.orchestrator import Orchestrator
from content_creator.prompting import PromptAssembler
from content_creator.providers import FakeProvider, ProviderRegistry


def _orchestrator(project):
    return Orchestrator(
        project,
        registry=ProviderRegistry(
            {
                "anthropic": FakeProvider(
                    {
                        "writer": [valid_draft()],
                        "critic": [passing_critique()],
                    }
                )
            }
        ),
    )


def test_prompt_composition_identifies_exact_learning_records(project):
    memory_path = project / "profiles" / "default" / "learnings" / "memory.json"
    memory_path.write_text(
        json.dumps(
            {
                "version": 1,
                "records": [
                    {
                        "id": "voice-writer-01",
                        "role": "writer",
                        "principle": "Prefer a restrained close.",
                        "evidence": "Explicit author feedback.",
                        "status": "active",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    composition = PromptAssembler(project).compose(
        "writer",
        WorkOrder(request="write", topic="topic"),
    )
    loaded = [layer for layer in composition.layers if layer.status == "loaded"]
    voice_learning = next(layer for layer in loaded if layer.category == "voice-learnings")

    assert loaded[0].source == "core:contracts/agent-harness.md"
    assert loaded[1].source == "core:contracts/roles/writer.md"
    assert loaded[2].source == "agents/writer.md"
    assert voice_learning.source == "profiles/default/learnings/memory.json"
    assert voice_learning.record_ids == ["voice-writer-01"]
    assert voice_learning.content_hash.startswith("sha256:")


def test_run_persists_privacy_safe_invocation_composition(project):
    draft = valid_draft()
    orchestrator = _orchestrator(project)
    state = orchestrator.start(
        WorkOrder(
            request="write",
            topic="topic",
            content_pack="general-text",
            format="text",
            pack_options={"length": "50:600"},
        )
    )

    manifest = ContextCompositionStore(project).read(state.id)
    serialized = manifest.model_dump_json()

    assert [item.role for item in manifest.invocations] == ["writer", "critic"]
    assert manifest.invocations[0].phase == "draft-01"
    assert manifest.invocations[0].invocation_id == "0001-writer"
    assert "runtime:payload" in serialized
    assert f"runs/{state.id}/work-order.json" in serialized
    assert draft not in serialized
    assert "Write or revise the piece" not in serialized


def test_preflight_and_historical_cli_are_read_only_and_human_friendly(project, capsys):
    assert (
        main(
            [
                "--root",
                str(project),
                "personalisation",
                "explain",
                "--role",
                "writer",
                "--json",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["mode"] == "preflight"
    assert report["instruction_layers"][0]["source"] == ("core:contracts/agent-harness.md")
    assert not (project / "runs").exists()

    state = _orchestrator(project).start(
        WorkOrder(
            request="write",
            topic="topic",
            content_pack="general-text",
            format="text",
            pack_options={"length": "50:600"},
        )
    )
    assert main(["--root", str(project), "context", "show", state.id]) == 0
    rendered = capsys.readouterr().out
    assert f"Runtime context composition for run {state.id}" in rendered
    assert "load Core harness from core:contracts/agent-harness.md" in rendered
    assert "payload task-payload: runtime:payload" in rendered


def test_live_trace_uses_stderr_and_does_not_print_private_prompt(project, capsys):
    orchestrator = _orchestrator(project)
    orchestrator.runner.enable_context_trace(_render_context_trace)
    orchestrator.start(
        WorkOrder(
            request="private request text",
            topic="private topic text",
            content_pack="general-text",
            format="text",
            pack_options={"length": "50:600"},
        )
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[context]   1. load Core harness" in captured.err
    assert "[context] Invocation pending: writer" in captured.err
    assert "private request text" not in captured.err
    assert "private topic text" not in captured.err
