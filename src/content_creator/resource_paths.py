"""Provide resource paths capabilities."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Union


class ResourceError(ValueError):
    """Report resource failures."""

    pass


class ResourceResolver:
    """Resolve workspace overrides before packaged core resources."""

    def __init__(self, workspace: Path, core: Optional[Path] = None):
        """Initialize the resource resolver with its required state and collaborators.

        Args:
            workspace (Path): The workspace service or directory used by the operation.
            core (Optional[Path]): The filesystem path containing the core. Defaults to
                ``None``.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        self.workspace = workspace.resolve()
        self.core = (core or Path(__file__).with_name("resources")).resolve()

    @staticmethod
    def _relative(value: Union[str, Path]) -> Path:
        """Convert the resource path to a workspace-relative path.

        Args:
            value (Union[str, Path]): The value to process.

        Returns:
            Path: The resolved filesystem path for relative.

        Raises:
            ResourceError: If the resource operation cannot complete.
        """
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts:
            raise ResourceError("Resource paths must stay within their root")
        return relative

    def path(self, relative: Union[str, Path]) -> Path:
        """Resolve the filesystem path managed by resource resolver.

        Args:
            relative (Union[str, Path]): The filesystem path containing the relative.

        Returns:
            Path: The resolved filesystem path for path.
        """
        relative = self._relative(relative)
        override = self.workspace / relative
        if override.exists():
            return override
        packaged = self.core / relative
        if packaged.exists():
            return packaged
        return override

    def workspace_path(self, relative: Union[str, Path]) -> Path:
        """Return the workspace path.

        Args:
            relative (Union[str, Path]): The filesystem path containing the relative.

        Returns:
            Path: The resolved filesystem path for workspace path.
        """
        return self.workspace / self._relative(relative)

    def matching(self, relative: Union[str, Path], pattern: str) -> List[Path]:
        """Return the matching.

        Args:
            relative (Union[str, Path]): The filesystem path containing the relative.
            pattern (str): The pattern text processed when matching.

        Returns:
            List[Path]: The resolved filesystem path for matching.
        """
        relative = self._relative(relative)
        matches: Dict[str, Path] = {}
        for base in (self.core / relative, self.workspace / relative):
            if not base.exists():
                continue
            for path in sorted(base.glob(pattern)):
                matches[str(path.relative_to(base))] = path
        return [matches[key] for key in sorted(matches)]
