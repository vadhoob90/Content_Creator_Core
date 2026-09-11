"""Stage and write complete draft review packages without publication effects."""

import json
import os
import shutil
import tempfile
from pathlib import Path

from ..storage import RunStore, StorageError, slugify
from ..versioned_artifacts import ActivationLock
from ..visual_placement import place_visuals
from .markdown import rewrite_markdown
from .models import DraftBundle, DraftExportManifest, ExportArtifact
from .paths import confined, export_destination
from .snapshots import byte_hash, read_member

MANIFEST = "package-manifest.json"


def export_package(
    root: Path,
    bundle: DraftBundle,
    destination: str,
    preview: bool = False,
    single_run: bool = False,
) -> DraftExportManifest:
    """Build and optionally persist a deterministic, non-publishing draft snapshot.

    Args:
        root (Path): Workspace root.
        bundle (DraftBundle): Exact source membership selected by the caller.
        destination (str): Workspace draft destination.
        preview (bool): Validate and return the manifest without writing. Defaults to ``False``.
        single_run (bool): Omit bundle identity for a standalone run. Defaults to ``False``.

    Returns:
        DraftExportManifest: Complete package mapping and source review states.

    """
    excluded = tuple(p for m in bundle.members for p in m.publication_destinations)
    target = export_destination(root, destination, excluded)
    _current(root, bundle)
    manifest, files = _materialize(root, bundle, single_run)
    files[MANIFEST] = (manifest.model_dump_json(indent=2) + "\n").encode("utf-8")
    if preview:
        if target.exists():
            _verify_existing(target, files)
        return manifest
    lock_id = byte_hash(str(target).encode()).removeprefix("sha256:")
    lock = confined(root, f"draft-bundles/.export-locks/{lock_id}.lock")
    with ActivationLock(lock, "Another export to this destination is in progress", StorageError):
        _current(root, bundle)
        if target.exists():
            _verify_existing(target, files)
            return manifest
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".draft-export-", dir=target.parent))
        try:
            for name, content in files.items():
                RunStore.atomic_bytes(confined(staging, name), content)
            _current(root, bundle)
            export_destination(root, destination, excluded)
            _expose(staging, target, files)
        finally:
            shutil.rmtree(staging)
    return manifest


def _current(root: Path, bundle: DraftBundle) -> None:
    """Reject stale or empty membership before exposing a draft package.

    Args:
        root (Path): Workspace root.
        bundle (DraftBundle): Selected pins.

    Returns:
        None: Every member and its selected evidence still matches.

    Raises:
        StorageError: If membership is empty or any source has changed.
    """
    if not bundle.members:
        raise StorageError("Cannot export an empty draft bundle")
    for member in bundle.members:
        if read_member(root, member.name, member.run_id) != member:
            raise StorageError(f"Bundle member {member.name} is stale; use bundle update")


def _materialize(
    root: Path, bundle: DraftBundle, single_run: bool
) -> tuple[DraftExportManifest, dict[str, bytes]]:
    """Build portable bytes and their deterministic source/export manifest.

    File names follow membership order and selected asset revisions. Markdown
    references are resolved against the full package before any output is exposed.

    Args:
        root (Path): Workspace root.
        bundle (DraftBundle): Verified source pins.
        single_run (bool): Whether membership is ephemeral for one run.

    Returns:
        tuple[DraftExportManifest, dict[str, bytes]]: Complete manifest and package files.

    Raises:
        StorageError: If an artifact no longer matches its pinned digest.
    """
    destinations = {m.artifact_path: f"{m.name}.md" for m in bundle.members}
    alt_texts = {}
    for member in bundle.members:
        for index, visual in enumerate(member.visuals, start=1):
            destinations[visual.source_path] = (
                f"assets/{member.name}-{index:02d}-{slugify(visual.role)}-r{visual.revision}.{visual.format}"
            )
            alt_texts[visual.source_path] = visual.alt_text
    files = {}
    artifacts = []
    for member in bundle.members:
        source = confined(root, member.artifact_path).read_bytes()
        if byte_hash(source) != member.sha256:
            raise StorageError("Draft artifact hash changed during export")
        markdown = rewrite_markdown(
            place_visuals(
                source.decode("utf-8"),
                member.artifact_path,
                [v.model_dump(mode="json") for v in member.visuals],
            ),
            member.artifact_path,
            destinations,
            alt_texts,
        )
        exported = markdown.encode("utf-8")
        target = destinations[member.artifact_path]
        files[target] = exported
        artifacts.append(
            ExportArtifact(
                member_name=member.name,
                run_id=member.run_id,
                run_revision=member.revision,
                kind="markdown",
                source_path=member.artifact_path,
                source_sha256=member.sha256,
                exported_path=target,
                exported_sha256=byte_hash(exported),
            )
        )
        for visual in member.visuals:
            content = confined(root, visual.source_path).read_bytes()
            if byte_hash(content) != visual.sha256:
                raise StorageError("Visual asset hash changed during export")
            target = destinations[visual.source_path]
            files[target] = content
            artifacts.append(
                ExportArtifact(
                    member_name=member.name,
                    run_id=member.run_id,
                    run_revision=member.revision,
                    kind="visual",
                    source_path=visual.source_path,
                    source_sha256=visual.sha256,
                    exported_path=target,
                    exported_sha256=byte_hash(content),
                    visual=visual,
                )
            )
    manifest = DraftExportManifest(
        bundle_id=None if single_run else bundle.bundle_id,
        bundle_revision=None if single_run else bundle.revision,
        source_sha256=byte_hash(
            json.dumps(bundle.model_dump(mode="json"), sort_keys=True).encode()
        ),
        members=bundle.members,
        artifacts=artifacts,
    )
    return manifest, files


def _verify_existing(target: Path, files: dict[str, bytes]) -> None:
    """Validate an identical retry only when the entire existing package matches.

    Args:
        target (Path): Existing destination directory.
        files (dict[str, bytes]): Exact intended package bytes.

    Returns:
        None: Existing package is identical, including its complete file inventory.

    Raises:
        StorageError: If the destination is incomplete, changed, or contains unrelated files.
    """
    if not target.is_dir():
        raise StorageError("Draft destination already exists and is not a package directory")
    paths = list(target.rglob("*"))
    if any(p.is_symlink() for p in paths):
        raise StorageError("Existing draft package contains a symlink")
    actual = {str(p.relative_to(target)) for p in paths if p.is_file()}
    expected_directories = {
        str(Path(name).parent) for name in files if Path(name).parent != Path(".")
    }
    actual_directories = {str(p.relative_to(target)) for p in paths if p.is_dir()}
    if actual != set(files) or actual_directories != expected_directories:
        raise StorageError(
            "Draft destination contains an incomplete or different package; "
            "choose a new destination"
        )
    if any(confined(target, name).read_bytes() != content for name, content in files.items()):
        raise StorageError("Draft destination contains modified content; refusing to overwrite")


def _expose(staging: Path, target: Path, files: dict[str, bytes]) -> None:
    """Write staged files without overwrites and install the manifest last.

    Exclusive directory creation and hard links avoid overwriting a destination
    created concurrently. A complete manifest is the package commit record.
    Ordinary failures compensate only files written by this operation; a process
    interruption leaves an incomplete destination that cannot be mistaken for a
    successful or idempotently reusable export.

    Args:
        staging (Path): Complete validated staging directory on the destination filesystem.
        target (Path): New draft package directory.
        files (dict[str, bytes]): Exact bytes owned by the operation.

    Returns:
        None: The complete package is exposed.
    """
    target.mkdir(exist_ok=False)
    created = []
    directories = []
    try:
        for name in [n for n in files if n != MANIFEST] + [MANIFEST]:
            destination = confined(target, name)
            if destination.parent != target and not destination.parent.exists():
                destination.parent.mkdir()
                directories.append(destination.parent)
            os.link(confined(staging, name), destination)
            created.append(name)
    except Exception:
        for name in reversed(created):
            path = target / name
            if path.is_file() and not path.is_symlink() and path.read_bytes() == files[name]:
                path.unlink()
        for directory in reversed(directories):
            if directory.exists() and not any(directory.iterdir()):
                directory.rmdir()
        if not any(target.iterdir()):
            target.rmdir()
        raise
