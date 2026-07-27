"""Deterministic capability routing.

The orchestrator chooses a capability tier. Provider-specific model names are
resolved only at the adapter boundary.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Route:
    provider: str
    adapter: str
    tier: str
    model_reference: str


def load_catalog(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def select_route(catalog: dict, provider: str, complexity: str) -> Route:
    try:
        tier = catalog["complexity_to_tier"][complexity]
    except KeyError as exc:
        raise ValueError(f"Unknown complexity: {complexity}") from exc

    try:
        provider_config = catalog["providers"][provider]
    except KeyError as exc:
        raise ValueError(f"Unknown provider: {provider}") from exc

    return Route(
        provider=provider,
        adapter=provider_config["adapter"],
        tier=tier,
        model_reference=provider_config["models"][tier],
    )
