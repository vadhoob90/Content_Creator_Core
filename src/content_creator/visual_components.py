"""Manage immutable reusable visual components shipped by Core."""

from __future__ import annotations

import json
from enum import Enum
from importlib.resources import files
from typing import Iterable, List

from pydantic import BaseModel, Field

from .visual_contracts import ExecutionClass, VisualComponentRef, VisualError


class VisualComponentKind(str, Enum):
    """Classify reusable visual component responsibilities."""

    CONTRACT = "contract"
    LAYOUT = "layout"
    RENDERER = "renderer"
    VALIDATOR = "validator"
    PREVIEW = "preview"


class VisualComponent(BaseModel):
    """Describe one versioned reusable visual component."""

    id: str
    version: str
    kind: VisualComponentKind
    supported_roles: List[str] = Field(default_factory=lambda: ["*"])
    execution_classes: List[ExecutionClass] = Field(default_factory=list)
    formats: List[str] = Field(default_factory=list)
    aspect_ratios: List[str] = Field(default_factory=list)
    required_inputs: List[str] = Field(default_factory=list)
    produced_outputs: List[str] = Field(default_factory=list)
    provenance: str = "content-creator-core"
    compatibility: dict[str, str] = Field(default_factory=dict)

    def reference(self) -> VisualComponentRef:
        """Return the immutable reference persisted with a visual run.

        Returns:
            VisualComponentRef: Stable component identity and provenance.
        """
        return VisualComponentRef(
            id=self.id,
            version=self.version,
            kind=self.kind.value,
            provenance=self.provenance,
        )

    def supports(
        self,
        role: str,
        execution_class: ExecutionClass,
        output_format: str,
        aspect_ratio: str,
    ) -> bool:
        """Return whether this component is compatible with a requested output.

        Args:
            role (str): Pack-owned visual role.
            execution_class (ExecutionClass): Requested rendering execution class.
            output_format (str): Requested output format without a leading dot.
            aspect_ratio (str): Requested positive ``WIDTH:HEIGHT`` ratio.

        Returns:
            bool: Whether every declared compatibility constraint is satisfied.
        """
        return (
            ("*" in self.supported_roles or role in self.supported_roles)
            and (not self.execution_classes or execution_class in self.execution_classes)
            and (not self.formats or output_format in self.formats)
            and (not self.aspect_ratios or aspect_ratio in self.aspect_ratios)
        )


class VisualComponentRegistry:
    """Enumerate and resolve compatible Core visual components."""

    def __init__(self, components: Iterable[VisualComponent]):
        """Initialize a registry from reviewed immutable component records.

        Args:
            components (Iterable[VisualComponent]): Components available to the host.

        Returns:
            None: The registry is initialized in place.

        Raises:
            VisualError: If component IDs are duplicated.
        """
        self._components = sorted(components, key=lambda item: (item.kind.value, item.id))
        identifiers = [item.id for item in self._components]
        if len(identifiers) != len(set(identifiers)):
            raise VisualError("Visual component IDs must be unique")

    @classmethod
    def from_core(cls) -> VisualComponentRegistry:
        """Load the registry embedded in the installed Core package.

        Returns:
            VisualComponentRegistry: Registry from the pinned package installation.

        Raises:
            VisualError: If the packaged component manifest is invalid or unavailable.
        """
        resource = files("content_creator.resources").joinpath("visuals/components.json")
        try:
            payload = json.loads(resource.read_text(encoding="utf-8"))
            components = [VisualComponent.model_validate(item) for item in payload["components"]]
        except (KeyError, OSError, TypeError, ValueError) as exc:
            raise VisualError("Installed Core visual components could not be loaded") from exc
        return cls(components)

    def list(self) -> List[VisualComponent]:
        """Return every installed component in deterministic order.

        Returns:
            List[VisualComponent]: Immutable component records.
        """
        return list(self._components)

    def resolve(
        self,
        role: str,
        execution_class: ExecutionClass,
        output_format: str,
        aspect_ratio: str,
    ) -> List[VisualComponent]:
        """Resolve the complete compatible component set for one visual role.

        Args:
            role (str): Pack-owned visual role.
            execution_class (ExecutionClass): Requested rendering execution class.
            output_format (str): Requested output format without a leading dot.
            aspect_ratio (str): Requested positive ``WIDTH:HEIGHT`` ratio.

        Returns:
            List[VisualComponent]: Compatible components in deterministic order.

        Raises:
            VisualError: If a required component kind cannot be resolved.
        """
        compatible = [
            component
            for component in self._components
            if component.supports(role, execution_class, output_format, aspect_ratio)
        ]
        kinds = {component.kind for component in compatible}
        required = {
            VisualComponentKind.CONTRACT,
            VisualComponentKind.LAYOUT,
            VisualComponentKind.RENDERER,
            VisualComponentKind.VALIDATOR,
        }
        missing = sorted(kind.value for kind in required - kinds)
        if missing:
            message = (
                "No compatible Core visual component for {} "
                "(role={}, execution={}, format={}, ratio={})"
            )
            raise VisualError(
                message.format(
                    ", ".join(missing),
                    role,
                    execution_class.value,
                    output_format,
                    aspect_ratio,
                )
            )
        return compatible
