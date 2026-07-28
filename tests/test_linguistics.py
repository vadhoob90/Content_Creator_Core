import pytest

from content_creator.linguistics import (
    build_linguistic_signature,
    extract_linguistic_features,
)


def test_feature_extraction_captures_rhythm_stance_and_structure():
    text = (
        "I think this matters.\n\n"
        "You can test the claim, but you should keep the boundary visible. "
        "Why? Because clear reasoning is useful—and it isn't the same as certainty."
    )

    features = extract_linguistic_features(text)

    assert features["word_count"] > 20
    assert features["paragraph_count"] == 2
    assert features["sentence_count"] == 4
    assert features["sentence_length_variation"] > 0
    assert features["first_person_per_1000_words"] > 0
    assert features["second_person_per_1000_words"] > 0
    assert features["questions_per_100_sentences"] == 25
    assert features["contrast_markers_per_1000_words"] > 0
    assert features["contractions_per_1000_words"] > 0


def test_signature_uses_attribution_weights_and_separates_registers():
    signature = build_linguistic_signature(
        [
            {
                "id": "written-1",
                "kind": "text",
                "weight": 1.0,
                "text": "This is a deliberately measured written sentence. " * 20,
            },
            {
                "id": "spoken-1",
                "kind": "transcript",
                "weight": 0.5,
                "text": "Short. Spoken. Direct. " * 20,
            },
        ]
    )

    assert set(signature["by_mode"]) == {"spoken", "written"}
    assert signature["source_profiles"][1]["weight"] == 0.5
    assert signature["reference_comparison"]["status"] == "not_supplied"
    assert any("Spoken and written" in item for item in signature["cautions"])
    overall = signature["overall"]["sentence_length_median"]
    assert overall["weighted_mean"] > overall["median"]


def test_empty_signature_is_explicitly_limited():
    signature = build_linguistic_signature([])

    assert signature["overall"] == {}
    assert signature["source_profiles"] == []
    assert signature["reference_comparison"]["status"] == "not_supplied"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("One sentence.", 1),
        ("One sentence. Another sentence!", 2),
    ],
)
def test_sentence_count_is_deterministic(text, expected):
    assert extract_linguistic_features(text)["sentence_count"] == expected
