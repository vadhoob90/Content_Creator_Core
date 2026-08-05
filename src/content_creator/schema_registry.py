"""Provide schema registry contracts and behavior."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Type

from pydantic import BaseModel

from .domain import RunState, WorkOrder
from .perspectives import PerspectiveManifest
from .storage import RunStore
from .visuals import VisualManifest
from .voices import VoiceManifest

CURRENT_SCHEMA_VERSION = "1.0"
SUPPORTED_READ_VERSIONS = ("legacy", "1.0")


class SchemaCompatibilityError(ValueError):
    """Report schema compatibility failures."""

    pass


SCHEMA_MODELS: Dict[str, Type[BaseModel]] = {
    "work-order": WorkOrder,
    "run-state": RunState,
    "voice-manifest": VoiceManifest,
    "perspective-manifest": PerspectiveManifest,
    "visual-manifest": VisualManifest,
}


def schema_catalogue() -> Dict[str, Dict[str, Any]]:
    """Return the schema catalogue.

    Returns:
        Dict[str, Dict[str, Any]]: The structured resulting data for schema catalogue.
    """
    result: Dict[str, Dict[str, Any]] = {}
    for name, model in SCHEMA_MODELS.items():
        schema = model.model_json_schema()
        schema["$id"] = "https://content-creator.dev/schemas/{}/{}.json".format(
            name, CURRENT_SCHEMA_VERSION
        )
        result[name] = {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "supported_read_versions": list(SUPPORTED_READ_VERSIONS),
            "schema": schema,
        }
    return result


def write_schema_bundle(destination: Path) -> Dict[str, Any]:
    """Write the schema bundle.

    Args:
        destination (Path): The destination filesystem path.

    Returns:
        Dict[str, Any]: The structured resulting data for write schema bundle.
    """
    destination.mkdir(parents=True, exist_ok=True)
    entries = []
    for name, item in schema_catalogue().items():
        filename = "{}-{}.schema.json".format(name, item["schema_version"])
        RunStore._atomic_text(
            destination / filename,
            json.dumps(item["schema"], indent=2, sort_keys=True),
        )
        entries.append({"name": name, "version": item["schema_version"], "path": filename})
    index = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "supported_read_versions": list(SUPPORTED_READ_VERSIONS),
        "schemas": entries,
    }
    RunStore._atomic_text(destination / "index.json", json.dumps(index, indent=2))
    return index


def migrate_artifact(kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return the migrate artifact.

    Args:
        kind (str): The domain category used to classify the value.
        payload (Dict[str, Any]): The structured payload to validate or persist.

    Returns:
        Dict[str, Any]: The structured resulting data for migrate artifact.

    Raises:
        SchemaCompatibilityError: If the schema compatibility operation cannot complete.
    """
    if kind not in SCHEMA_MODELS:
        raise SchemaCompatibilityError("Unknown artifact schema: {}".format(kind))
    migrated = deepcopy(payload)
    version = str(migrated.get("schema_version", "legacy"))
    if version not in SUPPORTED_READ_VERSIONS:
        raise SchemaCompatibilityError("Unsupported {} schema version: {}".format(kind, version))
    if version == "legacy":
        migrated["schema_version"] = CURRENT_SCHEMA_VERSION
    return migrated
