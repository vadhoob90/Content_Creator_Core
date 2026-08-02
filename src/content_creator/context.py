from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .agent_resources import LEARNING_FILES, ROLE_FILES, AgentWorkspace
from .domain import WorkOrder
from .packs import ContentPack
from .resource_paths import ResourceResolver
from .version import VERSION
from .voices import hash_file


def resolved_context(
    root: Path,
    order: WorkOrder,
    pack: ContentPack,
    voice: dict,
    perspectives: Optional[List[dict]] = None,
) -> Dict[str, Any]:
    resources = ResourceResolver(root)
    hashes = {
        "core_rubric": hash_file(resources.path("rubrics/core.yaml")),
        "pack_manifest": hash_file(resources.path(Path("packs") / pack.id / "pack.json")),
    }
    agent_workspace = AgentWorkspace(root)
    hashes["agent_harness"] = hash_file(agent_workspace.harness_path())
    for role in sorted(ROLE_FILES):
        hashes["agent_contract_{}".format(role)] = hash_file(agent_workspace.contract_path(role))
        hashes["repository_agent_{}".format(role)] = hash_file(agent_workspace.role_path(role))
    for role in sorted(LEARNING_FILES):
        hashes["repository_learning_policy_{}".format(role)] = hash_file(
            agent_workspace.learning_instructions_path(role)
        )
    voice_root = root / voice["path"]
    manifest = voice_root / "manifest.json"
    if manifest.exists():
        hashes["voice_manifest"] = hash_file(manifest)
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for name, value in data.get("component_hashes", {}).items():
            hashes["voice_{}".format(name)] = value
    repository_memory = root / "learnings" / "memory.json"
    repository_learning_ids = []
    if repository_memory.exists():
        repository_learning_ids = [
            item["id"]
            for item in json.loads(repository_memory.read_text(encoding="utf-8")).get("records", [])
            if item.get("status") == "active"
        ]
        hashes["repository_learning_memory"] = hash_file(repository_memory)
    voice_memory = root / "profiles" / order.voice_id / "learnings" / "memory.json"
    voice_learning_ids = []
    if voice_memory.exists():
        voice_learning_ids = [
            item["id"]
            for item in json.loads(voice_memory.read_text(encoding="utf-8")).get("records", [])
            if item.get("status") == "active"
        ]
        hashes["voice_learning_memory"] = hash_file(voice_memory)
    result: Dict[str, Any] = {
        "schema_version": "1.1",
        "engine_version": VERSION,
        "content_pack": {"id": pack.id, "version": pack.version},
        "voice": voice,
        "component_hashes": hashes,
        "active_learning_ids": voice_learning_ids,
        "active_repository_learning_ids": repository_learning_ids,
        "active_voice_learning_ids": voice_learning_ids,
        "resolved_at": datetime.now(UTC).isoformat(),
    }
    resolved_perspectives = perspectives or []
    if resolved_perspectives:
        result["perspective"] = resolved_perspectives[0]
        result["perspectives"] = resolved_perspectives
        for index, perspective in enumerate(resolved_perspectives):
            perspective_root = root / perspective["path"]
            manifest = perspective_root / "manifest.json"
            context_id = perspective["context_id"]
            if index == 0:
                hashes["perspective_manifest"] = hash_file(manifest)
            hashes["perspective_{}_manifest".format(context_id)] = hash_file(manifest)
            data = json.loads(manifest.read_text(encoding="utf-8"))
            for name, value in data.get("component_hashes", {}).items():
                if index == 0:
                    hashes["perspective_{}".format(name)] = value
                hashes["perspective_{}_{}".format(context_id, name)] = value
    else:
        result["perspective"] = None
        result["perspectives"] = []
    return result
