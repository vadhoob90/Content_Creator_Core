from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .resource_paths import ResourceResolver


class PackError(ValueError):
    pass


class StatisticalVoiceScorePackPolicy(BaseModel):
    eligible: bool = False


class ContentPack(BaseModel):
    schema_version: str = "1.0"
    id: str
    version: str
    format: str
    destination: str
    extends: Optional[str] = None
    rubric: Optional[str] = "rubric.yaml"
    rubrics: List[str] = Field(default_factory=list)
    prompts: Dict[str, str] = Field(default_factory=dict)
    statistical_voice_score: StatisticalVoiceScorePackPolicy = Field(
        default_factory=StatisticalVoiceScorePackPolicy
    )
    validators: List[str] = Field(default_factory=list)
    integrity_validators: List[str] = Field(
        default_factory=lambda: [
            "personal-integrity",
            "provenance",
            "phrase-overlap",
        ]
    )
    defaults: Dict[str, Any] = Field(default_factory=dict)
    allowed_run_overrides: List[str] = Field(
        default_factory=lambda: [
            "objective",
            "audience",
            "language",
            "length",
            "research",
            "structure",
            "destination",
        ]
    )
    allowed_research: List[str] = Field(
        default_factory=lambda: ["none", "light", "deep"]
    )


class PackRegistry:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.resources = ResourceResolver(self.root)
        self._packs: Dict[str, ContentPack] = {}

    def path(self, pack_id: str, filename: str = "pack.json") -> Path:
        return self.resources.path(
            Path("packs") / pack_id / filename
        )

    def get(self, pack_id: str) -> ContentPack:
        if pack_id in self._packs:
            return self._packs[pack_id]
        path = self.path(pack_id)
        if not path.exists():
            raise PackError("Unknown content pack: {}".format(pack_id))
        pack = ContentPack.model_validate_json(path.read_text(encoding="utf-8"))
        if pack.id != pack_id:
            raise PackError(
                "Pack id {} does not match directory {}".format(pack.id, pack_id)
            )
        self._packs[pack_id] = pack
        return pack

    def resolve(
        self, pack_id: str, overrides: Optional[Dict[str, Any]] = None
    ) -> ContentPack:
        chain: List[ContentPack] = []
        seen = set()
        current = self.get(pack_id)
        while current:
            if current.id in seen:
                raise PackError("Content pack inheritance cycle")
            seen.add(current.id)
            chain.append(current)
            current = self.get(current.extends) if current.extends else None
        if len(chain) > 2:
            raise PackError("Content packs may extend exactly one base pack")

        data = chain[-1].model_dump()
        for child in reversed(chain[:-1]):
            child_data = child.model_dump(exclude_unset=True)
            for mapping in ("defaults", "prompts", "statistical_voice_score"):
                merged = dict(data.get(mapping, {}))
                merged.update(child_data.get(mapping, {}))
                child_data[mapping] = merged
            for sequence in ("rubrics", "validators"):
                child_data[sequence] = list(
                    dict.fromkeys(data.get(sequence, []) + child_data.get(sequence, []))
                )
            child_data["integrity_validators"] = list(
                dict.fromkeys(
                    data.get("integrity_validators", [])
                    + child_data.get("integrity_validators", [])
                )
            )
            data.update(child_data)

        requested = deepcopy(overrides or {})
        forbidden = sorted(set(requested) - set(data["allowed_run_overrides"]))
        if forbidden:
            raise PackError(
                "Forbidden pack override(s): {}".format(", ".join(forbidden))
            )
        if "destination" in requested:
            data["destination"] = requested.pop("destination")
        length = requested.get("length")
        if isinstance(length, str):
            parts = length.split(":")
            if (
                len(parts) != 2
                or not all(part.isdigit() for part in parts)
                or int(parts[0]) > int(parts[1])
            ):
                raise PackError("Length override must be MIN:MAX")
        data["defaults"] = {**data.get("defaults", {}), **requested}
        destination = (self.root / data["destination"]).resolve()
        try:
            destination.relative_to(self.root)
        except ValueError as exc:
            raise PackError("Pack destination leaves repository root") from exc
        return ContentPack.model_validate(data)

    def list(self) -> List[ContentPack]:
        return [
            self.get(path.parent.name)
            for path in self.resources.matching("packs", "*/pack.json")
        ]
