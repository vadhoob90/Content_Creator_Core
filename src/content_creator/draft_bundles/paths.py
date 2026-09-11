"""Validate workspace sources, metadata locations, and draft export destinations."""

from pathlib import Path

from pydantic import TypeAdapter

from ..packs import PackRegistry
from ..storage import StorageError
from .models import Identifier


def identifier(value: str) -> str:
    """Validate a portable bundle or member identifier.

    Args:
        value (str): Requested identifier.

    Returns:
        str: Validated lowercase slug.

    Raises:
        StorageError: If the identifier is invalid.
    """
    try:
        return TypeAdapter(Identifier).validate_python(value)
    except ValueError as exc:
        raise StorageError("Use a portable lowercase slug for the bundle/member name") from exc


def confined(root: Path, relative: str) -> Path:
    """Resolve a relative workspace path and reject symlink traversal.

    Args:
        root (Path): Allowed root directory.
        relative (str): Relative artifact or metadata path.

    Returns:
        Path: Confined path without symlink components.

    Raises:
        StorageError: If the path is absolute, escapes its root, or traverses a symlink.
    """
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative:
        raise StorageError("Artifact path must stay within its workspace root")
    destination = root / path
    if not destination.resolve().is_relative_to(root.resolve()):
        raise StorageError("Artifact path leaves its workspace root")
    current = destination
    while current != root:
        if current.is_symlink():
            raise StorageError("Artifact paths must not traverse symlinks")
        current = current.parent
    return destination


def export_destination(root: Path, value: str, excluded: tuple[str, ...] = ()) -> Path:
    """Require a new package directory below a workspace draft destination.

    Args:
        root (Path): Workspace root.
        value (str): Requested relative or workspace-contained absolute destination.
        excluded (tuple[str, ...]): Member publication destinations. Defaults to ``()``.

    Returns:
        Path: Safe draft package directory.

    Raises:
        StorageError: If the destination is outside draft areas or overlaps publication.
    """
    requested = Path(value)
    if requested.is_absolute():
        try:
            requested = requested.relative_to(root)
        except ValueError as exc:
            raise StorageError("Draft export destination leaves the workspace") from exc
    destination = confined(root, str(requested))
    parts = requested.parts
    root_draft = len(parts) >= 2 and parts[0] == "drafts"
    pack_draft = len(parts) >= 4 and parts[0] == "content" and parts[2] == "drafts"
    if not (root_draft or pack_draft) or "published" in parts:
        raise StorageError("Export to drafts/<package> or content/<pack>/drafts/<package>")
    packs = PackRegistry(root)
    publication_paths = list(excluded)
    for pack in packs.list():
        resolved = packs.resolve(pack.id)
        publication_paths.append(resolved.destination)
        if resolved.visuals.destination:
            publication_paths.append(resolved.visuals.destination)
    for path in publication_paths:
        published = (root / path).resolve()
        if destination.is_relative_to(published) or published.is_relative_to(destination):
            raise StorageError("Draft export must not overlap a publication destination")
    return destination
