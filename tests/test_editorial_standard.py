import shutil
from pathlib import Path

import pytest

from content_creator.agent_resources import ROLE_FILES, AgentWorkspace
from content_creator.context import resolved_context
from content_creator.domain import WorkOrder
from content_creator.packs import PackRegistry
from content_creator.prompting import PromptAssembler
from content_creator.versioned_artifacts import hash_file
from content_creator.voices import VoiceRegistry


@pytest.mark.parametrize("role", ROLE_FILES)
def test_editorial_standard_is_shared_only_by_content_writer_and_critic(tmp_path, role):
    AgentWorkspace(tmp_path).scaffold()
    composition = PromptAssembler(tmp_path).compose(role)
    layer = next(layer for layer in composition.layers if layer.category == "core-editorial")
    if role in {"writer", "critic"}:
        assert layer.status == "loaded"
        assert layer.owner == "core"
        assert layer.source == "core:contracts/editorial-standard.md"
        assert "# Core editorial standard" in composition.prompt
        assert layer.content_hash == hash_file(
            PromptAssembler(tmp_path).resources.core / "contracts/editorial-standard.md"
        )
    else:
        assert layer.status == "skipped"
        assert layer.reason == "role-does-not-receive-editorial-standard"
        assert "# Core editorial standard" not in composition.prompt


@pytest.mark.parametrize("role", ["writer", "critic"])
def test_legacy_overrides_cannot_hide_core_but_local_voice_rules_survive(tmp_path, role):
    AgentWorkspace(tmp_path).scaffold()
    agent = tmp_path / "agents" / f"{role}.md"
    agent.write_text("Keep the author's terse rhythm and British spelling.", encoding="utf-8")
    (tmp_path / "contracts").mkdir()
    (tmp_path / "contracts/editorial-standard.md").write_text("STALE POLICY", encoding="utf-8")
    (tmp_path / "rubrics").mkdir()
    (tmp_path / "rubrics/core.yaml").write_text("legacy: rubric", encoding="utf-8")
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}

    prompt = PromptAssembler(tmp_path).system_prompt(
        role, WorkOrder(request="Write an update", topic="Release status")
    )

    assert "# Core editorial standard" in prompt
    assert "STALE POLICY" not in prompt
    assert "Keep the author's terse rhythm and British spelling." in prompt
    assert "legacy: rubric" in prompt
    assert before == {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}


def test_package_policy_updates_change_prompt_and_run_provenance(tmp_path, monkeypatch):
    AgentWorkspace(tmp_path).scaffold()
    assembler = PromptAssembler(tmp_path)
    policy = tmp_path / "installed-core/contracts/editorial-standard.md"
    shutil.copytree(assembler.resources.core, policy.parent.parent)
    policy.write_text("Editorial release A", encoding="utf-8")
    monkeypatch.setattr(assembler.resources, "core", policy.parent.parent)
    first = assembler.compose("writer")
    policy.write_text("Editorial release B", encoding="utf-8")
    second = assembler.compose("writer")
    assert "Editorial release A" in first.prompt
    assert "Editorial release B" in second.prompt
    first_layer = next(layer for layer in first.layers if layer.category == "core-editorial")
    second_layer = next(layer for layer in second.layers if layer.category == "core-editorial")
    assert first_layer.content_hash != second_layer.content_hash

    order = WorkOrder(request="Write an update", topic="Release status")
    context = resolved_context(
        tmp_path,
        order,
        PackRegistry(tmp_path).get(order.content_pack),
        VoiceRegistry(tmp_path).resolve("default"),
    )
    installed = Path(__file__).resolve().parents[1] / "src/content_creator/resources"
    assert context["component_hashes"]["editorial_standard"] == hash_file(
        installed / "contracts/editorial-standard.md"
    )
