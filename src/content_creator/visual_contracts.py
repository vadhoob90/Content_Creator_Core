from __future__ import annotations

import re
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Self
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from .domain import utc_now


class VisualError(RuntimeError):
    pass


class ExecutionClass(str, Enum):
    DETERMINISTIC = "deterministic"
    GENERATIVE = "generative"


class RightsStatus(str, Enum):
    OWNED = "owned"
    LICENSED = "licensed"
    PUBLIC_DOMAIN = "public_domain"
    PERMISSION_GRANTED = "permission_granted"
    UNVERIFIED = "unverified"


class VisualApprovalStatus(str, Enum):
    DRAFT = "draft"
    CRITIQUED = "critiqued"
    SELECTED = "selected"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"


class DiagnosticSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class BoundingBox(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)
    role: str = "content"

    @model_validator(mode="after")
    def remains_on_canvas(self) -> Self:
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("Bounding boxes must remain within the normalised canvas")
        return self


class SafeAreaProfile(BaseModel):
    id: str
    left: float = Field(default=0, ge=0, lt=0.5)
    top: float = Field(default=0, ge=0, lt=0.5)
    right: float = Field(default=0, ge=0, lt=0.5)
    bottom: float = Field(default=0, ge=0, lt=0.5)
    applies_to_roles: List[str] = Field(default_factory=lambda: ["text", "headline"])


class CropProfile(BaseModel):
    id: str
    visible_area: BoundingBox
    protected_roles: List[str] = Field(default_factory=lambda: ["headline"])


class VisualPackProfile(BaseModel):
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

    @field_validator("aspect_ratios")
    @classmethod
    def validate_ratios(cls, values: List[str]) -> List[str]:
        for value in values:
            if not re.fullmatch(r"[1-9]\d*:[1-9]\d*", value):
                raise ValueError("Aspect ratios must use positive WIDTH:HEIGHT values")
        return values

    @model_validator(mode="after")
    def validate_support(self) -> Self:
        if self.required and not self.supported:
            raise ValueError("A required visual profile must also be supported")
        if self.supported and not self.execution_classes:
            raise ValueError("A supported visual profile needs an execution class")
        if self.supported and not self.destination:
            raise ValueError("A supported visual profile needs a publication destination")
        return self


class VisualSource(BaseModel):
    source_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    uri: str
    role: str = "reference"
    creator: Optional[str] = None
    attribution: Optional[str] = None
    rights_status: RightsStatus = RightsStatus.UNVERIFIED
    licence: Optional[str] = None


class VisualBrief(BaseModel):
    schema_version: str = "1.0"
    run_id: str
    objective: str
    content_connection: str
    exact_copy: List[str] = Field(default_factory=list)
    platform_profile: str
    aspect_ratios: List[str] = Field(min_length=1)
    output_formats: List[str] = Field(min_length=1)
    safe_area_profiles: List[str] = Field(default_factory=list)
    crop_profiles: List[str] = Field(default_factory=list)
    hierarchy: List[str] = Field(default_factory=list)
    layout_constraints: List[str] = Field(default_factory=list)
    revision_invariants: List[str] = Field(default_factory=list)
    sources: List[VisualSource] = Field(default_factory=list)
    alt_text: str
    preferred_execution_class: Optional[ExecutionClass] = None
    preferred_adapter: Optional[str] = None
    author_approval: VisualApprovalStatus = VisualApprovalStatus.DRAFT
    created_at: str = Field(default_factory=lambda: utc_now().isoformat())

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("Invalid run id")
        return value


class VisualOutput(BaseModel):
    content: bytes
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    format: str
    extracted_copy: Optional[List[str]] = None
    content_boxes: List[BoundingBox] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VisualDiagnostic(BaseModel):
    code: str
    severity: DiagnosticSeverity
    message: str
    profile: Optional[str] = None


class VisualValidation(BaseModel):
    passed: bool
    diagnostics: List[VisualDiagnostic] = Field(default_factory=list)
    validated_at: str = Field(default_factory=lambda: utc_now().isoformat())


class VisualCritique(BaseModel):
    summary: str
    strengths: List[str] = Field(default_factory=list)
    issues: List[str] = Field(default_factory=list)
    reviewer: str = "visual-critic"
    created_at: str = Field(default_factory=lambda: utc_now().isoformat())


class VisualAsset(BaseModel):
    asset_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    parent_asset_id: Optional[str] = None
    revision: int = Field(default=1, ge=1)
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
    validation: Optional[VisualValidation] = None
    critique: Optional[VisualCritique] = None
    status: VisualApprovalStatus = VisualApprovalStatus.DRAFT
    created_at: str = Field(default_factory=lambda: utc_now().isoformat())


class VisualManifest(BaseModel):
    schema_version: str = "1.0"
    run_id: str
    assets: List[VisualAsset] = Field(default_factory=list)
    selected_asset_id: Optional[str] = None
    published_path: Optional[str] = None
    updated_at: str = Field(default_factory=lambda: utc_now().isoformat())


class VisualAdapter(ABC):
    name: str
    execution_class: ExecutionClass
    model_or_renderer: str
    prompt_or_template_version: Optional[str] = None

    @abstractmethod
    def render(self, brief: VisualBrief, parent: Optional[VisualAsset] = None) -> VisualOutput:
        """Produce one visual without assuming a particular provider."""


class VisualAdapterRegistry:
    def __init__(self) -> None:
        self._adapters: Dict[str, VisualAdapter] = {}

    def register(self, adapter: VisualAdapter) -> None:
        if not adapter.name:
            raise VisualError("Visual adapters need a stable name")
        self._adapters[adapter.name] = adapter

    def get(self, name: str) -> VisualAdapter:
        try:
            return self._adapters[name]
        except KeyError as exc:
            raise VisualError("Unknown visual adapter: {}".format(name)) from exc

    def route(self, brief: VisualBrief) -> VisualAdapter:
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
