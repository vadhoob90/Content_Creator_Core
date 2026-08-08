import json
from pathlib import Path

import pytest

from content_creator.cli import main
from content_creator.schema_registry import (
    SchemaCompatibilityError,
    migrate_artifact,
    schema_catalogue,
    write_schema_bundle,
)

FIXTURES = Path(__file__).parent / "fixtures" / "schemas"


def test_schema_catalogue_covers_persisted_public_contracts():
    catalogue = schema_catalogue()

    assert {
        "work-order",
        "run-state",
        "voice-manifest",
        "voice-evolution-change-set",
        "voice-evolution-delta",
        "perspective-manifest",
        "perspective-review-decision",
        "perspective-semantic-artifact",
        "publication-baseline",
        "publication-receipt",
        "visual-manifest",
    } <= set(catalogue)
    assert all(item["schema_version"] == "1.0" for item in catalogue.values())


def test_schema_bundle_is_deterministic_and_indexed(tmp_path):
    index = write_schema_bundle(tmp_path)

    assert index == json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert (tmp_path / "work-order-1.0.schema.json").is_file()


def test_supported_legacy_artifact_is_migrated_without_mutating_input():
    legacy = json.loads((FIXTURES / "legacy-work-order.json").read_text(encoding="utf-8"))

    migrated = migrate_artifact("work-order", legacy)

    assert migrated["schema_version"] == "1.0"
    assert "schema_version" not in legacy


def test_current_models_write_explicit_schema_versions():
    work_order_schema = schema_catalogue()["work-order"]["schema"]
    run_state_schema = schema_catalogue()["run-state"]["schema"]

    assert work_order_schema["properties"]["schema_version"]["default"] == "1.0"
    assert run_state_schema["properties"]["schema_version"]["default"] == "1.0"


def test_unknown_schema_version_is_rejected():
    with pytest.raises(SchemaCompatibilityError, match="Unsupported"):
        migrate_artifact("work-order", {"schema_version": "99.0"})


def test_schema_export_cli_writes_bundle(project, tmp_path):
    assert main(["--workspace", str(project), "schema", "export", str(tmp_path)]) == 0
    assert (tmp_path / "index.json").is_file()
