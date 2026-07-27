from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .domain import LearningExtraction, LearningRecord
from .storage import RunStore


class LearningMemory:
    def __init__(self, root: Path, voice_id: str = "default"):
        self.path = root / "profiles" / voice_id / "learnings" / "memory.json"

    def apply(
        self,
        run_id: str,
        extraction: LearningExtraction,
        explicit_feedback: Optional[str] = None,
    ) -> None:
        data = {"version": 1, "records": []}
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
        existing = {
            (item["role"], item["principle"].strip().lower()) for item in data["records"]
        }
        for candidate in extraction.candidates:
            key = (candidate.role, candidate.principle.strip().lower())
            if key in existing:
                continue
            record = LearningRecord(
                **candidate.model_dump(exclude={"status"}),
                status=candidate.status,
                run_id=run_id,
            )
            data["records"].append(record.model_dump(mode="json"))
            existing.add(key)
        RunStore._atomic_text(
            self.path, json.dumps(data, indent=2, ensure_ascii=False)
        )
