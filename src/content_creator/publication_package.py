"""Publish content and approved media as one recoverable local package."""

from __future__ import annotations

import mimetypes
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from .domain import PublishedMediaArtifact, RunState
from .publication_provenance import PublicationProvenance, PublicationProvenanceError
from .storage import StorageError
from .versioned_artifacts import hash_file
from .visual_contracts import VisualAsset, VisualError, VisualPackProfile
from .visuals import VisualWorkflow


class PublicationPackagePublisher:
    """Coordinate staged destination writes and compensating rollback."""

    def __init__(
        self,
        root: Path,
        visuals: VisualWorkflow,
        publications: PublicationProvenance,
    ):
        """Initialize package publication collaborators.

        Args:
            root (Path): Author workspace root.
            visuals (VisualWorkflow): Governed visual lifecycle service.
            publications (PublicationProvenance): Canonical receipt service.

        Returns:
            None: The publisher stores resolved collaborators in place.
        """
        self.root = root.resolve()
        self.visuals = visuals
        self.publications = publications

    def publish(
        self,
        state: RunState,
        target: Path,
        draft: str,
        profile: VisualPackProfile,
        visual_asset: Optional[VisualAsset],
        gate: Any,
    ) -> Path:
        """Publish text, optional media, and one canonical package receipt.

        Stage complete bytes before exposing destinations. If a later receipt or
        manifest step fails, remove every new destination and restore in-memory state.

        Args:
            state (RunState): Reviewed run crossing the publication boundary.
            target (Path): Canonical content publication destination.
            draft (str): Exact reviewed content bytes to publish.
            profile (VisualPackProfile): Resolved pack visual policy.
            visual_asset (Optional[VisualAsset]): Approved selected media, when present.
            gate (Any): Deterministic and semantic publication-gate evidence.

        Returns:
            Path: Canonical publication receipt written for the complete package.
        """
        visual_target = (
            self.visuals.publication_target(state.id, visual_asset, profile)
            if visual_asset is not None
            else None
        )
        self._ensure_available(target, visual_target)
        staged = [self._stage(target, (draft.rstrip() + "\n").encode("utf-8"))]
        if visual_asset is not None and visual_target is not None:
            source = self._visual_source(state.id, visual_asset)
            staged.append(self._stage(visual_target, source.read_bytes()))
        committed: list[Path] = []
        receipt_path = self.publications.receipt_path(str(target.relative_to(self.root)))
        prior = (state.published_path, state.published_visual_path, list(state.published_media))
        try:
            for temporary, destination in staged:
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(temporary, destination)
                committed.append(destination)
            state.published_path = str(target.relative_to(self.root))
            state.published_visual_path = (
                str(visual_target.relative_to(self.root)) if visual_target else None
            )
            state.published_media = (
                [self._media(state.id, visual_asset, visual_target)]
                if visual_asset is not None and visual_target is not None
                else []
            )
            self.publications.issue(
                state,
                target,
                gate.perspective_evaluation,
                gate.evaluation_artifact_hash,
                gate.semantic_review,
            )
            if visual_asset is not None and visual_target is not None:
                self.visuals.mark_published(state.id, visual_asset.asset_id, visual_target)
            return receipt_path
        except Exception:
            receipt_path.unlink(missing_ok=True)
            for path in reversed(committed):
                path.unlink(missing_ok=True)
            state.published_path, state.published_visual_path, state.published_media = prior
            raise
        finally:
            for temporary, _ in staged:
                temporary.unlink(missing_ok=True)

    def replace_visual(
        self,
        state: RunState,
        asset: VisualAsset,
        profile: VisualPackProfile,
    ) -> Path:
        """Publish replacement media while retaining text and receipt history.

        Publish the replacement under a new immutable filename, revise the canonical
        receipt, and retain both the predecessor receipt and superseded visual bytes.

        Args:
            state (RunState): Published run whose media is being replaced.
            asset (VisualAsset): Selected and author-approved replacement asset.
            profile (VisualPackProfile): Resolved pack visual policy.

        Returns:
            Path: Revised canonical publication receipt path.

        Raises:
            PublicationProvenanceError: If receipt history cannot be revised safely.
            VisualError: If the run or replacement source is not publishable.
        """
        if not state.published_path:
            raise VisualError("Visual replacement requires a published content artifact")
        target = self.visuals.publication_target(state.id, asset, profile)
        self._ensure_available(None, target)
        source = self._visual_source(state.id, asset)
        temporary, destination = self._stage(target, source.read_bytes())
        receipt_path = self.publications.receipt_path(state.published_path)
        receipt_bytes = receipt_path.read_text(encoding="utf-8")
        history_pattern = f"{Path(state.published_path).name}.receipt.r*-*.json"
        prior_history = set(receipt_path.parent.glob(history_pattern))
        prior_visual = state.published_visual_path
        prior_media = list(state.published_media)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temporary, destination)
            state.published_visual_path = str(destination.relative_to(self.root))
            state.published_media = [self._media(state.id, asset, destination)]
            try:
                self.publications.packages.replace(state)
            except (OSError, ValueError) as exc:
                raise PublicationProvenanceError(str(exc)) from exc
            self.visuals.mark_published(state.id, asset.asset_id, destination)
            return receipt_path
        except Exception:
            destination.unlink(missing_ok=True)
            state.published_visual_path = prior_visual
            state.published_media = prior_media
            if receipt_path.exists():
                from .storage import RunStore

                RunStore._atomic_text(receipt_path, receipt_bytes.rstrip())
            current_history = set(receipt_path.parent.glob(history_pattern))
            for path in current_history - prior_history:
                path.unlink(missing_ok=True)
            raise
        finally:
            temporary.unlink(missing_ok=True)

    def _visual_source(self, run_id: str, asset: VisualAsset) -> Path:
        """Resolve and verify the immutable selected visual source.

        Args:
            run_id (str): Run containing the visual asset lineage.
            asset (VisualAsset): Selected asset with its recorded hash and relative path.

        Returns:
            Path: Verified run-local visual source path.

        Raises:
            VisualError: If the source is missing or differs from its recorded hash.
        """
        source = self.root / "runs" / run_id / asset.relative_path
        if not source.is_file() or hash_file(source) != "sha256:" + asset.sha256:
            raise VisualError("Selected visual asset is missing or its hash has changed")
        return source

    def _media(
        self,
        run_id: str,
        asset: VisualAsset,
        target: Path,
    ) -> PublishedMediaArtifact:
        """Build persisted package metadata for one selected visual.

        Args:
            run_id (str): Run containing the selected visual source.
            asset (VisualAsset): Selected visual lifecycle record.
            target (Path): Published immutable visual destination.

        Returns:
            PublishedMediaArtifact: Complete state metadata for the package media.
        """
        source = self._visual_source(run_id, asset)
        return PublishedMediaArtifact(
            role=asset.role or "visual",
            source_path=str(source.relative_to(self.root)),
            published_path=str(target.relative_to(self.root)),
            sha256=hash_file(target),
            mime_type=self._mime_type(asset.format),
            width=asset.width,
            height=asset.height,
            alt_text=asset.alt_text,
            approval_state="approved",
            asset_id=asset.asset_id,
            parent_asset_id=asset.parent_asset_id,
            revision=asset.revision,
        )

    @staticmethod
    def _mime_type(format_name: str) -> str:
        """Return the MIME type for a validated visual format.

        Args:
            format_name (str): Validated format name with or without a leading dot.

        Returns:
            str: Specific image MIME type or a binary fallback.
        """
        normalized = format_name.lower().lstrip(".")
        if normalized == "svg":
            return "image/svg+xml"
        return mimetypes.guess_type("asset." + normalized)[0] or "application/octet-stream"

    @staticmethod
    def _stage(destination: Path, content: bytes) -> tuple[Path, Path]:
        """Write complete bytes to a hidden sibling staging file.

        Args:
            destination (Path): Final destination used to select the staging directory.
            content (bytes): Complete artifact bytes to flush and sync.

        Returns:
            tuple[Path, Path]: Hidden staging path and final destination.
        """
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=".publication-staging-", dir=destination.parent)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        return Path(name), destination

    @staticmethod
    def _ensure_available(content: Optional[Path], media: Optional[Path]) -> None:
        """Reject an operation when any requested destination already exists.

        Args:
            content (Optional[Path]): Proposed content destination, when applicable.
            media (Optional[Path]): Proposed media destination, when applicable.

        Returns:
            None: Available destinations continue without mutation.

        Raises:
            StorageError: If either proposed destination already exists.
        """
        for path in (content, media):
            if path is not None and path.exists():
                raise StorageError(f"Refusing to overwrite {path}")
