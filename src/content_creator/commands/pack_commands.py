"""Content-pack creation and inspection command handlers."""

from __future__ import annotations

import json

from ..packs import PackRegistry
from ..storage import RunStore
from .context import CommandContext


def _create_pack(context: CommandContext, packs: PackRegistry) -> int:
    """Create pack."""
    arguments = context.arguments
    destination = context.root / "packs" / arguments.pack_id
    if destination.exists():
        raise ValueError(f"Content pack already exists: {arguments.pack_id}")
    destination.mkdir(parents=True)
    manifest = {
        "schema_version": "1.0",
        "id": arguments.pack_id,
        "version": "0.1.0",
        "extends": arguments.extends,
        "format": "text",
        "destination": f"content/{arguments.pack_id}/published",
        "rubric": "rubric.yaml",
    }
    RunStore._atomic_text(destination / "pack.json", json.dumps(manifest, indent=2))
    RunStore._atomic_text(destination / "rubric.yaml", "dimensions: {}\nhard_gates: []")
    RunStore._atomic_text(destination / "validators.yaml", "append: []")
    RunStore._atomic_text(
        destination / "README.md",
        f"# {arguments.pack_id}\n\nExtends `{arguments.extends}`.",
    )
    (destination / "evals").mkdir()
    context.emit(packs.resolve(arguments.pack_id))
    return 0


def manage_pack(context: CommandContext) -> int:
    """Manage pack."""
    packs = PackRegistry(context.root)
    arguments = context.arguments
    if arguments.pack_command == "create":
        return _create_pack(context, packs)
    if arguments.pack_command == "list":
        context.emit([pack.model_dump(mode="json") for pack in packs.list()])
        return 0
    should_resolve = arguments.pack_command in {"show", "validate"} or arguments.resolved
    context.emit(
        packs.resolve(arguments.pack_id) if should_resolve else packs.get(arguments.pack_id)
    )
    return 0
