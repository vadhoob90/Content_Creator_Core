"""Provide draft bundles and visual slot review through coordinator queries."""

from pathlib import Path
from typing import Any

from .coordinator_models import operation
from .draft_bundles.service import DraftBundleWorkflow
from .storage import RunStore, StorageError
from .visual_contracts import VisualManifest
from .visual_slots import approval_hash, slot_for


def draft_operations() -> list[dict[str, Any]]:
    """Return coordinator-discoverable bundle and placement operations.

    Draft export remains separate from publication. Author approval is required
    for media approval and replacement but not for creating review candidates.

    Returns:
        list[dict[str, Any]]: Explicit commands with mutation and approval boundaries.
    """
    return [
        operation(
            "visual.render-slot",
            ["visual", "render", "<run-id>", "--slot", "<slot-id>"],
            mutates=True,
        ),
        operation("visual.select", ["visual", "select", "<run-id>", "<asset-id>"], mutates=True),
        operation(
            "visual.critique",
            ["visual", "critique", "<run-id>", "<asset-id>", "<critique.json>"],
            mutates=True,
        ),
        operation(
            "visual.replace",
            ["visual", "replace", "<run-id>", "<asset-id>"],
            mutates=True,
            approval=True,
        ),
        operation(
            "bundle.create", ["bundle", "create", "<bundle>", "--title", "<title>"], mutates=True
        ),
        operation("bundle.add", ["bundle", "add", "<bundle>", "<name>", "<run-id>"], mutates=True),
        operation("bundle.update", ["bundle", "update", "<bundle>", "<name>"], mutates=True),
        operation("bundle.remove", ["bundle", "remove", "<bundle>", "<name>"], mutates=True),
        operation("bundle.review", ["bundle", "review", "<bundle>"]),
        operation(
            "bundle.preview", ["bundle", "export", "<bundle>", "<draft-destination>", "--preview"]
        ),
        operation(
            "bundle.export", ["bundle", "export", "<bundle>", "<draft-destination>"], mutates=True
        ),
        operation(
            "draft.export", ["export-draft", "<run-id>", "<draft-destination>"], mutates=True
        ),
        operation(
            "visual.slot-brief", ["visual", "brief", "<run-id>", "<slot-brief.json>"], mutates=True
        ),
        operation(
            "visual.import", ["visual", "import", "<run-id>", "<import-request.json>"], mutates=True
        ),
        operation("visual.migrate-slots", ["visual", "migrate-slots", "<run-id>"], mutates=True),
        operation(
            "visual.approve",
            ["visual", "approve", "<run-id>", "<asset-id>"],
            mutates=True,
            approval=True,
        ),
    ]


def bundle_summaries(root: Path, run_id: str | None = None) -> list[dict[str, Any]]:
    """Return current bundle review evidence without changing membership.

    Args:
        root (Path): Workspace root.
        run_id (str | None): Optional membership filter. Defaults to ``None``.

    Returns:
        list[dict[str, Any]]: Bundle summaries, including actionable invalid metadata findings.
    """
    workflow = DraftBundleWorkflow(root)
    summaries = []
    for path in sorted((root / "draft-bundles").glob("*.json")):
        try:
            review = workflow.review(path.stem)
            if run_id and not any(m.member.run_id == run_id for m in review.members):
                continue
            summaries.append(review.model_dump(mode="json"))
        except StorageError as exc:
            summaries.append({"bundle_id": path.stem, "stale": True, "error": str(exc)})
    return summaries


def slot_summary(root: Path, run_id: str) -> list[dict[str, Any]]:
    """Return independently actionable visual placement review states.

    Args:
        root (Path): Workspace root.
        run_id (str): Reviewed run identifier.

    Returns:
        list[dict[str, Any]]: Slot selection, approval, and stale ownership summaries.
    """
    from .visual_slots import verify_slot

    path = root / "runs" / run_id / "visuals/manifest.json"
    if not path.exists():
        return []
    try:
        manifest = VisualManifest.model_validate_json(path.read_bytes())
    except ValueError as exc:
        return [{"error": str(exc), "requires_review": True}]
    result = []
    for slot in manifest.slots:
        asset = next((a for a in manifest.assets if a.asset_id == slot.selected_asset_id), None)
        summary = {
            "slot_id": slot.slot_id,
            "selected_asset_id": slot.selected_asset_id,
            "requires_review": True,
            "brief_revision": slot.brief_revision,
        }
        if asset:
            try:
                verify_slot(RunStore(root), slot_for(manifest, slot.slot_id), asset)
                summary["requires_review"] = (
                    slot.approval_sha256 != approval_hash(slot, asset)
                    or asset.status.value not in {"approved", "published"}
                    or not asset.validation
                    or not asset.validation.passed
                )
            except (RuntimeError, OSError, ValueError) as exc:
                summary["error"] = str(exc)
        result.append(summary)
    return result
