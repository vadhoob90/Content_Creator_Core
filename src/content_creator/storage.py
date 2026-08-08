"""Provide storage capabilities."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from pydantic import BaseModel

from .domain import RunState, utc_now


class StorageError(RuntimeError):
    """Report storage failures."""

    pass


class IdempotencyError(ValueError):
    """Report idempotency failures."""

    pass


def slugify(value: str) -> str:
    """Convert an identifier into a filesystem-safe slug.

    Args:
        value (str): The value to process.

    Returns:
        str: The resulting text for slugify.
    """
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value[:70] or "untitled"


class RunStore:
    """Manage run records."""

    def __init__(self, root: Path):
        """Initialize the run store with its required state and collaborators.

        Args:
            root (Path): The workspace root directory.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        self.root = root.resolve()
        self.runs_dir = self.root / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def create(self, state: RunState) -> RunState:
        """Create the run store workflow.

        Args:
            state (RunState): The persisted lifecycle state to inspect or update.

        Returns:
            RunState: The created run state for value.
        """
        run_dir = self.run_dir(state.id)
        run_dir.mkdir(parents=True, exist_ok=False)
        self.save_state(state)
        return state

    def create_idempotent(
        self,
        state: RunState,
        idempotency_key: str,
        fingerprint: str,
    ) -> Tuple[RunState, bool]:
        """Create the idempotent.

        Create a run exactly once for an idempotency key, returning the existing run only
        when its submission fingerprint matches.

        Args:
            state (RunState): The persisted lifecycle state to inspect or update.
            idempotency_key (str): The stable retry key for an equivalent submission.
            fingerprint (str): The deterministic fingerprint identifying the input set.

        Returns:
            Tuple[RunState, bool]: The created idempotent values in their documented order.

        Raises:
            StorageError: If the storage operation cannot complete.
        """
        key_hash = self.idempotency_key_hash(idempotency_key)
        database = self._idempotency_database()
        connection = None
        try:
            connection = sqlite3.connect(str(database), timeout=10)
            self._ensure_idempotency_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT fingerprint, run_id FROM submissions WHERE key_hash = ?",
                (key_hash,),
            ).fetchone()
            if existing:
                connection.rollback()
                return self._existing_submission(key_hash, fingerprint, existing), False
            state.idempotency_key_hash = key_hash
            connection.execute(
                "INSERT INTO submissions "
                "(key_hash, fingerprint, run_id, created_at) VALUES (?, ?, ?, ?)",
                (
                    key_hash,
                    fingerprint,
                    state.id,
                    utc_now().isoformat(),
                ),
            )
            self.create(state)
            connection.commit()
            return state, True
        except IdempotencyError:
            if connection is not None:
                connection.rollback()
            raise
        except (OSError, sqlite3.Error) as exc:
            if connection is not None:
                connection.rollback()
            raise StorageError("Could not persist idempotent run submission") from exc
        finally:
            if connection is not None:
                connection.close()

    def load_by_idempotency_key(
        self,
        idempotency_key: str,
        fingerprint: Optional[str] = None,
    ) -> Optional[RunState]:
        """Load the by idempotency key.

        Args:
            idempotency_key (str): The stable retry key for an equivalent submission.
            fingerprint (Optional[str]): The deterministic fingerprint identifying the input
                set. Defaults to ``None``.

        Returns:
            Optional[RunState]: The loaded by idempotency key when available; otherwise
                ``None``.

        Raises:
            StorageError: If the storage operation cannot complete.
        """
        key_hash = self.idempotency_key_hash(idempotency_key)
        database = self.root / ".content-creator" / "idempotency.sqlite3"
        if not database.exists():
            return None
        connection = None
        try:
            connection = sqlite3.connect(str(database), timeout=10)
            self._ensure_idempotency_schema(connection)
            existing = connection.execute(
                "SELECT fingerprint, run_id FROM submissions WHERE key_hash = ?",
                (key_hash,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise StorageError("Could not read idempotent run submission") from exc
        finally:
            if connection is not None:
                connection.close()
        if not existing:
            return None
        expected = fingerprint or existing[0]
        return self._existing_submission(key_hash, expected, existing)

    @staticmethod
    def idempotency_key_hash(idempotency_key: str) -> str:
        """Return the idempotency key hash.

        Args:
            idempotency_key (str): The stable retry key for an equivalent submission.

        Returns:
            str: The resulting text for idempotency key hash.

        Raises:
            IdempotencyError: If the idempotency operation cannot complete.
        """
        if not isinstance(idempotency_key, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", idempotency_key
        ):
            raise IdempotencyError(
                "Idempotency keys must be 1-128 letters, digits, dots, "
                "underscores, colons, or hyphens"
            )
        return hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()

    def _existing_submission(
        self,
        key_hash: str,
        fingerprint: str,
        existing: sqlite3.Row,
    ) -> RunState:
        """Return the existing submission.

        Args:
            key_hash (str): The key hash text processed when existing submission.
            fingerprint (str): The deterministic fingerprint identifying the input set.
            existing (sqlite3.Row): The existing value passed to existing submission.

        Returns:
            RunState: The resulting run state for existing submission.

        Raises:
            IdempotencyError: If the idempotency operation cannot complete.
            StorageError: If the storage operation cannot complete.
        """
        if existing[0] != fingerprint:
            raise IdempotencyError(
                "Idempotency key is already associated with a different work order"
            )
        state = self.load(existing[1])
        if state.idempotency_key_hash != key_hash:
            raise StorageError("Idempotency index does not match persisted run")
        state.idempotency_reused = True
        return state

    def _idempotency_database(self) -> Path:
        """Return the idempotency database.

        Returns:
            Path: The resolved filesystem path for idempotency database.
        """
        directory = self.root / ".content-creator"
        directory.mkdir(parents=True, exist_ok=True)
        return directory / "idempotency.sqlite3"

    @staticmethod
    def _ensure_idempotency_schema(connection: sqlite3.Connection) -> None:
        """Return the ensure idempotency schema.

        Args:
            connection (sqlite3.Connection): The connection value passed to ensure
                idempotency schema.

        Returns:
            None: The callable updates ensure idempotency schema state and returns no value.
        """
        connection.execute(
            "CREATE TABLE IF NOT EXISTS submissions ("
            "key_hash TEXT PRIMARY KEY, "
            "fingerprint TEXT NOT NULL, "
            "run_id TEXT NOT NULL UNIQUE, "
            "created_at TEXT NOT NULL"
            ")"
        )
        connection.commit()

    def load(self, run_id: str) -> RunState:
        """Load the run store workflow.

        Args:
            run_id (str): The stable identifier for the content run.

        Returns:
            RunState: The loaded run state for value.

        Raises:
            StorageError: If the storage operation cannot complete.
        """
        path = self.run_dir(run_id) / "state.json"
        if not path.exists():
            raise StorageError("Unknown run: {}".format(run_id))
        return RunState.model_validate_json(path.read_text(encoding="utf-8"))

    def save_state(self, state: RunState) -> None:
        """Save the state.

        Args:
            state (RunState): The persisted lifecycle state to inspect or update.

        Returns:
            None: The callable updates state state and returns no value.
        """
        state.updated_at = utc_now()
        from .production_manifest import refresh_production_manifest

        refresh_production_manifest(self.root, state, self._atomic_text)
        self._atomic_text(
            self.run_dir(state.id) / "state.json",
            state.model_dump_json(indent=2),
        )

    def write_artifact(self, run_id: str, name: str, value: Any) -> Path:
        """Write the artifact.

        Args:
            run_id (str): The stable identifier for the content run.
            name (str): The stable or human-readable name for the domain object.
            value (Any): The value to process.

        Returns:
            Path: The resolved filesystem path for write artifact.
        """
        path = self.run_dir(run_id) / name
        if isinstance(value, BaseModel):
            content = value.model_dump_json(indent=2)
        elif isinstance(value, (dict, list)):
            content = json.dumps(value, indent=2, default=str, ensure_ascii=False)
        else:
            content = str(value)
        self._atomic_text(path, content)
        return path

    def read_artifact(self, run_id: str, name: str) -> str:
        """Read the artifact.

        Args:
            run_id (str): The stable identifier for the content run.
            name (str): The stable or human-readable name for the domain object.

        Returns:
            str: The loaded text for artifact.

        Raises:
            StorageError: If the storage operation cannot complete.
        """
        path = self.run_dir(run_id) / name
        if not path.exists():
            raise StorageError("Missing artifact: {}".format(path))
        return path.read_text(encoding="utf-8")

    def run_dir(self, run_id: str) -> Path:
        """Run the dir.

        Args:
            run_id (str): The stable identifier for the content run.

        Returns:
            Path: The resolved filesystem path for dir.

        Raises:
            StorageError: If the storage operation cannot complete.
        """
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", run_id):
            raise StorageError("Invalid run id")
        return self.runs_dir / run_id

    @staticmethod
    def _atomic_text(path: Path, content: str) -> None:
        """Return the atomic text.

        Args:
            path (Path): The filesystem path to inspect or update.
            content (str): The content to process.

        Returns:
            None: The callable updates atomic text state and returns no value.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.write("\n")
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def load_json(path: Path) -> Dict[str, Any]:
    """Load the json.

    Args:
        path (Path): The filesystem path to inspect or update.

    Returns:
        Dict[str, Any]: The structured loaded data for json.
    """
    return json.loads(path.read_text(encoding="utf-8"))
