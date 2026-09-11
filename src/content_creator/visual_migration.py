"""Convert legacy singleton selection into an explicit governed placement."""

from pathlib import Path

from .storage import RunStore
from .versioned_artifacts import hash_file
from .visual_contracts import (
    VisualApprovalStatus,
    VisualBrief,
    VisualError,
    VisualManifest,
    VisualSlot,
)
from .visual_mutation import visual_lock
from .visual_slots import approval_hash, brief_path


def migrate_slots(root: Path, run_id: str) -> VisualManifest:
    """Preserve legacy artifacts while binding their current selection to a legacy slot.

    Migration preserves the historical manifest and brief verbatim. Only the
    current selected candidate gets a verified brief binding; other candidates
    remain historical records without reconstructed approval context.

    Args:
        root (Path): Workspace root.
        run_id (str): Existing single-visual run.

    Returns:
        VisualManifest: Current schema 1.1 collection.

    Raises:
        VisualError: If selected media or brief evidence cannot be verified.
    """
    store = RunStore(root)
    with visual_lock(root, run_id):
        run = store.run_dir(run_id)
        path = run / "visuals/manifest.json"
        manifest = VisualManifest.model_validate_json(path.read_bytes())
        if manifest.slots:
            return manifest
        brief = VisualBrief.model_validate_json((run / "visual_brief.json").read_bytes())
        asset = next((a for a in manifest.assets if a.asset_id == manifest.selected_asset_id), None)
        if (
            asset is None
            or hash_file(run / asset.relative_path) != "sha256:" + asset.sha256
            or asset.alt_text != brief.alt_text
        ):
            raise VisualError(
                "Legacy migration requires matching selected bytes and brief alt text"
            )
        for source, backup in [
            (path, run / "visuals/legacy-manifest.json"),
            (run / "visual_brief.json", run / "visuals/legacy-brief.json"),
        ]:
            if backup.exists() and backup.read_bytes() != source.read_bytes():
                raise VisualError("Conflicting legacy migration backup; inspect before retrying")
            RunStore.atomic_bytes(backup, source.read_bytes())
        brief.slot_id = "legacy"
        brief.brief_revision = 1
        relative = brief_path("legacy", 1)
        store.write_artifact(run_id, relative, brief)
        asset.slot_id = "legacy"
        asset.brief_revision = 1
        asset.brief_sha256 = hash_file(run / relative)
        state = store.load(run_id)
        slot = VisualSlot(
            slot_id="legacy",
            role=asset.role or "visual",
            objective=brief.objective,
            artifact_path=f"runs/{run_id}/final.md",
            artifact_revision=state.revision,
            artifact_sha256=hash_file(run / "final.md"),
            brief_revision=1,
            brief_sha256=asset.brief_sha256,
            selected_asset_id=asset.asset_id,
            published_path=manifest.published_path,
        )
        if (
            asset.status in {VisualApprovalStatus.APPROVED, VisualApprovalStatus.PUBLISHED}
            and asset.validation
            and asset.validation.passed
        ):
            slot.approval_sha256 = approval_hash(slot, asset)
        if state.published_media:
            for media in state.published_media:
                if media.asset_id == asset.asset_id:
                    media.slot_id = "legacy"
            store.save_state(state)
        manifest.slots = [slot]
        manifest.selected_asset_id = None
        manifest.schema_version = "1.1"
        store.write_artifact(run_id, "visuals/manifest.json", manifest)
        from .visual_projection import project_visual_manifest

        project_visual_manifest(root, run_id)
        return manifest
