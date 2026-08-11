"""Provide init contracts and behavior."""

from .domain import WorkOrder
from .orchestrator import Orchestrator
from .version import VERSION
from .visual_components import VisualComponent, VisualComponentRegistry
from .visual_rendering import EditorialSvgRenderer
from .visual_requests import VisualRenderRequest, VisualRequestWorkflow
from .visuals import VisualAdapter, VisualBrief, VisualWorkflow

__version__ = VERSION

__all__ = [
    "Orchestrator",
    "VERSION",
    "VisualAdapter",
    "VisualBrief",
    "VisualComponent",
    "VisualComponentRegistry",
    "VisualRequestWorkflow",
    "VisualRenderRequest",
    "EditorialSvgRenderer",
    "VisualWorkflow",
    "WorkOrder",
    "__version__",
]
