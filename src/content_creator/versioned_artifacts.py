"""Provide versioned artifacts contracts and behavior.

This module owns filesystem mechanics only. Voice and perspective modules retain
their lifecycle policy, validation rules, manifests, and registry schemas.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Callable
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


def numeric_version_directories(versions_root: Path) -> list[Path]:
    """Return published semantic-version directories from newest to oldest.

    Hidden promotion state and unrelated directories are excluded so recovery only
    considers immutable snapshots that crossed the atomic publication boundary.

    Args:
        versions_root (Path): Directory containing immutable versions.

    Returns:
        list[Path]: Numeric semantic-version directories in descending order.
    """

    def version_key(path: Path) -> tuple[int, int, int]:
        """Return the numeric sort key for one version directory.

        Args:
            path (Path): Candidate version directory.

        Returns:
            tuple[int, int, int]: Numeric semantic-version components, or sentinels
                for an invalid directory name.
        """
        parts = path.name.split(".")
        if len(parts) != 3 or not all(part.isdigit() for part in parts):
            return (-1, -1, -1)
        return (int(parts[0]), int(parts[1]), int(parts[2]))

    return sorted(
        (
            path
            for path in versions_root.glob("*")
            if path.is_dir() and version_key(path) != (-1, -1, -1)
        ),
        key=version_key,
        reverse=True,
    )


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


def publish_candidate(
    voice_root: Path,
    operation: Callable[[Any], None],
    state: Any,
    error_type: Type[RuntimeError],
) -> None:
    """Publish a built voice candidate under the shared lifecycle lock.

    Args:
        voice_root (Path): Root directory for one selected voice.
        operation (Callable[[Any], None]): Candidate directory swap operation.
        state (Any): Completed build state passed to the swap operation.
        error_type (Type[RuntimeError]): Runtime error raised on lock conflict.

    Returns:
        None: The candidate is published in place.
    """
    with ActivationLock(
        voice_root / ".lifecycle.lock",
        "Voice candidate lifecycle operation is already in progress",
        error_type,
    ):
        operation(state)


def replace_candidate(staging: Path, candidate: Path) -> None:
    """Publish a mutable candidate atomically while preserving rollback safety.

    Args:
        staging (Path): Complete staged candidate directory to publish.
        candidate (Path): Mutable candidate directory replaced by the staged snapshot.

    Returns:
        None: The staged directory becomes the candidate in place.

    """
    previous = candidate.parent / ".candidate-previous"
    if previous.exists():
        shutil.rmtree(previous)
    if candidate.exists():
        os.replace(candidate, previous)
    try:
        os.replace(staging, candidate)
    except Exception:
        if previous.exists():
            os.replace(previous, candidate)
        raise
    if previous.exists():
        shutil.rmtree(previous)


def publish_version_snapshot(
    candidate: Path,
    versions_root: Path,
    prepare: Callable[[Path, str], None],
    verify: Callable[[Path], None],
) -> tuple[str, Path]:
    """Publish one complete immutable version through a hidden staging directory.

    The caller must hold the lifecycle lock shared with candidate replacement. The
    candidate is copied once, domain-specific active metadata is written to the hidden
    snapshot, and verification runs before the numeric version becomes visible.

    Args:
        candidate (Path): Validated mutable candidate directory to snapshot.
        versions_root (Path): Directory containing immutable numeric versions.
        prepare (Callable[[Path, str], None]): Callback that writes active manifests,
            receipts, and locks into the hidden snapshot.
        verify (Callable[[Path], None]): Callback that fails closed unless the prepared
            snapshot is complete and internally consistent.

    Returns:
        tuple[str, Path]: Allocated version and atomically published destination.

    """
    versions_root.mkdir(parents=True, exist_ok=True)
    version = next_major_version(versions_root)
    destination = versions_root / version
    staging = versions_root / f".{version}.promotion-staging"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        shutil.copytree(candidate, staging)
        prepare(staging, version)
        verify(staging)
        os.replace(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return version, destination


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
