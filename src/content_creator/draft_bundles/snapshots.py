"""Read exact run artifacts and review evidence for draft bundle membership."""

import hashlib
import json
from pathlib import Path

from ..domain import RunState, RunStatus
from ..draft_integrity import DraftIntegrity
from ..packs import PackRegistry
from ..storage import RunStore, StorageError
from ..visual_contracts import VisualAsset, VisualError, VisualManifest
from ..visual_slots import approval_hash, selected_slots, slot_for
from .models import BundleMember, BundleVisual
from .paths import confined, identifier


def byte_hash(content: bytes) -> str:
    """Hash exact artifact bytes using the shared prefixed digest convention.

    Args:
        content (bytes): Artifact bytes.

    Returns:
        str: Prefixed SHA-256 digest.
    """
    return "sha256:" + hashlib.sha256(content).hexdigest()


def read_member(root: Path, name: str, run_id: str) -> BundleMember:
    """Record exact text, selected media, and independent run review evidence.

    Bundles preserve each run identity and exact selected evidence. Pending
    approval is recorded, while bytes conflicting with provenance are rejected.

    Args:
        root (Path): Workspace root.
        name (str): Member's portable output name.
        run_id (str): Existing reviewed run identifier.

    Returns:
        BundleMember: Complete deterministic snapshot without mutating the run.

    Raises:
        StorageError: If the run or any governed artifact is missing or inconsistent.
    """
    name = identifier(name)
    try:
        run = confined(root, f"runs/{run_id}")
        state = RunState.model_validate_json(
            confined(root, f"runs/{run_id}/state.json").read_bytes()
        )
        if state.id != run_id or state.status not in {
            RunStatus.READY,
            RunStatus.NEEDS_AUTHOR,
            RunStatus.PUBLISHED,
        }:
            raise StorageError("Bundle members must be reviewed runs with matching identities")
        expected = f"runs/{run_id}/final.md"
        if state.final_draft_path != expected:
            raise StorageError("Bundle member must own its canonical final artifact")
        final = confined(root, expected).read_bytes()
        hashes = _evidence(root, run_id, state.revision)
        _verify_draft(root, run_id, byte_hash(final), hashes)
        context = (
            json.loads((run / "resolved-context.json").read_bytes())
            if "resolved-context.json" in hashes
            else {}
        )
        validation = (
            json.loads((run / f"validation-{state.revision:02d}.json").read_bytes())
            if f"validation-{state.revision:02d}.json" in hashes
            else None
        )
        return BundleMember(
            name=name,
            run_id=run_id,
            revision=state.revision,
            artifact_path=expected,
            sha256=byte_hash(final),
            content_session_id=state.work_order.content_session_id,
            parent_run_id=state.work_order.parent_run_id,
            content_pack=state.work_order.content_pack,
            content_pack_version=context.get("content_pack", {}).get("version"),
            voice_id=state.work_order.voice_id,
            voice_version=state.work_order.voice_version,
            run_status=state.status.value,
            claim_review_required=state.claim_review_required,
            validation_status=(
                "unavailable"
                if validation is None
                else "failed"
                if validation.get("errors")
                else "passed"
            ),
            publication_destinations=_publication_destinations(root, state, context),
            evidence_hashes=hashes,
            visuals=_selected_visuals(root, run_id),
        )
    except (OSError, ValueError) as exc:
        raise StorageError(
            f"Cannot pin bundle member {name}: invalid or missing run evidence"
        ) from exc


def _evidence(root: Path, run_id: str, revision: int) -> dict[str, str]:
    """Hash available review evidence without copying its private contents.

    Args:
        root (Path): Workspace root.
        run_id (str): Reviewed run identifier.
        revision (int): Exact run revision.

    Returns:
        dict[str, str]: Run-relative evidence paths and digests.
    """
    names = [
        "resolved-context.json",
        "context-composition.json",
        "draft-integrity.json",
        "research.json",
        "claim-provenance.json",
        f"validation-{revision:02d}.json",
        f"claim-review-{revision:02d}.json",
        f"quality-{revision:02d}.json",
    ]
    result = {}
    for name in names:
        path = confined(root, f"runs/{run_id}/{name}")
        if path.is_file():
            result[name] = byte_hash(path.read_bytes())
    return result


def _verify_draft(root: Path, run_id: str, digest: str, hashes: dict[str, str]) -> None:
    """Reject unadopted text, changed research, or interrupted author edits.

    Args:
        root (Path): Workspace root.
        run_id (str): Member run identifier.
        digest (str): Current final text hash.
        hashes (dict[str, str]): Current evidence digests.

    Returns:
        None: Any available binding agrees with the selected bytes.

    Raises:
        StorageError: If current bytes conflict with existing provenance.
    """
    run = confined(root, f"runs/{run_id}")
    if (run / "author-edit-transaction.json").exists():
        raise StorageError("Recover the interrupted author edit before bundling")
    if "draft-integrity.json" in hashes:
        binding = DraftIntegrity.model_validate_json((run / "draft-integrity.json").read_bytes())
        if binding.draft_sha256 != digest or binding.research_sha256 != hashes.get("research.json"):
            raise StorageError("Adopt changed draft/research bytes before bundling")
    else:
        manifest_path = confined(root, f"runs/{run_id}/production-manifest.json")
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_bytes())
            final_hashes = [
                a["content_hash"]
                for a in manifest.get("artifacts", [])
                if a["kind"] == "final-draft"
            ]
            if final_hashes and final_hashes != [digest]:
                raise StorageError("Adopt changed legacy draft bytes before bundling")


def _selected_visuals(root: Path, run_id: str) -> list[BundleVisual]:
    """Read every explicit selection without guessing additional placements.

    Args:
        root (Path): Workspace root.
        run_id (str): Reviewed run identifier.

    Returns:
        list[BundleVisual]: Selected governed asset, or no selected media.

    Raises:
        StorageError: If visual schema, identity, selection, or bytes are invalid.
    """
    relative = f"runs/{run_id}/visuals/manifest.json"
    path = confined(root, relative)
    if not path.is_file():
        return []
    manifest = VisualManifest.model_validate_json(path.read_bytes())
    if manifest.run_id != run_id:
        raise StorageError("Unsupported or mismatched visual manifest")
    if manifest.slots:
        try:
            selected = selected_slots(RunStore(root), manifest)
        except VisualError as exc:
            raise StorageError(str(exc)) from exc
    elif manifest.selected_asset_id:
        selected = [a for a in manifest.assets if a.asset_id == manifest.selected_asset_id]
        if len(selected) != 1:
            raise StorageError("Visual manifest has an ambiguous or missing selection")
    else:
        return []
    return [_visual_snapshot(root, manifest, asset) for asset in selected]


def _visual_snapshot(root: Path, manifest: VisualManifest, asset: VisualAsset) -> BundleVisual:
    """Record one exact selected asset and optional placement evidence.

    Args:
        root (Path): Workspace root.
        manifest (VisualManifest): Current visual collection.
        asset (VisualAsset): Selected governed candidate.

    Returns:
        BundleVisual: Exact source and placement snapshot.

    Raises:
        StorageError: If source bytes or supported format are invalid.
    """
    run_id = manifest.run_id
    relative = f"runs/{run_id}/visuals/manifest.json"
    slot = slot_for(manifest, asset.slot_id) if asset.slot_id else None
    source = f"runs/{run_id}/{asset.relative_path}"
    content = confined(root, source).read_bytes()
    digest = "sha256:" + asset.sha256
    if byte_hash(content) != digest:
        raise StorageError("Selected visual is missing or its hash changed")
    if asset.format.lower() not in {"svg", "png", "jpg", "jpeg", "webp"}:
        raise StorageError("Selected visual uses an unsupported export format")
    return BundleVisual(
        slot_id=asset.slot_id,
        anchor=slot.anchor if slot else None,
        order=slot.order if slot else 0,
        slot_sha256=byte_hash(slot.model_dump_json().encode()) if slot else None,
        asset_id=asset.asset_id,
        revision=asset.revision,
        parent_asset_id=asset.parent_asset_id,
        role=asset.role or "visual",
        source_path=source,
        sha256=digest,
        format=asset.format.lower(),
        width=asset.width,
        height=asset.height,
        alt_text=asset.alt_text,
        approval_state=(
            "review_required"
            if slot and slot.approval_sha256 != approval_hash(slot, asset)
            else asset.status.value
        ),
        validation_passed=asset.validation.passed if asset.validation else None,
        record_sha256=byte_hash(asset.model_dump_json().encode()),
        provenance_path=relative,
    )


def _publication_destinations(root: Path, state: RunState, context: dict) -> list[str]:
    """Return historical or configured publication destinations for export exclusion.

    Args:
        root (Path): Workspace root.
        state (RunState): Member run and its pack options.
        context (dict): Available resolved context.

    Returns:
        list[str]: Text and visual publication destinations.
    """
    pack = context.get("effective_pack")
    if not pack:
        pack = (
            PackRegistry(root)
            .resolve(state.work_order.content_pack, state.work_order.pack_options)
            .model_dump(mode="json")
        )
    return [p for p in [pack["destination"], pack.get("visuals", {}).get("destination")] if p]
