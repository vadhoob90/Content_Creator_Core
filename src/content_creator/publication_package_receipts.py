"""Build, revise, select, and verify publication-package receipt artifacts."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any, Optional

from .domain import RunState
from .publication_receipt_models import PublicationArtifactReceipt, PublicationReceipt
from .storage import RunStore, StorageError
from .versioned_artifacts import hash_file


class PublicationPackageReceipts:
    """Manage media-aware details that extend canonical publication receipts."""

    def __init__(self, root: Path, receipts_root: Path):
        """Initialize package receipt paths.

        Args:
            root (Path): Author workspace root.
            receipts_root (Path): Configured publication receipt directory.

        Returns:
            None: The service stores resolved paths in place.
        """
        self.root = root.resolve()
        self.receipts_root = receipts_root.resolve()

    def artifacts(self, state: RunState, target: Path) -> list[PublicationArtifactReceipt]:
        """Build the complete content-and-media package artifact list.

        Args:
            state (RunState): Published run containing selected media metadata.
            target (Path): Canonical published content artifact.

        Returns:
            list[PublicationArtifactReceipt]: Content first, followed by selected media.
        """
        artifacts = [
            PublicationArtifactReceipt(
                role="content",
                path=self._relative(target),
                sha256=hash_file(target),
                mime_type=self._media_type(target),
            )
        ]
        artifacts.extend(
            PublicationArtifactReceipt(
                role=item.role,
                path=item.published_path,
                source_path=item.source_path,
                sha256=item.sha256,
                mime_type=item.mime_type,
                width=item.width,
                height=item.height,
                alt_text=item.alt_text,
                approval_state=item.approval_state,
                asset_id=item.asset_id,
                parent_asset_id=item.parent_asset_id,
                derivation_revision=item.revision,
            )
            for item in state.published_media
        )
        return artifacts

    def replace(self, state: RunState) -> Path:
        """Update the canonical media receipt and preserve its immutable predecessor.

        Args:
            state (RunState): Published run containing the replacement media package.

        Returns:
            Path: Canonical receipt path updated to the next revision.

        Raises:
            ValueError: If the run, receipt, or receipt ownership is invalid.
        """
        if not state.published_path:
            raise ValueError("Published run has no content artifact")
        target = self._within_root(state.published_path)
        receipt_path = self._receipt_path(state.published_path)
        if not receipt_path.is_file():
            raise ValueError("Published run has no publication receipt")
        previous_bytes = receipt_path.read_bytes()
        previous = PublicationReceipt.model_validate_json(previous_bytes)
        if previous.run_id != state.id:
            raise ValueError("Publication receipt belongs to another run")
        previous_hash = hash_file(receipt_path)
        archive = receipt_path.with_name(
            "{}.receipt.r{}-{}.json".format(
                Path(state.published_path).name,
                previous.revision,
                previous_hash.removeprefix("sha256:")[:12],
            )
        )
        if archive.exists():
            raise ValueError(f"Refusing to overwrite {archive}")
        replacement = previous.model_copy(
            update={
                "revision": previous.revision + 1,
                "supersedes_receipt_hash": previous_hash,
                "artifact_hash": hash_file(target),
                "artifacts": self.artifacts(state, target),
            }
        )
        RunStore._atomic_text(archive, previous_bytes.decode("utf-8").rstrip())
        try:
            RunStore._atomic_text(receipt_path, replacement.model_dump_json(indent=2))
        except Exception:
            archive.unlink(missing_ok=True)
            raise
        return receipt_path

    def select_primary(
        self,
        artifacts: list[Path],
        baseline: dict[str, str],
        run_id: Optional[str],
        artifact_path: Optional[str],
        new_only: bool,
    ) -> list[Path]:
        """Select canonical content artifacts for bounded verification.

        Args:
            artifacts (list[Path]): All configured primary publication artifacts.
            baseline (dict[str, str]): Approved legacy artifact hashes by path.
            run_id (Optional[str]): Run scope, or ``None`` for no run filter.
            artifact_path (Optional[str]): Artifact scope, or ``None`` for no path filter.
            new_only (bool): Whether to exclude unchanged baseline artifacts.

        Returns:
            list[Path]: Stable primary artifacts matching the requested scope.

        Raises:
            StorageError: If a run scope is unknown or has no published artifact.
        """
        if artifact_path:
            return [self._within_root(artifact_path)]
        if run_id:
            state = RunStore(self.root).load(run_id)
            if not state.published_path:
                raise StorageError("Run has no published artifact")
            return [self._within_root(state.published_path)]
        if new_only:
            return [
                item for item in artifacts if baseline.get(self._relative(item)) != hash_file(item)
            ]
        return artifacts

    def existing_primary(self, artifacts: list[Path]) -> tuple[list[Path], list[dict[str, Any]]]:
        """Return existing primary artifacts and deterministic missing findings.

        Args:
            artifacts (list[Path]): Scoped canonical publication paths.

        Returns:
            tuple[list[Path], list[dict[str, Any]]]: Existing paths and missing findings.
        """
        existing = [item for item in artifacts if item.is_file()]
        missing = [
            self._finding("missing_artifact", self._relative(item), "Publication does not exist")
            for item in artifacts
            if not item.is_file()
        ]
        return existing, missing

    def verify(self, receipt: PublicationReceipt) -> list[dict[str, Any]]:
        """Verify every artifact named by a package-aware receipt.

        Legacy receipts without an artifact collection remain valid. Package-aware
        receipts additionally require unique paths, immutable bytes, complete image
        metadata, and exactly one canonical content role.

        Args:
            receipt (PublicationReceipt): Parsed canonical publication receipt.

        Returns:
            list[dict[str, Any]]: Normalized deterministic finding mappings.
        """
        if not receipt.artifacts:
            return []
        findings: list[dict[str, Any]] = []
        paths = [item.path for item in receipt.artifacts]
        if len(paths) != len(set(paths)):
            findings.append(
                self._finding(
                    "duplicate_package_artifact",
                    receipt.artifact_path,
                    "Publication package contains duplicate artifact paths",
                )
            )
        for item in receipt.artifacts:
            findings.extend(self._verify_artifact(item))
        content = [item for item in receipt.artifacts if item.role == "content"]
        if len(content) != 1 or content[0].path != receipt.artifact_path:
            findings.append(
                self._finding(
                    "invalid_content_artifact",
                    receipt.artifact_path,
                    "Package must contain one canonical content artifact",
                )
            )
        return findings

    def _verify_artifact(self, item: PublicationArtifactReceipt) -> list[dict[str, Any]]:
        """Verify bytes and required metadata for one package artifact.

        Args:
            item (PublicationArtifactReceipt): Content or media artifact receipt.

        Returns:
            list[dict[str, Any]]: Zero or more normalized finding mappings.
        """
        path = self._within_root(item.path)
        if not path.is_file():
            return [self._finding("missing_package_artifact", item.path, "Missing file")]
        findings = []
        if hash_file(path) != item.sha256:
            findings.append(
                self._finding("package_artifact_hash_mismatch", item.path, "Content changed")
            )
        if item.mime_type.startswith("image/") and (
            not item.alt_text or item.width is None or item.height is None
        ):
            findings.append(
                self._finding(
                    "incomplete_media_metadata",
                    item.path,
                    "Image artifact requires alt text and dimensions",
                )
            )
        return findings

    def _receipt_run_id(self, artifact: Path) -> Optional[str]:
        """Return the run identifier from an artifact's valid canonical receipt.

        Args:
            artifact (Path): Canonical published content artifact.

        Returns:
            Optional[str]: Receipt run identifier, or ``None`` when unavailable.
        """
        receipt = self._receipt_path(self._relative(artifact))
        if not receipt.is_file():
            return None
        try:
            return PublicationReceipt.model_validate_json(
                receipt.read_text(encoding="utf-8")
            ).run_id
        except (OSError, ValueError):
            return None

    def _receipt_path(self, artifact_path: str) -> Path:
        """Return the canonical sidecar path for a workspace-relative artifact.

        Args:
            artifact_path (str): Workspace-relative published content path.

        Returns:
            Path: Receipt sidecar under the configured receipt root.
        """
        relative = Path(artifact_path)
        return self.receipts_root / relative.parent / f"{relative.name}.receipt.json"

    def _within_root(self, relative: str) -> Path:
        """Resolve a workspace-relative path without allowing traversal.

        Args:
            relative (str): Candidate workspace-relative path.

        Returns:
            Path: Resolved path inside the workspace.

        Raises:
            ValueError: If the candidate leaves the workspace.
        """
        path = (self.root / relative).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("Publication path leaves workspace") from exc
        return path

    def _relative(self, path: Path) -> str:
        """Return a stable workspace-relative path.

        Args:
            path (Path): Resolved workspace path.

        Returns:
            str: Workspace-relative path text.

        Raises:
            ValueError: If the path leaves the workspace.
        """
        try:
            return str(path.resolve().relative_to(self.root))
        except ValueError as exc:
            raise ValueError("Publication path leaves workspace") from exc

    @staticmethod
    def _media_type(path: Path) -> str:
        """Return a stable MIME type for a publication artifact.

        Args:
            path (Path): Artifact whose suffix identifies its media type.

        Returns:
            str: Detected MIME type or a binary fallback.
        """
        return mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    @staticmethod
    def _finding(code: str, artifact_path: Optional[str], detail: str) -> dict[str, Any]:
        """Build one normalized deterministic package finding.

        Args:
            code (str): Stable machine-readable finding code.
            artifact_path (Optional[str]): Related artifact path when available.
            detail (str): Human-readable finding detail.

        Returns:
            dict[str, Any]: Finding mapping accepted by the provenance model.
        """
        return {
            "code": code,
            "artifact_path": artifact_path,
            "detail": detail,
        }
