from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .domain import WorkOrder
from .packs import ContentPack
from .resource_paths import ResourceResolver
from .voices import hash_file


def resolved_context(
    root: Path,
    order: WorkOrder,
    pack: ContentPack,
    voice: dict,
    perspective: Optional[dict] = None,
) -> dict:
    resources = ResourceResolver(root)
    hashes = {
        "core_rubric": hash_file(resources.path("rubrics/core.yaml")),
        "pack_manifest": hash_file(
            resources.path(Path("packs") / pack.id / "pack.json")
        ),
    }
    voice_root = root / voice["path"]
    manifest = voice_root / "manifest.json"
    if manifest.exists():
        hashes["voice_manifest"] = hash_file(manifest)
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for name, value in data.get("component_hashes", {}).items():
            hashes["voice_{}".format(name)] = value
    memory = root / "profiles" / order.voice_id / "learnings" / "memory.json"
    learning_ids = []
    if memory.exists():
        learning_ids = [
            item["id"]
            for item in json.loads(memory.read_text(encoding="utf-8")).get(
                "records", []
            )
            if item.get("status") == "active"
        ]
        hashes["learning_memory"] = hash_file(memory)
    result = {
        "schema_version": "1.0",
        "engine_version": "0.2.0",
        "content_pack": {"id": pack.id, "version": pack.version},
        "voice": voice,
        "component_hashes": hashes,
        "active_learning_ids": learning_ids,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }
    if perspective:
        result["perspective"] = perspective
        perspective_root = root / perspective["path"]
        manifest = perspective_root / "manifest.json"
        hashes["perspective_manifest"] = hash_file(manifest)
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for name, value in data.get("component_hashes", {}).items():
            hashes["perspective_{}".format(name)] = value
    else:
        result["perspective"] = None
    return result
