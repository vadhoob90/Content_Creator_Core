"""Update visual references without reconstructing historical production context."""

from pathlib import Path

from .production_manifest import ProductionArtifact, ProductionManifest, render_production_table
from .storage import RunStore
from .versioned_artifacts import hash_file
from .visual_contracts import VisualManifest


def project_visual_manifest(root: Path, run_id: str) -> None:
    """Update only visual evidence in an existing production manifest.

    Args:
        root (Path): Workspace root.
        run_id (str): Run whose visual collection changed.

    Returns:
        None: Existing production metadata gains current visual references.
    """
    run = root / "runs" / run_id
    production = run / "production-manifest.json"
    visuals = run / "visuals/manifest.json"
    if not production.exists() or not visuals.exists():
        return
    manifest = ProductionManifest.model_validate_json(production.read_bytes())
    collection = VisualManifest.model_validate_json(visuals.read_bytes())
    manifest.visual_slots = collection.slots
    manifest.artifacts = [a for a in manifest.artifacts if a.kind != "visual-manifest"]
    manifest.artifacts.append(
        ProductionArtifact(
            kind="visual-manifest",
            path=str(visuals.relative_to(root)),
            content_hash=hash_file(visuals),
        )
    )
    RunStore.atomic_bytes(production, (manifest.model_dump_json(indent=2) + "\n").encode())
    RunStore.atomic_bytes(
        run / "production-manifest.md", (render_production_table(manifest).rstrip() + "\n").encode()
    )
