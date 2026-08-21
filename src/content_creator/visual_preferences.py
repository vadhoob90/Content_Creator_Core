"""Persist author-approved visual preferences outside linguistic voice memory."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from .domain import utc_now
from .storage import RunStore


class VisualPreferenceRecord(BaseModel):
    """Represent one evidence-backed visual preference."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    principle: str
    evidence: str
    run_id: str
    role: str = "visual"
    status: str = "active"
    scope: str = "visual"
    created_at: str = Field(default_factory=lambda: utc_now().isoformat())


class VisualPreferenceMemory:
    """Manage voice-selected visual preferences in a dedicated memory file."""

    def __init__(self, root: Path, voice_id: str = "default"):
        """Initialize visual preference memory for one selected author voice.

        Args:
            root (Path): Author workspace root.
            voice_id (str): Selected author voice identifier. Defaults to ``"default"``.

        Returns:
            None: The memory stores its dedicated visual-scope path in place.
        """
        self.path = root / "profiles" / voice_id / "visual-learnings" / "memory.json"

    def record(self, run_id: str, principle: str, evidence: str | None = None) -> Path:
        """Persist explicit visual feedback without changing writing voice memory.

        Args:
            run_id (str): Reviewed run that supplied the author feedback.
            principle (str): Durable visual preference stated by the author.
            evidence (str | None): Evidence label. Defaults to ``None``.

        Returns:
            Path: Dedicated visual preference memory path.

        Raises:
            ValueError: If the preference is empty or existing memory is invalid.
        """
        principle = principle.strip()
        if not principle:
            raise ValueError("Visual preference feedback must not be empty")
        data = self._load()
        existing = {str(item.get("principle", "")).strip().casefold() for item in data["records"]}
        if principle.casefold() not in existing:
            record = VisualPreferenceRecord(
                principle=principle,
                evidence=(evidence or "Explicit author visual feedback").strip(),
                run_id=run_id,
            )
            data["records"].append(record.model_dump(mode="json"))
        RunStore._atomic_text(
            self.path,
            json.dumps(data, indent=2, ensure_ascii=False),
        )
        return self.path

    def active_principles(self) -> list[str]:
        """Return active visual preferences in recorded order.

        Returns:
            list[str]: Active visual principles without linguistic voice records.
        """
        return [
            str(item["principle"])
            for item in self._load()["records"]
            if item.get("status") == "active" and item.get("principle")
        ]

    def _load(self) -> dict:
        """Load visual memory while preserving an empty-file default.

        Returns:
            dict: Versioned visual-scope memory with a records list.

        Raises:
            ValueError: If persisted memory does not contain a records list.
        """
        if not self.path.exists():
            return {"version": 1, "scope": "visual", "records": []}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
            raise ValueError("Visual preference memory must contain a records list")
        payload.setdefault("version", 1)
        payload.setdefault("scope", "visual")
        return payload
