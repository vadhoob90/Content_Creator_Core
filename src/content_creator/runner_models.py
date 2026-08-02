"""Value objects shared across the agent-runner boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Type

from pydantic import BaseModel

from .domain import WorkOrder


@dataclass(frozen=True)
class AgentRunOptions:
    """Optional model, provider, and tool requirements for one agent call."""

    order: Optional[WorkOrder] = None
    output_model: Optional[Type[BaseModel]] = None
    provider: Optional[str] = None
    profile: Optional[str] = None
    tools: list[str] = field(default_factory=list)
