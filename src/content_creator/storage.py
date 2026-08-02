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
    pass


class IdempotencyError(ValueError):
    pass


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value[:70] or "untitled"


class RunStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.runs_dir = self.root / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def create(self, state: RunState) -> RunState:
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
        directory = self.root / ".content-creator"
        directory.mkdir(parents=True, exist_ok=True)
        return directory / "idempotency.sqlite3"

    @staticmethod
    def _ensure_idempotency_schema(connection: sqlite3.Connection) -> None:
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
        path = self.run_dir(run_id) / "state.json"
        if not path.exists():
            raise StorageError("Unknown run: {}".format(run_id))
        return RunState.model_validate_json(path.read_text(encoding="utf-8"))

    def save_state(self, state: RunState) -> None:
        state.updated_at = utc_now()
        self._atomic_text(
            self.run_dir(state.id) / "state.json",
            state.model_dump_json(indent=2),
        )

    def write_artifact(self, run_id: str, name: str, value: Any) -> Path:
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
        path = self.run_dir(run_id) / name
        if not path.exists():
            raise StorageError("Missing artifact: {}".format(path))
        return path.read_text(encoding="utf-8")

    def run_dir(self, run_id: str) -> Path:
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", run_id):
            raise StorageError("Invalid run id")
        return self.runs_dir / run_id

    @staticmethod
    def _atomic_text(path: Path, content: str) -> None:
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
    return json.loads(path.read_text(encoding="utf-8"))
