"""Provide learning capabilities."""

from __future__ import annotations

import json
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Optional

from .domain import LearningExtraction, LearningRecord
from .storage import RunStore


class LearningMemory:
    """Represent a learning memory."""

    def __init__(self, root: Path, voice_id: str = "default"):
        """Initialize the learning memory with its required state and collaborators.

        Args:
            root (Path): The workspace root directory.
            voice_id (str): The stable identifier for the selected voice. Defaults to
                ``'default'``.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        self.path = root / "profiles" / voice_id / "learnings" / "memory.json"

    def apply(
        self,
        run_id: str,
        extraction: LearningExtraction,
        explicit_feedback: Optional[str] = None,
        voice_version: Optional[str] = None,
        content_pack: Optional[str] = None,
    ) -> None:
        """Apply the learning memory workflow.

        Args:
            run_id (str): The stable identifier for the content run.
            extraction (LearningExtraction): The extraction value passed to apply.
            explicit_feedback (Optional[str]): The explicit feedback text processed when
                apply. Defaults to ``None``.
            voice_version (Optional[str]): The immutable version of the selected voice
                profile. Defaults to ``None``.
            content_pack (Optional[str]): The content pack text processed when apply.
                Defaults to ``None``.

        Returns:
            None: The callable updates apply state and returns no value.
        """
        data: Dict[str, Any] = {"version": 1, "records": []}
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
        existing = {(item["role"], item["principle"].strip().lower()) for item in data["records"]}
        for candidate in extraction.candidates:
            key = (candidate.role, candidate.principle.strip().lower())
            if key in existing:
                continue
            conflicts = [
                item["id"]
                for item in data["records"]
                if item.get("role") == candidate.role
                and SequenceMatcher(
                    None,
                    item.get("principle", "").lower(),
                    candidate.principle.lower(),
                ).ratio()
                >= 0.7
            ]
            record = LearningRecord(
                **candidate.model_dump(exclude={"status", "conflicts_with"}),
                status=(candidate.status if explicit_feedback else "provisional"),
                run_id=run_id,
                voice_id=self.path.parents[1].name,
                voice_version=voice_version,
                content_pack=content_pack,
                conflicts_with=list(dict.fromkeys(candidate.conflicts_with + conflicts)),
            )
            data["records"].append(record.model_dump(mode="json"))
            existing.add(key)
        RunStore._atomic_text(self.path, json.dumps(data, indent=2, ensure_ascii=False))

    def consolidate_candidate(self) -> Path:
        """Return the consolidate candidate.

        Returns:
            Path: The resolved filesystem path for consolidate candidate.
        """
        data: Dict[str, Any] = {"version": 1, "records": []}
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
        candidate = self.path.parents[1] / "learning-candidate.json"
        RunStore._atomic_text(
            candidate,
            json.dumps(
                {
                    "status": "candidate",
                    "source_learning_ids": [
                        item["id"] for item in data["records"] if item.get("status") == "active"
                    ],
                },
                indent=2,
            ),
        )
        return candidate
