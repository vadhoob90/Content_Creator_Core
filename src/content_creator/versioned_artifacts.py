"""Provide versioned artifacts contracts and behavior.

This module owns filesystem mechanics only. Voice and perspective modules retain
their lifecycle policy, validation rules, manifests, and registry schemas.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Mapping, Type


def hash_file(path: Path) -> str:
    """Return the stable SHA-256 identifier used by Core manifests.

    Args:
        path (Path): The filesystem path to inspect or update.

    Returns:
        str: The resulting text for hash file.
    """
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def hash_json(value: Any) -> str:
    """Hash JSON data independently of mapping insertion order.

    Args:
        value (Any): The value to process.

    Returns:
        str: The resulting text for hash json.
    """
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def next_major_version(versions_root: Path) -> str:
    """Allocate the next immutable ``N.0.0`` directory version.

    Args:
        versions_root (Path): The filesystem path containing the versions root.

    Returns:
        str: The resulting text for next major version.
    """
    majors = [
        int(path.name.split(".")[0])
        for path in versions_root.glob("*")
        if path.is_dir() and path.name.split(".")[0].isdigit()
    ]
    return "{}.0.0".format(max(majors, default=0) + 1)


def verify_components(
    directory: Path,
    components: Mapping[str, str],
    expected_hashes: Mapping[str, str],
) -> list[str]:
    """Return component names that are missing or no longer match their manifest.

    Args:
        directory (Path): The filesystem path containing the directory.
        components (Mapping[str, str]): The components value passed to verify
            components.
        expected_hashes (Mapping[str, str]): The expected hashes value passed to verify
            components.

    Returns:
        list[str]: The verified components values in their documented order.
    """
    return [
        name
        for name, filename in components.items()
        if not (directory / filename).is_file()
        or hash_file(directory / filename) != expected_hashes.get(name)
    ]


class ActivationLock:
    """Represent the activation lock contract."""

    def __init__(
        self,
        path: Path,
        conflict_message: str,
        error_type: Type[RuntimeError] = RuntimeError,
    ):
        """Initialize the activation lock with its required state and collaborators.

        Args:
            path (Path): The filesystem path to inspect or update.
            conflict_message (str): The conflict message text processed when init.
            error_type (Type[RuntimeError]): The error type value passed to init. Defaults
                to ``RuntimeError``.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        self.path = path
        self.conflict_message = conflict_message
        self.error_type = error_type

    def __enter__(self) -> ActivationLock:
        """Enter the activation lock context.

        Returns:
            ActivationLock: The resulting activation lock for enter.

        Raises:
            self.error_type: If the error type operation cannot complete.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            metadata = json.dumps(
                {"pid": os.getpid(), "created_at": datetime.now(UTC).isoformat()}
            ).encode()
            os.write(descriptor, metadata)
            os.close(descriptor)
        except FileExistsError as exc:
            raise self.error_type(self.conflict_message) from exc
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Exit the activation lock context.

        Args:
            exc_type (type[BaseException] | None): The exc type value passed to exit.
            exc (BaseException | None): The exception raised by the failed operation.
            traceback (TracebackType | None): The traceback value passed to exit.

        Returns:
            None: The callable updates exit state and returns no value.
        """
        self.path.unlink(missing_ok=True)
