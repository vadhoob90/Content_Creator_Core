from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from pydantic import BaseModel, Field


class PackError(ValueError):
    pass


class ContentPack(BaseModel):
    id: str
    version: str
    format: str
    destination: str
    rubric: str = "rubric.yaml"
    allowed_research: List[str] = Field(
        default_factory=lambda: ["none", "light", "deep"]
    )


class PackRegistry:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self._packs: Dict[str, ContentPack] = {}

    def get(self, pack_id: str) -> ContentPack:
        if pack_id in self._packs:
            return self._packs[pack_id]
        path = self.root / "packs" / pack_id / "pack.json"
        if not path.exists():
            raise PackError("Unknown content pack: {}".format(pack_id))
        pack = ContentPack.model_validate_json(path.read_text(encoding="utf-8"))
        if pack.id != pack_id:
            raise PackError(
                "Pack id {} does not match directory {}".format(pack.id, pack_id)
            )
        self._packs[pack_id] = pack
        return pack

    def list(self) -> List[ContentPack]:
        return [
            self.get(path.parent.name)
            for path in sorted((self.root / "packs").glob("*/pack.json"))
        ]
