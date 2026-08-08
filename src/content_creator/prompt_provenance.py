"""Record prompt source provenance without changing composed prompt text."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .context_composition import ContextLayer, LayerOwner
from .versioned_artifacts import hash_file


@dataclass(frozen=True)
class PromptComposition:
    """Return prompt text together with its ordered source provenance."""

    prompt: str
    layers: list[ContextLayer]


class PromptProvenance:
    """Record loaded and skipped prompt sources using stable locators."""

    def __init__(self, root: Path, core: Path):
        """Initialize prompt provenance path boundaries.

        Args:
            root (Path): Workspace root directory.
            core (Path): Installed Core resource directory.

        Returns:
            None: Resolved boundaries are stored in place.
        """
        self.root = root.resolve()
        self.core = core.resolve()

    def load(
        self,
        layers: list[ContextLayer],
        category: str,
        label: str,
        path: Path,
        owner: Optional[LayerOwner] = None,
        version: Optional[str] = None,
        record_ids: Optional[list[str]] = None,
    ) -> str:
        """Read one actual prompt source and record its provenance.

        Args:
            layers (list[ContextLayer]): Ordered provenance collection.
            category (str): Stable instruction-layer category.
            label (str): Human-readable source label.
            path (Path): Exact file read into the prompt.
            owner (Optional[LayerOwner]): Explicit owner. Defaults to ``None``.
            version (Optional[str]): Resolved artifact version. Defaults to ``None``.
            record_ids (Optional[list[str]]): Selected record identifiers. Defaults to
                ``None``.

        Returns:
            str: Exact stripped source text used by prompt composition.
        """
        text = path.read_text(encoding="utf-8").strip()
        self.record_loaded(layers, category, label, path, owner, version, record_ids)
        return text

    def record_loaded(
        self,
        layers: list[ContextLayer],
        category: str,
        label: str,
        path: Path,
        owner: Optional[LayerOwner] = None,
        version: Optional[str] = None,
        record_ids: Optional[list[str]] = None,
    ) -> None:
        """Record one exact file that contributed instructions.

        Args:
            layers (list[ContextLayer]): Ordered provenance collection.
            category (str): Stable instruction-layer category.
            label (str): Human-readable source label.
            path (Path): Exact loaded file.
            owner (Optional[LayerOwner]): Explicit owner. Defaults to ``None``.
            version (Optional[str]): Resolved artifact version. Defaults to ``None``.
            record_ids (Optional[list[str]]): Selected record identifiers. Defaults to
                ``None``.

        Returns:
            None: The provenance collection is updated in place.
        """
        layers.append(
            ContextLayer(
                order=len(layers) + 1,
                category=category,
                label=label,
                owner=owner or self.owner(path),
                source=self.source(path),
                status="loaded",
                version=version,
                content_hash=hash_file(path),
                record_ids=record_ids or [],
            )
        )

    @staticmethod
    def skip(
        layers: list[ContextLayer],
        category: str,
        label: str,
        source: str,
        reason: str,
        owner: LayerOwner = "workspace",
        content_hash: Optional[str] = None,
    ) -> None:
        """Record why an eligible conceptual layer did not enter the prompt.

        Args:
            layers (list[ContextLayer]): Ordered provenance collection.
            category (str): Stable instruction-layer category.
            label (str): Human-readable source label.
            source (str): Logical source locator.
            reason (str): Deterministic skip explanation.
            owner (LayerOwner): Source owner. Defaults to ``workspace``.
            content_hash (Optional[str]): Existing source hash. Defaults to ``None``.

        Returns:
            None: The provenance collection is updated in place.
        """
        layers.append(
            ContextLayer(
                order=len(layers) + 1,
                category=category,
                label=label,
                owner=owner,
                source=source,
                status="skipped",
                reason=reason,
                content_hash=content_hash,
            )
        )

    def append_learning_scope(
        self,
        parts: list[str],
        layers: list[ContextLayer],
        path: Path,
        records: list[dict[str, Any]],
        scope: str,
    ) -> None:
        """Append one role-matched learning scope and its source evidence.

        Args:
            parts (list[str]): Mutable prompt-part collection.
            layers (list[ContextLayer]): Ordered provenance collection.
            path (Path): Learning-memory source file.
            records (list[dict[str, Any]]): Active role-matched learning records.
            scope (str): Repository or voice scope label.

        Returns:
            None: Prompt and provenance collections are updated in place.
        """
        category = f"{scope}-learnings"
        label = f"Active {scope} learnings"
        owner: LayerOwner = "workspace" if scope == "repository" else "voice"
        if not records:
            self.skip(
                layers,
                category,
                label,
                self.source(path),
                (
                    "learning-memory-is-missing"
                    if not path.is_file()
                    else "no-active-role-matched-learning"
                ),
                owner=owner,
                content_hash=hash_file(path) if path.is_file() else None,
            )
            return
        self.record_loaded(
            layers,
            category,
            label,
            path,
            owner=owner,
            record_ids=[str(record.get("id", "unknown")) for record in records],
        )
        principles = [f"- {record['principle']}" for record in records]
        parts.append(f"## {label}\n\n" + "\n".join(principles))

    def source(self, path: Path) -> str:
        """Return a stable logical locator without installation-specific paths.

        Args:
            path (Path): Workspace or packaged Core source path.

        Returns:
            str: Repository-relative or ``core:``-prefixed source locator.
        """
        try:
            return str(path.resolve().relative_to(self.root))
        except ValueError:
            try:
                relative = path.resolve().relative_to(self.core)
            except ValueError:
                return f"external:{path.name}"
            return f"core:{relative}"

    def owner(self, path: Path) -> LayerOwner:
        """Return whether a resolved file came from Core or the workspace.

        Args:
            path (Path): Resolved prompt source path.

        Returns:
            LayerOwner: ``workspace`` for overrides, otherwise ``core``.
        """
        try:
            path.resolve().relative_to(self.root)
        except ValueError:
            return "core"
        return "workspace"
