from pathlib import Path

import pytest

from content_creator.routing import load_catalog, select_route


ROOT = Path(__file__).resolve().parents[1]
CATALOG = load_catalog(ROOT / "config" / "providers.json")


@pytest.mark.parametrize(
    ("complexity", "tier"),
    [("simple", "fast"), ("standard", "balanced"), ("deep", "deep")],
)
def test_complexity_maps_to_provider_neutral_tier(complexity, tier):
    route = select_route(CATALOG, "openai", complexity)

    assert route.tier == tier


@pytest.mark.parametrize("provider", ["openai", "anthropic", "custom"])
def test_all_declared_provider_routes_resolve(provider):
    route = select_route(CATALOG, provider, "standard")

    assert route.provider == provider
    assert route.model_reference.startswith("${")


def test_unknown_provider_fails_clearly():
    with pytest.raises(ValueError, match="Unknown provider"):
        select_route(CATALOG, "missing", "simple")
