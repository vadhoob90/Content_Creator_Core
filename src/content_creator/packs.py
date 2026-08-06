"""Provide packs capabilities."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .resource_paths import ResourceResolver
from .visuals import VisualPackProfile


class PackError(ValueError):
    """Report pack failures."""

    pass


class StatisticalVoiceScorePackPolicy(BaseModel):
    """Represent a statistical voice score pack policy."""

    eligible: bool = False


class ContentPack(BaseModel):
    """Represent a content pack."""

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
    visuals: VisualPackProfile = Field(default_factory=VisualPackProfile)
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
    allowed_research: List[str] = Field(default_factory=lambda: ["none", "light", "deep"])


class PackRegistry:
    """Manage pack records."""

    def __init__(self, root: Path):
        """Initialize the pack registry with its required state and collaborators.

        Args:
            root (Path): The workspace root directory.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        self.root = root.resolve()
        self.resources = ResourceResolver(self.root)
        self._packs: Dict[str, ContentPack] = {}

    def path(self, pack_id: str, filename: str = "pack.json") -> Path:
        """Resolve the filesystem path managed by pack registry.

        Args:
            pack_id (str): The stable identifier for the pack.
            filename (str): The filename text processed when path. Defaults to
                ``'pack.json'``.

        Returns:
            Path: The resolved filesystem path for path.
        """
        return self.resources.path(Path("packs") / pack_id / filename)

    def get(self, pack_id: str) -> ContentPack:
        """Retrieve the pack registry managed by pack registry.

        Args:
            pack_id (str): The stable identifier for the pack.

        Returns:
            ContentPack: The resulting content pack for get.

        Raises:
            PackError: If the pack operation cannot complete.
        """
        if pack_id in self._packs:
            return self._packs[pack_id]
        path = self.path(pack_id)
        if not path.exists():
            raise PackError("Unknown content pack: {}".format(pack_id))
        pack = ContentPack.model_validate_json(path.read_text(encoding="utf-8"))
        if pack.id != pack_id:
            raise PackError("Pack id {} does not match directory {}".format(pack.id, pack_id))
        self._packs[pack_id] = pack
        return pack

    def resolve(self, pack_id: str, overrides: Optional[Dict[str, Any]] = None) -> ContentPack:
        """Resolve the pack registry workflow.

        Args:
            pack_id (str): The stable identifier for the pack.
            overrides (Optional[Dict[str, Any]]): The overrides value passed to resolve.
                Defaults to ``None``.

        Returns:
            ContentPack: The resolved content pack for value.
        """
        data = self._merged_pack(pack_id)
        self._apply_overrides(data, overrides)
        self._validate_destinations(data)
        return ContentPack.model_validate(data)

    def override_compatibility(
        self, pack_id: str, overrides: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Describe legacy overrides no longer owned by a run.

        Compare forbidden persisted overrides with current pack defaults without
        changing either the run or the resolved pack.

        Args:
            pack_id (str): Content pack identifier.
            overrides (Optional[Dict[str, Any]]): Persisted run overrides. Defaults to
                ``None``.

        Returns:
            List[Dict[str, Any]]: Structured compatible or conflicting decisions.
        """
        data = self._merged_pack(pack_id)
        requested = deepcopy(overrides or {})
        forbidden = sorted(set(requested) - set(data["allowed_run_overrides"]))
        defaults = data.get("defaults", {})
        return [
            {
                "setting": key,
                "legacy_value": requested[key],
                "current_value": defaults.get(key),
                "outcome": (
                    "compatible"
                    if key in defaults and requested[key] == defaults[key]
                    else "conflict"
                ),
                "effective_source": "current_pack",
            }
            for key in forbidden
        ]

    def _merged_pack(self, pack_id: str) -> Dict[str, Any]:
        """Return the merged pack.

        Args:
            pack_id (str): The stable identifier for the pack.

        Returns:
            Dict[str, Any]: The structured resulting data for merged pack.

        Raises:
            PackError: If the pack operation cannot complete.
        """
        chain: List[ContentPack] = []
        seen = set()
        current: Optional[ContentPack] = self.get(pack_id)
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
            for mapping in ("defaults", "prompts", "statistical_voice_score", "visuals"):
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
        return data

    @staticmethod
    def _apply_overrides(data: Dict[str, Any], overrides: Optional[Dict[str, Any]]) -> None:
        """Apply the overrides.

        Args:
            data (Dict[str, Any]): The structured data to process.
            overrides (Optional[Dict[str, Any]]): The overrides value passed to apply
                overrides.

        Returns:
            None: The callable updates apply overrides state and returns no value.

        Raises:
            PackError: If the pack operation cannot complete.
        """
        requested = deepcopy(overrides or {})
        # Runs created by older Core versions could persist effective pack policy as a
        # run override.  Newer packs own that policy.  Treat an identical value as
        # redundant migration data, while continuing to reject a value that would
        # actually change the resolved pack contract.
        defaults = data.get("defaults", {})
        for key in set(requested) - set(data["allowed_run_overrides"]):
            if key in defaults and requested[key] == defaults[key]:
                requested.pop(key)
        forbidden = sorted(set(requested) - set(data["allowed_run_overrides"]))
        if forbidden:
            raise PackError("Forbidden pack override(s): {}".format(", ".join(forbidden)))
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

    def _validate_destinations(self, data: Dict[str, Any]) -> None:
        """Validate the destinations.

        Args:
            data (Dict[str, Any]): The structured data to process.

        Returns:
            None: The callable updates destinations state and returns no value.

        Raises:
            PackError: If the pack operation cannot complete.
        """
        destination = (self.root / data["destination"]).resolve()
        try:
            destination.relative_to(self.root)
        except ValueError as exc:
            raise PackError("Pack destination leaves repository root") from exc
        visual_destination = data.get("visuals", {}).get("destination")
        if visual_destination:
            resolved_visual_destination = (self.root / visual_destination).resolve()
            try:
                resolved_visual_destination.relative_to(self.root)
            except ValueError as exc:
                raise PackError("Visual destination leaves repository root") from exc

    def list(self) -> List[ContentPack]:
        """List the pack registry workflow.

        Returns:
            List[ContentPack]: The available value values in their documented order.
        """
        return [
            self.get(path.parent.name) for path in self.resources.matching("packs", "*/pack.json")
        ]
