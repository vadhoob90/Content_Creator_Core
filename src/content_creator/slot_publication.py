"""Publish complete visual collections with immutable media and text snapshots."""

import os
import posixpath
from pathlib import Path
from typing import Any

from .domain import RunState
from .draft_bundles.markdown import rewrite_markdown
from .storage import RunStore
from .visual_contracts import VisualAsset, VisualManifest, VisualPackProfile
from .visual_placement import place_visuals
from .visual_slots import slot_for


def publication_text(
    root: Path,
    state: RunState,
    target: Path,
    draft: str,
    assets: list[VisualAsset],
    destinations: list[Path],
) -> str:
    """Map selected placements into a portable published Markdown snapshot.

    Args:
        root (Path): Workspace root.
        state (RunState): Reviewed source run.
        target (Path): New published Markdown destination.
        draft (str): Reviewed source text.
        assets (list[VisualAsset]): Complete selected collection.
        destinations (list[Path]): Corresponding immutable publication paths.

    Returns:
        str: Text with validated relative links and explicit placements.
    """
    source = f"runs/{state.id}/final.md"
    manifest = VisualManifest.model_validate_json(
        (root / f"runs/{state.id}/visuals/manifest.json").read_bytes()
    )
    placements = []
    mapping = {source: target.name}
    alt = {}
    for asset, destination in zip(assets, destinations, strict=True):
        path = f"runs/{state.id}/{asset.relative_path}"
        mapping[path] = posixpath.relpath(str(destination), str(target.parent))
        alt[path] = asset.alt_text
        if asset.slot_id:
            placements.append(
                {
                    "source_path": path,
                    "alt_text": asset.alt_text,
                    "anchor": slot_for(manifest, asset.slot_id).anchor,
                }
            )
    return rewrite_markdown(place_visuals(draft, source, placements), source, mapping, alt)


def publish_collection(
    publisher: Any,
    state: RunState,
    target: Path,
    draft: str,
    profile: VisualPackProfile,
    assets: list[VisualAsset],
    gate: Any,
) -> Path:
    """Stage and publish all selected placements before issuing one complete receipt.

    Text and media are staged together. Exclusive destination creation prevents
    overwrites, and failures restore the manifest and in-memory publication state.

    Args:
        publisher (Any): Composed package publisher.
        state (RunState): Run at the publication boundary.
        target (Path): New text destination.
        draft (str): Reviewed source text.
        profile (VisualPackProfile): Pack publication policy.
        assets (list[VisualAsset]): Complete approved media collection.
        gate (Any): Publication gate evidence.

    Returns:
        Path: Canonical receipt for the complete package.
    """
    destinations = [publisher.visuals.publication_target(state.id, a, profile) for a in assets]
    for destination in [target, *destinations]:
        publisher._ensure_available(destination, None)
    text = (
        publication_text(publisher.root, state, target, draft, assets, destinations)
        if any(a.slot_id for a in assets)
        else draft
    )
    contents = [(target, (text.rstrip() + "\n").encode())]
    contents.extend(
        (d, publisher._visual_source(state.id, a).read_bytes())
        for a, d in zip(assets, destinations, strict=True)
    )
    receipt = publisher.publications.receipt_path(str(target.relative_to(publisher.root)))
    manifest_path = publisher.root / f"runs/{state.id}/visuals/manifest.json"
    before_manifest = manifest_path.read_bytes() if manifest_path.exists() else None
    before_state = (state.published_path, state.published_visual_path, list(state.published_media))
    staged = []
    committed = []
    try:
        for path, content in contents:
            staged.append(publisher._stage(path, content))
        for temporary, destination in staged:
            os.link(temporary, destination)
            committed.append(destination)
        state.published_path = str(target.relative_to(publisher.root))
        state.published_media = [
            publisher._media(state.id, a, d) for a, d in zip(assets, destinations, strict=True)
        ]
        state.published_visual_path = (
            state.published_media[0].published_path if state.published_media else None
        )
        publisher.publications.issue(
            state,
            target,
            gate.perspective_evaluation,
            gate.evaluation_artifact_hash,
            gate.semantic_review,
        )
        for asset, destination in zip(assets, destinations, strict=True):
            publisher.visuals.mark_published(state.id, asset.asset_id, destination)
        return receipt
    except Exception:
        if target in committed:
            receipt.unlink(missing_ok=True)
        for path in reversed(committed):
            path.unlink(missing_ok=True)
        if before_manifest is not None:
            RunStore.atomic_bytes(manifest_path, before_manifest)
        state.published_path, state.published_visual_path, state.published_media = before_state
        raise
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)


def replace_slot(
    publisher: Any, state: RunState, asset: VisualAsset, profile: VisualPackProfile
) -> Path:
    """Create an immutable text snapshot when replacing one published placement.

    Unaffected media and the previous text/receipt remain intact. The replacement
    receipt links to its predecessor while the run points to the new package.

    Args:
        publisher (Any): Composed package publisher.
        state (RunState): Published run whose collection is being revised.
        asset (VisualAsset): Selected approved slot replacement.
        profile (VisualPackProfile): Pack publication policy.

    Returns:
        Path: New package receipt path.

    Raises:
        ValueError: If the slot is not already in the published collection.
    """
    from .publication_receipt_models import PublicationReceipt
    from .versioned_artifacts import hash_file

    previous_text = publisher.root / str(state.published_path)
    previous_receipt = publisher.publications.receipt_path(str(state.published_path))
    previous = PublicationReceipt.model_validate_json(previous_receipt.read_bytes())
    old = next((m for m in state.published_media if m.slot_id == asset.slot_id), None)
    if old is None:
        raise ValueError("Replacement slot is absent from the published package")
    target = previous_text.with_name(f"{previous_text.stem}-media-{asset.asset_id}.md")
    media_target = publisher.visuals.publication_target(state.id, asset, profile)
    receipt = publisher.publications.receipt_path(str(target.relative_to(publisher.root)))
    for path in [target, media_target, receipt]:
        publisher._ensure_available(path, None)
    text = replacement_text(publisher.root, state, target, asset, media_target)
    manifest_path = publisher.root / f"runs/{state.id}/visuals/manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    before = (state.published_path, state.published_visual_path, list(state.published_media))
    staged = []
    committed = []
    try:
        staged.append(
            publisher._stage(media_target, publisher._visual_source(state.id, asset).read_bytes())
        )
        staged.append(publisher._stage(target, (text.rstrip() + "\n").encode()))
        for temporary, destination in staged:
            os.link(temporary, destination)
            committed.append(destination)
        replacement = publisher._media(state.id, asset, media_target)
        state.published_media = [
            replacement if m.slot_id == asset.slot_id else m for m in state.published_media
        ]
        state.published_visual_path = state.published_media[0].published_path
        state.published_path = str(target.relative_to(publisher.root))
        updated = previous.model_copy(
            update={
                "artifact_path": state.published_path,
                "artifact_hash": hash_file(target),
                "revision": previous.revision + 1,
                "supersedes_receipt_hash": hash_file(previous_receipt),
                "artifacts": publisher.publications.packages.artifacts(state, target),
            }
        )
        RunStore.atomic_bytes(receipt, (updated.model_dump_json(indent=2) + "\n").encode())
        publisher.visuals.mark_published(state.id, asset.asset_id, media_target)
        return receipt
    except Exception:
        if target in committed:
            receipt.unlink(missing_ok=True)
        for path in reversed(committed):
            path.unlink(missing_ok=True)
        RunStore.atomic_bytes(manifest_path, manifest_bytes)
        state.published_path, state.published_visual_path, state.published_media = before
        raise
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)


def replacement_text(
    root: Path, state: RunState, target: Path, asset: VisualAsset, media_target: Path
) -> str:
    """Update one placement in an immutable copy of the previous published text.

    Args:
        root (Path): Workspace root.
        state (RunState): Current published package state.
        target (Path): New immutable text destination.
        asset (VisualAsset): Approved replacement candidate.
        media_target (Path): New immutable media path.

    Returns:
        str: Previous publication with only the selected placement's path and alt text updated.
    """
    source = str(state.published_path)
    mapping = {source: target.name}
    alt = {}
    for media in state.published_media:
        changed = media.slot_id == asset.slot_id
        destination = media_target if changed else root / media.published_path
        mapping[media.published_path] = posixpath.relpath(str(destination), str(target.parent))
        alt[media.published_path] = asset.alt_text if changed else media.alt_text
    return rewrite_markdown((root / source).read_text(), source, mapping, alt)


def preflight_collection(
    publisher: Any,
    state: RunState,
    target: Path,
    draft: str,
    profile: VisualPackProfile,
    assets: list[VisualAsset],
) -> None:
    """Validate complete publication destinations and placements before learning extraction.

    Args:
        publisher (Any): Composed package publisher.
        state (RunState): Reviewed run.
        target (Path): New published Markdown destination.
        draft (str): Exact reviewed source text.
        profile (VisualPackProfile): Pack publication policy.
        assets (list[VisualAsset]): Complete selected collection.

    Returns:
        None: All destinations and explicit placement references are valid.
    """
    destinations = [
        publisher.visuals.publication_target(state.id, asset, profile) for asset in assets
    ]
    for destination in destinations:
        publisher._ensure_available(destination, None)
    if any(asset.slot_id for asset in assets):
        publication_text(publisher.root, state, target, draft, assets, destinations)
