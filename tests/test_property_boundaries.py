from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from content_creator.attribution import classify_attribution, isolate_attributed_text
from content_creator.publication_provenance import (
    PublicationProvenance,
    PublicationProvenanceError,
)

safe_text = st.text(
    alphabet=st.characters(categories=("L", "N", "Zs"), exclude_characters="\n\r"),
    min_size=1,
    max_size=120,
).filter(lambda value: bool(value.strip()))
path_component = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")),
    min_size=1,
    max_size=20,
)


@given(author=safe_text, body=safe_text)
def test_byline_attribution_is_stable_for_generated_unicode(author, body):
    author = author.strip()
    source = f"By {author}. {body}"

    attribution = classify_attribution(source, author, "text")
    isolated, scope = isolate_attributed_text(source, author, attribution, "text")

    assert attribution.classification == "directly_authored"
    assert attribution.voice_weight == 1.0
    assert scope == "full-source-with-byline-removed"
    assert isolated == body.strip()


@given(
    text=st.text(max_size=500),
    author=safe_text,
    kind=st.sampled_from(["text", "webpage", "transcript"]),
)
def test_attribution_never_grants_weight_without_a_supported_classification(text, author, kind):
    attribution = classify_attribution(text, author, kind)

    assert 0.0 <= attribution.voice_weight <= 1.0
    if attribution.voice_weight == 0:
        assert attribution.needs_human_review
    else:
        assert attribution.classification in {"directly_authored", "co_authored", "interview"}


@given(parts=st.lists(path_component, min_size=1, max_size=5))
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_publication_paths_resolve_inside_the_workspace(project, parts):
    service = PublicationProvenance(
        project,
        {"policy": "advisory", "receipts_directory": "publication-receipts"},
    )

    resolved = service._within_root("/".join(parts))

    assert resolved.is_relative_to(project.resolve())


@given(depth=st.integers(min_value=1, max_value=8), leaf=path_component)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_publication_path_traversal_always_fails_closed(project, depth, leaf):
    service = PublicationProvenance(
        project,
        {"policy": "advisory", "receipts_directory": "publication-receipts"},
    )
    traversal = Path(*([".."] * depth), leaf)

    with pytest.raises(PublicationProvenanceError, match="leaves workspace"):
        service._within_root(str(traversal))
