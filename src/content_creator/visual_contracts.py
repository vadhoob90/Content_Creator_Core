"""Provide visual contracts capabilities."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Self
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from .domain import utc_now


class VisualError(RuntimeError):
    """Report visual failures."""

    pass


class ExecutionClass(str, Enum):
    """Classify how a visual operation is executed."""

    DETERMINISTIC = "deterministic"
    GENERATIVE = "generative"


class RightsStatus(str, Enum):
    """Enumerate supported rights status values."""

    OWNED = "owned"
    LICENSED = "licensed"
    PUBLIC_DOMAIN = "public_domain"
    PERMISSION_GRANTED = "permission_granted"
    UNVERIFIED = "unverified"


class VisualApprovalStatus(str, Enum):
    """Enumerate supported visual approval status values."""

    DRAFT = "draft"
    CRITIQUED = "critiqued"
    SELECTED = "selected"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"


class DiagnosticSeverity(str, Enum):
    """Represent a diagnostic severity."""

    ERROR = "error"
    WARNING = "warning"


class BoundingBox(BaseModel):
    """Represent a bounding box."""

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)
    role: str = "content"

    @model_validator(mode="after")
    def remains_on_canvas(self) -> Self:
        """Return the remains on canvas.

        Returns:
            Self: The resulting self for remains on canvas.

        Raises:
            ValueError: If an input value violates the supported domain constraints.
        """
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("Bounding boxes must remain within the normalised canvas")
        return self


class SafeAreaProfile(BaseModel):
    """Represent a safe area profile."""

    id: str
    left: float = Field(default=0, ge=0, lt=0.5)
    top: float = Field(default=0, ge=0, lt=0.5)
    right: float = Field(default=0, ge=0, lt=0.5)
    bottom: float = Field(default=0, ge=0, lt=0.5)
    applies_to_roles: List[str] = Field(default_factory=lambda: ["text", "headline"])


class CropProfile(BaseModel):
    """Represent a crop profile."""

    id: str
    visible_area: BoundingBox
    protected_roles: List[str] = Field(default_factory=lambda: ["headline"])


class VisualRoleProfile(BaseModel):
    """Represent one pack-owned publication role for visual output."""

    aspect_ratio: str
    recommended_width: int = Field(gt=0)
    recommended_height: int = Field(gt=0)
    formats: List[str] = Field(min_length=1)
    safe_area_profiles: List[str] = Field(default_factory=list)
    crop_profiles: List[str] = Field(default_factory=list)

    @field_validator("aspect_ratio")
    @classmethod
    def validate_ratio(cls, value: str) -> str:
        """Validate a role aspect ratio.

        Args:
            value (str): Positive ``WIDTH:HEIGHT`` ratio, including decimal values.

        Returns:
            str: Validated ratio text.

        Raises:
            ValueError: If the ratio does not use positive numeric values.
        """
        if not re.fullmatch(
            r"(?:[1-9]\d*(?:\.\d+)?|0\.\d*[1-9]\d*):(?:[1-9]\d*(?:\.\d+)?|0\.\d*[1-9]\d*)", value
        ):
            raise ValueError("Aspect ratios must use positive WIDTH:HEIGHT values")
        return value


class VisualPackProfile(BaseModel):
    """Represent a visual pack profile."""

    supported: bool = False
    required: bool = False
    execution_classes: List[ExecutionClass] = Field(default_factory=list)
    aspect_ratios: List[str] = Field(default_factory=list)
    formats: List[str] = Field(default_factory=list)
    max_file_size_bytes: Optional[int] = Field(default=None, gt=0)
    safe_areas: List[SafeAreaProfile] = Field(default_factory=list)
    crop_profiles: List[CropProfile] = Field(default_factory=list)
    require_alt_text: bool = True
    require_provenance: bool = True
    destination: Optional[str] = None
    default_role: Optional[str] = None
    roles: Dict[str, VisualRoleProfile] = Field(default_factory=dict)

    @field_validator("aspect_ratios")
    @classmethod
    def validate_ratios(cls, values: List[str]) -> List[str]:
        """Validate the ratios.

        Args:
            values (List[str]): The values collection consumed while validate ratios.

        Returns:
            List[str]: The validated ratios values in their documented order.

        Raises:
            ValueError: If an input value violates the supported domain constraints.
        """
        for value in values:
            if not re.fullmatch(
                r"(?:[1-9]\d*(?:\.\d+)?|0\.\d*[1-9]\d*):(?:[1-9]\d*(?:\.\d+)?|0\.\d*[1-9]\d*)",
                value,
            ):
                raise ValueError("Aspect ratios must use positive WIDTH:HEIGHT values")
        return values

    @model_validator(mode="after")
    def validate_support(self) -> Self:
        """Validate the support.

        Returns:
            Self: The validated self for support.

        Raises:
            ValueError: If an input value violates the supported domain constraints.
        """
        if self.required and not self.supported:
            raise ValueError("A required visual profile must also be supported")
        if self.supported and not self.execution_classes:
            raise ValueError("A supported visual profile needs an execution class")
        if self.supported and not self.destination:
            raise ValueError("A supported visual profile needs a publication destination")
        if self.default_role and self.default_role not in self.roles:
            raise ValueError("The default visual role must be declared in roles")
        for role in self.roles.values():
            if role.aspect_ratio not in self.aspect_ratios:
                self.aspect_ratios.append(role.aspect_ratio)
            self.formats = list(dict.fromkeys(self.formats + role.formats))
        return self

    def role(self, role_id: Optional[str] = None) -> VisualRoleProfile:
        """Resolve one named role or the backward-compatible aggregate profile.

        Args:
            role_id (Optional[str]): Requested visual role. Defaults to ``None``.

        Returns:
            VisualRoleProfile: Resolved pack-owned output requirements.

        Raises:
            VisualError: If the requested or default role is unavailable.
        """
        selected = role_id or self.default_role
        if selected:
            try:
                return self.roles[selected]
            except KeyError as exc:
                message = (
                    "The selected content pack does not support visual role '{}' (available: {})"
                )
                raise VisualError(
                    message.format(selected, ", ".join(sorted(self.roles)) or "none")
                ) from exc
        if self.roles:
            raise VisualError("The selected content pack has no default visual role")
        if not self.aspect_ratios or not self.formats:
            raise VisualError("The selected content pack has no usable visual output profile")
        width, height = _recommended_dimensions(self.aspect_ratios[0])
        return VisualRoleProfile(
            aspect_ratio=self.aspect_ratios[0],
            recommended_width=width,
            recommended_height=height,
            formats=self.formats,
            safe_area_profiles=[item.id for item in self.safe_areas],
            crop_profiles=[item.id for item in self.crop_profiles],
        )


def _recommended_dimensions(ratio: str) -> tuple[int, int]:
    """Return bounded fallback dimensions derived from a ratio.

    Args:
        ratio (str): Positive ``WIDTH:HEIGHT`` ratio.

    Returns:
        tuple[int, int]: Width and height suitable for a legacy aggregate profile.
    """
    width, height = (float(part) for part in ratio.split(":"))
    scale = 1200 / width
    return 1200, max(1, round(height * scale))


class VisualSource(BaseModel):
    """Enumerate supported visual source values."""

    source_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    uri: str
    role: str = "reference"
    creator: Optional[str] = None
    attribution: Optional[str] = None
    rights_status: RightsStatus = RightsStatus.UNVERIFIED
    licence: Optional[str] = None


class VisualComponentRef(BaseModel):
    """Represent one immutable reusable visual component reference."""

    id: str
    version: str
    kind: str
    provenance: str


class VisualLockedAssetRef(BaseModel):
    """Represent an exact workspace-owned brand asset pinned by immutable hash."""

    id: str
    path: str
    role: str = "brand-mark"
    sha256: str
    mime_type: str


class VisualBrief(BaseModel):
    """Represent a visual brief."""

    schema_version: str = "1.0"
    run_id: str
    objective: str
    content_connection: str
    exact_copy: List[str] = Field(default_factory=list)
    platform_profile: str
    role: Optional[str] = None
    aspect_ratios: List[str] = Field(min_length=1)
    output_formats: List[str] = Field(min_length=1)
    output_width: Optional[int] = Field(default=None, gt=0)
    output_height: Optional[int] = Field(default=None, gt=0)
    safe_area_profiles: List[str] = Field(default_factory=list)
    crop_profiles: List[str] = Field(default_factory=list)
    hierarchy: List[str] = Field(default_factory=list)
    layout_constraints: List[str] = Field(default_factory=list)
    revision_invariants: List[str] = Field(default_factory=list)
    sources: List[VisualSource] = Field(default_factory=list)
    alt_text: str
    brand_tokens: Dict[str, str] = Field(default_factory=dict)
    locked_assets: List[VisualLockedAssetRef] = Field(default_factory=list)
    visual_preferences: List[str] = Field(default_factory=list)
    components: List[VisualComponentRef] = Field(default_factory=list)
    preferred_execution_class: Optional[ExecutionClass] = None
    preferred_adapter: Optional[str] = None
    author_approval: VisualApprovalStatus = VisualApprovalStatus.DRAFT
    created_at: str = Field(default_factory=lambda: utc_now().isoformat())

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        """Validate the run id.

        Args:
            value (str): The value to process.

        Returns:
            str: The validated text for run id.

        Raises:
            ValueError: If an input value violates the supported domain constraints.
        """
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("Invalid run id")
        return value


class VisualOutput(BaseModel):
    """Represent a visual output."""

    content: bytes
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    format: str
    extracted_copy: Optional[List[str]] = None
    content_boxes: List[BoundingBox] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VisualDiagnostic(BaseModel):
    """Represent a visual diagnostic."""

    code: str
    severity: DiagnosticSeverity
    message: str
    profile: Optional[str] = None


class VisualValidation(BaseModel):
    """Represent a visual validation."""

    passed: bool
    diagnostics: List[VisualDiagnostic] = Field(default_factory=list)
    validated_at: str = Field(default_factory=lambda: utc_now().isoformat())


class VisualCritique(BaseModel):
    """Represent a visual critique."""

    summary: str
    strengths: List[str] = Field(default_factory=list)
    issues: List[str] = Field(default_factory=list)
    reviewer: str = "visual-critic"
    created_at: str = Field(default_factory=lambda: utc_now().isoformat())


class VisualDecision(BaseModel):
    """Record the selected asset and author-governed approval state."""

    schema_version: str = "1.0"
    run_id: str
    selected_asset_id: str
    decision: str
    approval_state: VisualApprovalStatus
    decided_at: str = Field(default_factory=lambda: utc_now().isoformat())


class VisualAsset(BaseModel):
    """Represent a visual asset."""

    asset_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    parent_asset_id: Optional[str] = None
    revision: int = Field(default=1, ge=1)
    variant_name: Optional[str] = None
    role: Optional[str] = None
    execution_class: ExecutionClass
    adapter: str
    provider: Optional[str] = None
    model_or_renderer: str
    prompt_or_template_version: Optional[str] = None
    source_ids: List[str] = Field(default_factory=list)
    sources: List[VisualSource] = Field(default_factory=list)
    alt_text: str
    relative_path: str
    sha256: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    format: str
    size_bytes: int = Field(ge=0)
    extracted_copy: Optional[List[str]] = None
    content_boxes: List[BoundingBox] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    components: List[VisualComponentRef] = Field(default_factory=list)
    validation: Optional[VisualValidation] = None
    critique: Optional[VisualCritique] = None
    status: VisualApprovalStatus = VisualApprovalStatus.DRAFT
    created_at: str = Field(default_factory=lambda: utc_now().isoformat())


class VisualManifest(BaseModel):
    """Represent a visual manifest."""

    schema_version: str = "1.0"
    run_id: str
    assets: List[VisualAsset] = Field(default_factory=list)
    components: List[VisualComponentRef] = Field(default_factory=list)
    selected_asset_id: Optional[str] = None
    published_path: Optional[str] = None
    updated_at: str = Field(default_factory=lambda: utc_now().isoformat())


class VisualAdapter(ABC):
    """Represent a visual adapter."""

    name: str
    execution_class: ExecutionClass
    model_or_renderer: str
    prompt_or_template_version: Optional[str] = None

    @abstractmethod
    def render(self, brief: VisualBrief, parent: Optional[VisualAsset] = None) -> VisualOutput:
        """Produce one visual without assuming a particular provider.

        Args:
            brief (VisualBrief): The research or content brief that defines the requested
                work.
            parent (Optional[VisualAsset]): The parent value passed to render. Defaults to
                ``None``.

        Returns:
            VisualOutput: The rendered visual output for value.
        """


class VisualAdapterRegistry:
    """Manage visual adapter records."""

    def __init__(self) -> None:
        """Initialize the visual adapter registry.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        self._adapters: Dict[str, VisualAdapter] = {}

    def register(self, adapter: VisualAdapter) -> None:
        """Register the visual adapter registry workflow.

        Args:
            adapter (VisualAdapter): The adapter value passed to register.

        Returns:
            None: The callable updates register state and returns no value.

        Raises:
            VisualError: If the visual operation cannot complete.
        """
        if not adapter.name:
            raise VisualError("Visual adapters need a stable name")
        self._adapters[adapter.name] = adapter

    def get(self, name: str) -> VisualAdapter:
        """Return the visual adapter registry.

        Args:
            name (str): The stable or human-readable name for the domain object.

        Returns:
            VisualAdapter: The resulting visual adapter for get.

        Raises:
            VisualError: If the visual operation cannot complete.
        """
        try:
            return self._adapters[name]
        except KeyError as exc:
            raise VisualError("Unknown visual adapter: {}".format(name)) from exc

    def route(self, brief: VisualBrief) -> VisualAdapter:
        """Return the route.

        Args:
            brief (VisualBrief): The research or content brief that defines the requested
                work.

        Returns:
            VisualAdapter: The resulting visual adapter for route.

        Raises:
            VisualError: If the visual operation cannot complete.
        """
        if brief.preferred_adapter:
            return self.get(brief.preferred_adapter)
        candidates = list(self._adapters.values())
        if brief.preferred_execution_class:
            candidates = [
                item
                for item in candidates
                if item.execution_class == brief.preferred_execution_class
            ]
        if not candidates:
            raise VisualError("No adapter supports the requested visual execution class")
        return sorted(candidates, key=lambda item: item.name)[0]
