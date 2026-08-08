"""Provide runner models contracts and behavior."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Type

from pydantic import BaseModel

from .domain import WorkOrder


@dataclass(frozen=True)
class AgentRunOptions:
    """Represent the agent run options contract."""

    order: Optional[WorkOrder] = None
    output_model: Optional[Type[BaseModel]] = None
    provider: Optional[str] = None
    profile: Optional[str] = None
    tools: list[str] = field(default_factory=list)
    phase: Optional[str] = None
    payload_sources: list[str] = field(default_factory=list)
    run_id: Optional[str] = None
