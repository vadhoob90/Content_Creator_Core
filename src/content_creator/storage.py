from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict

from pydantic import BaseModel

from .domain import RunState, utc_now


class StorageError(RuntimeError):
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
