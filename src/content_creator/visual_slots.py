"""Manage independently pinned visual placements and approval evidence."""

from pathlib import Path

from .domain import RunStatus
from .storage import RunStore
from .versioned_artifacts import hash_file, hash_json
from .visual_contracts import (
    VisualApprovalStatus,
    VisualAsset,
    VisualBrief,
    VisualError,
    VisualManifest,
    VisualPackProfile,
    VisualSlot,
)


def slot_for(manifest: VisualManifest, slot_id: str) -> VisualSlot:
    """Return one explicitly named placement.

    Args:
        manifest (VisualManifest): Current governed visual collection.
        slot_id (str): Stable placement identifier.

    Returns:
        VisualSlot: Matching placement.

    Raises:
        VisualError: If the placement is unknown.
    """
    for slot in manifest.slots:
        if slot.slot_id == slot_id:
            return slot
    raise VisualError(f"Unknown visual slot: {slot_id}")


def brief_path(slot_id: str, revision: int) -> str:
    """Return the immutable brief location for one placement revision.

    Args:
        slot_id (str): Validated placement identifier.
        revision (int): Brief revision number.

    Returns:
        str: Run-relative brief path.
    """
    return f"visuals/slots/{slot_id}/r{revision:04d}/brief.json"


def prepare_slot(store: RunStore, brief: VisualBrief, profile: VisualPackProfile) -> VisualBrief:
    """Persist a new slot brief without changing any other placement.

    A new brief revision clears only this slot selection and approval. Its exact
    source text and role remain pinned for later validation and publication.

    Args:
        store (RunStore): Workspace artifact store.
        brief (VisualBrief): Explicit slot specification and purpose.
        profile (VisualPackProfile): Selected pack visual requirements.

    Returns:
        VisualBrief: Persisted brief with allocated revision.

    Raises:
        VisualError: If placement, ownership, or requested role is invalid.
    """
    state = store.load(brief.run_id)
    if not brief.slot_id or state.status not in {
        RunStatus.READY,
        RunStatus.NEEDS_AUTHOR,
        RunStatus.PUBLISHED,
    }:
        raise VisualError("Visual slots require reviewed content and an explicit slot ID")
    if not profile.supported or not brief.objective.strip() or not brief.alt_text.strip():
        raise VisualError("Slots require a supported pack, editorial purpose, and alt text")
    role = profile.role(brief.role)
    if set(brief.aspect_ratios) != {role.aspect_ratio} or not set(brief.output_formats) <= set(
        role.formats
    ):
        raise VisualError("Slot outputs must match the selected pack role")
    brief.safe_area_profiles = role.safe_area_profiles
    brief.crop_profiles = role.crop_profiles
    run = store.run_dir(brief.run_id)
    path = run / "visuals/manifest.json"
    manifest = (
        VisualManifest.model_validate_json(path.read_bytes())
        if path.exists()
        else VisualManifest(run_id=brief.run_id)
    )
    if manifest.selected_asset_id:
        raise VisualError(
            "Migrate the legacy selection with visual migrate-slots before adding slots"
        )
    existing = next((s for s in manifest.slots if s.slot_id == brief.slot_id), None)
    brief.brief_revision = existing.brief_revision + 1 if existing else 1
    relative = brief_path(brief.slot_id, brief.brief_revision)
    if (run / relative).exists():
        raise VisualError("An interrupted slot write exists; inspect it before retrying")
    store.write_artifact(brief.run_id, relative, brief)
    slot = VisualSlot(
        slot_id=brief.slot_id,
        role=brief.role or "visual",
        objective=brief.objective,
        order=brief.display_order,
        anchor=brief.insertion_anchor,
        artifact_path=f"runs/{brief.run_id}/final.md",
        artifact_revision=state.revision,
        artifact_sha256=hash_file(run / "final.md"),
        brief_revision=brief.brief_revision,
        brief_sha256=hash_file(run / relative),
        published_path=existing.published_path if existing else None,
    )
    manifest.slots = (
        [slot if s.slot_id == slot.slot_id else s for s in manifest.slots]
        if existing
        else [*manifest.slots, slot]
    )
    manifest.schema_version = "1.1"
    store.write_artifact(brief.run_id, "visuals/manifest.json", manifest)
    return brief


def approval_hash(slot: VisualSlot, asset: VisualAsset) -> str:
    """Bind approval to exact media, accessibility text, brief, and text ownership.

    Args:
        slot (VisualSlot): Placement whose editorial context is reviewed.
        asset (VisualAsset): Exact selected candidate.

    Returns:
        str: Stable approval digest.
    """
    return hash_json(
        {
            "slot": slot.model_dump(exclude={"approval_sha256", "published_path"}),
            "asset": asset.model_dump(mode="json", exclude={"status", "validation", "critique"}),
        }
    )


def verify_slot(store: RunStore, slot: VisualSlot, asset: VisualAsset) -> None:
    """Validate current placement ownership and immutable source bindings.

    Args:
        store (RunStore): Workspace artifact store.
        slot (VisualSlot): Selected placement.
        asset (VisualAsset): Selected candidate.

    Returns:
        None: Placement and source evidence agree.

    Raises:
        VisualError: If text, brief, asset identity, or source bytes changed.
    """
    run_id = Path(slot.artifact_path).parts[1]
    state = store.load(run_id)
    run = store.run_dir(run_id)
    if (
        state.revision != slot.artifact_revision
        or hash_file(run / "final.md") != slot.artifact_sha256
    ):
        raise VisualError(f"Visual slot {slot.slot_id} has stale text ownership; refresh its brief")
    if asset.slot_id != slot.slot_id or asset.brief_revision != slot.brief_revision:
        raise VisualError("Candidate belongs to a different slot or brief revision")
    if (
        hash_file(run / brief_path(slot.slot_id, slot.brief_revision)) != slot.brief_sha256
        or asset.brief_sha256 != slot.brief_sha256
    ):
        raise VisualError("Visual brief evidence changed")
    source = (run / asset.relative_path).resolve()
    if (
        not source.is_relative_to(run.resolve())
        or not source.is_file()
        or hash_file(source) != "sha256:" + asset.sha256
    ):
        raise VisualError("Selected visual asset is missing or its hash has changed")


def decide_slot(
    store: RunStore, manifest: VisualManifest, asset: VisualAsset, approve: bool
) -> VisualAsset:
    """Record selection or approval for exactly one placement.

    Args:
        store (RunStore): Workspace artifact store.
        manifest (VisualManifest): Complete visual collection.
        asset (VisualAsset): Critiqued candidate selected by the author.
        approve (bool): Whether this is an explicit approval decision.

    Returns:
        VisualAsset: Updated candidate.

    Raises:
        VisualError: If validation, critique, selection, or immutable evidence is missing.
    """
    slot = slot_for(manifest, str(asset.slot_id))
    verify_slot(store, slot, asset)
    if not asset.validation or not asset.validation.passed or asset.critique is None:
        raise VisualError("Slot selection and approval require validation and critique")
    if approve and slot.selected_asset_id != asset.asset_id:
        raise VisualError("Author approval requires this slot's selected asset")
    if (
        not approve
        and slot.selected_asset_id == asset.asset_id
        and asset.status
        in {
            VisualApprovalStatus.SELECTED,
            VisualApprovalStatus.APPROVED,
            VisualApprovalStatus.PUBLISHED,
        }
    ):
        return asset
    slot.selected_asset_id = asset.asset_id
    asset.status = VisualApprovalStatus.APPROVED if approve else VisualApprovalStatus.SELECTED
    slot.approval_sha256 = approval_hash(slot, asset) if approve else None
    directory = f"visuals/slots/{slot.slot_id}/r{slot.brief_revision:04d}/decisions"
    number = len(list((store.run_dir(manifest.run_id) / directory).glob("*.json"))) + 1
    store.write_artifact(
        manifest.run_id,
        f"{directory}/{number:04d}.json",
        {
            "slot": slot.model_dump(mode="json"),
            "asset": asset.model_dump(mode="json"),
            "decision": "approved" if approve else "selected",
        },
    )
    store.write_artifact(manifest.run_id, "visuals/manifest.json", manifest)
    return asset


def selected_slots(
    store: RunStore, manifest: VisualManifest, approved: bool = False
) -> list[VisualAsset]:
    """Return every selected placement in stable display order.

    Args:
        store (RunStore): Workspace artifact store.
        manifest (VisualManifest): Complete current collection.
        approved (bool): Require current author approval. Defaults to ``False``.

    Returns:
        list[VisualAsset]: Ordered selected candidates.

    Raises:
        VisualError: If a slot lacks a selection or has stale approval.
    """
    result = []
    for slot in sorted(manifest.slots, key=lambda s: (s.order, s.slot_id)):
        asset = next((a for a in manifest.assets if a.asset_id == slot.selected_asset_id), None)
        if asset is None:
            raise VisualError(f"Visual slot {slot.slot_id} has no selected asset")
        verify_slot(store, slot, asset)
        if approved and (
            slot.approval_sha256 != approval_hash(slot, asset)
            or asset.status not in {VisualApprovalStatus.APPROVED, VisualApprovalStatus.PUBLISHED}
            or not asset.validation
            or not asset.validation.passed
        ):
            raise VisualError(f"Visual slot {slot.slot_id} requires current author approval")
        result.append(asset)
    return result
