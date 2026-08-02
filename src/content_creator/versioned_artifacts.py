"""Shared mechanics for immutable, hash-verified domain artifacts.

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
    """Return the stable SHA-256 identifier used by Core manifests."""
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def hash_json(value: Any) -> str:
    """Hash JSON data independently of mapping insertion order."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def next_major_version(versions_root: Path) -> str:
    """Allocate the next immutable ``N.0.0`` directory version."""
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
    """Return component names that are missing or no longer match their manifest."""
    return [
        name
        for name, filename in components.items()
        if not (directory / filename).is_file()
        or hash_file(directory / filename) != expected_hashes.get(name)
    ]


class ActivationLock:
    """Small exclusive lock used while promoting a candidate artifact."""

    def __init__(
        self,
        path: Path,
        conflict_message: str,
        error_type: Type[RuntimeError] = RuntimeError,
    ):
        self.path = path
        self.conflict_message = conflict_message
        self.error_type = error_type

    def __enter__(self) -> ActivationLock:
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
        self.path.unlink(missing_ok=True)
