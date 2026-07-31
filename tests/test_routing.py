import pytest

from content_creator.domain import WorkOrder
from content_creator.routing import RoutingError, build_route


@pytest.mark.parametrize(
    "format_,depth,source,checkpoint",
    [
        ("post", "none", "none", False),
        ("article", "none", "none", False),
        ("post", "light", "agent", False),
        ("article", "light", "agent", False),
        ("post", "deep", "agent", True),
        ("article", "deep", "agent", True),
        ("post", "light", "supplied", False),
        ("article", "deep", "supplied", False),
    ],
)
def test_valid_routes(format_, depth, source, checkpoint):
    order = WorkOrder(
        request="x",
        topic="x",
        format=format_,
        research_depth=depth,
        research_source=source,
        supplied_research_path="brief.json" if source == "supplied" else None,
    )
    route = build_route(order)
    assert route.route == "{}-{}-{}".format(format_, depth, source)
    assert route.requires_research_checkpoint is checkpoint


@pytest.mark.parametrize(
    "depth,source",
    [("none", "agent"), ("light", "none"), ("deep", "none")],
)
def test_invalid_research_combinations(depth, source):
    with pytest.raises(RoutingError):
        build_route(
            WorkOrder(
                request="x",
                topic="x",
                research_depth=depth,
                research_source=source,
            )
        )


def test_supplied_research_requires_file():
    with pytest.raises(RoutingError):
        build_route(
            WorkOrder(
                request="x",
                topic="x",
                research_depth="light",
                research_source="supplied",
            )
        )


def test_model_complexity_follows_route_not_length_alone():
    simple_article = build_route(WorkOrder(request="x", topic="x", format="article"))
    deep_article = build_route(
        WorkOrder(
            request="x",
            topic="x",
            format="article",
            research_depth="deep",
            research_source="agent",
        )
    )
    assert simple_article.model_profiles["writer"] == "balanced"
    assert simple_article.model_profiles["critic"] == "balanced"
    assert deep_article.model_profiles["writer"] == "deep"
    assert deep_article.model_profiles["critic"] == "deep"
