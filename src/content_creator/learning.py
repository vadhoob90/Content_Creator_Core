"""Provide learning capabilities."""

from __future__ import annotations

import json
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Optional

from .domain import LearningExtraction, LearningRecord
from .storage import RunStore
from .voice_upgrade.epochs import epoch_path, load_epoch


class LearningMemory:
    """Represent a learning memory."""

    def __init__(
        self,
        root: Path,
        voice_id: str = "default",
        voice_version: Optional[str] = None,
    ):
        """Initialize the learning memory with its required state and collaborators.

        Args:
            root (Path): The workspace root directory.
            voice_id (str): The stable identifier for the selected voice. Defaults to
                ``'default'``.
            voice_version (Optional[str]): Exact immutable learning epoch. Defaults to
                ``None`` for legacy compatibility.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        self.root = root.resolve()
        self.voice_id = voice_id
        self.voice_version = voice_version
        self.path = (
            epoch_path(self.root, voice_id, voice_version)
            if voice_version
            else self.root / "profiles" / voice_id / "learnings" / "memory.json"
        )

    def apply(
        self,
        run_id: str,
        extraction: LearningExtraction,
        explicit_feedback: Optional[str] = None,
        voice_version: Optional[str] = None,
        content_pack: Optional[str] = None,
    ) -> None:
        """Append new run learning to the selected mutable voice epoch.

        Preserve existing records, suppress equivalent principles, and record conflicts
        without modifying immutable voice guidance.

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

        Raises:
            ValueError: If the selected version's learning epoch is frozen.
        """
        resolved_version = voice_version or self.voice_version
        registry_path = self.root / "profiles" / "registry.json"
        if registry_path.exists() and self.voice_id in json.loads(
            registry_path.read_text(encoding="utf-8")
        ).get("profiles", {}):
            from .voices import VoiceRegistry

            VoiceRegistry(self.root).resolve(self.voice_id, resolved_version)
        path = (
            epoch_path(self.root, self.voice_id, resolved_version)
            if resolved_version
            else self.path
        )
        if resolved_version:
            epoch = load_epoch(
                self.root,
                self.voice_id,
                resolved_version,
                migrate_legacy=True,
            )
            if epoch.status != "active":
                raise ValueError(
                    "Learning epoch is frozen for voice version {}".format(resolved_version)
                )
            data: Dict[str, Any] = epoch.model_dump(mode="json")
        else:
            data = {"version": 1, "records": []}
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
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
                voice_id=self.voice_id,
                voice_version=resolved_version,
                content_pack=content_pack,
                conflicts_with=list(dict.fromkeys(candidate.conflicts_with + conflicts)),
            )
            data["records"].append(record.model_dump(mode="json"))
            existing.add(key)
        RunStore._atomic_text(path, json.dumps(data, indent=2, ensure_ascii=False))

    def consolidate_candidate(self) -> Path:
        """Return the consolidate candidate.

        Returns:
            Path: The resolved filesystem path for consolidate candidate.
        """
        data: Dict[str, Any] = {"version": 1, "records": []}
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
        candidate = self.root / "profiles" / self.voice_id / "learning-candidate.json"
        RunStore._atomic_text(
            candidate,
            json.dumps(
                {
                    "status": "candidate",
                    "voice_id": self.voice_id,
                    "voice_version": self.voice_version,
                    "source_learning_ids": [
                        item["id"] for item in data["records"] if item.get("status") == "active"
                    ],
                },
                indent=2,
            ),
        )
        return candidate
