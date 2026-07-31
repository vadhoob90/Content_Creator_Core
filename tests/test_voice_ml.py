import json

from content_creator.cli import main
from content_creator.linguistics import build_linguistic_signature
from content_creator.voice_assessment import assess_voice_draft
from content_creator.voice_ml import (
    assess_with_ml_artifact,
    ml_model_path,
    train_voice_ml_model,
    training_reliability,
)
from content_creator.voices import hash_file


def _author_text(index, repeats=22):
    markers = [
        "alpha",
        "bravo",
        "charlie",
        "delta",
        "echo",
        "foxtrot",
        "golf",
        "hotel",
        "india",
        "juliet",
    ]
    marker = markers[index % len(markers)]
    return (
        "I examine the context carefully because judgment matters. "
        "However, the useful conclusion remains measured and practical. "
        "The {} example keeps the reasoning visible. ".format(marker)
    ) * repeats


def _comparison_text(index, repeats=22):
    markers = [
        "kilo",
        "lima",
        "mango",
        "november",
        "oscar",
        "papa",
        "quebec",
        "romeo",
        "sierra",
        "tango",
        "uniform",
        "victor",
        "whiskey",
        "xray",
        "yankee",
        "zulu",
        "amber",
        "birch",
        "cedar",
        "drift",
        "ember",
        "flint",
        "grove",
        "harbor",
        "island",
        "jungle",
        "kernel",
        "lantern",
        "meadow",
        "nectar",
        "orbit",
        "pebble",
        "quartz",
        "ridge",
        "summit",
        "timber",
        "upland",
        "valley",
        "willow",
        "zenith",
    ]
    marker = markers[index % len(markers)]
    distinctive_sequence = " ".join([marker] * 12)
    return (
        "You must act now! Why wait? The {} result is absolutely essential. "
        "You should always move quickly! This is definitely obvious. ".format(
            distinctive_sequence
        )
    ) * repeats


def _install_voice(project, count):
    signature = build_linguistic_signature(
        [
            {
                "id": "author-{:03d}".format(index),
                "kind": "text",
                "weight": 1.0,
                "text": _author_text(index),
            }
            for index in range(count)
        ]
    )
    version = project / "profiles" / "alice" / "versions" / "1.0.0"
    version.mkdir(parents=True)
    (version / "profile.md").write_text("# Alice voice", encoding="utf-8")
    (version / "source-index.json").write_text("[]", encoding="utf-8")
    (version / "linguistic-signature.json").write_text(
        json.dumps(signature), encoding="utf-8"
    )
    components = {
        "profile": "profile.md",
        "sources": "source-index.json",
        "linguistic_signature": "linguistic-signature.json",
    }
    (version / "manifest.json").write_text(
        json.dumps(
            {
                "id": "alice",
                "display_name": "Alice",
                "version": "1.0.0",
                "status": "active",
                "candidate_hash": "sha256:fixture",
                "components": components,
                "component_hashes": {
                    name: hash_file(version / filename)
                    for name, filename in components.items()
                },
                "supported_packs": {"linkedin-article": "high"},
                "authorisation": {"confirmed": True},
            }
        ),
        encoding="utf-8",
    )
    (project / "profiles" / "registry.json").write_text(
        json.dumps(
            {
                "profiles": {
                    "alice": {
                        "status": "active",
                        "active_version": "1.0.0",
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def _comparison_files(project, count):
    directory = project / "comparison"
    directory.mkdir()
    paths = []
    for index in range(count):
        path = directory / "comparison-{:03d}.md".format(index)
        path.write_text(_comparison_text(index), encoding="utf-8")
        paths.append(path)
    return paths


def test_reliability_distinguishes_refusal_warning_and_reliable_training():
    refused = training_reliability(9, 6000, 9, 6000)
    warned = training_reliability(20, 10000, 20, 10000)
    reliable = training_reliability(40, 20000, 40, 20000)

    assert refused["status"] == "insufficient_data"
    assert refused["can_train"] is False
    assert warned["status"] == "low_confidence"
    assert warned["requires_low_confidence_acceptance"] is True
    assert reliable["status"] == "reliable"


def test_cli_warns_and_does_not_train_low_confidence_model(project, capsys):
    _install_voice(project, 12)
    comparison = _comparison_files(project, 12)

    result = main(
        [
            "--workspace",
            str(project),
            "voice",
            "train-ml",
            "alice",
            "--comparison-documents",
            str(comparison[0].parent),
        ]
    )
    report = json.loads(capsys.readouterr().out)

    assert result == 5
    assert report["status"] == "warning_confirmation_required"
    assert report["trained"] is False
    assert report["preflight"]["reliability"]["warnings"]
    assert not ml_model_path(project, "alice", "1.0.0").exists()

    accepted = main(
        [
            "--workspace",
            str(project),
            "voice",
            "train-ml",
            "alice",
            "--comparison-documents",
            str(comparison[0].parent),
            "--accept-low-confidence",
        ]
    )
    accepted_report = json.loads(capsys.readouterr().out)

    assert accepted == 0
    assert accepted_report["status"] == "trained"
    assert accepted_report["preflight"]["reliability"]["status"] == "low_confidence"
    assert ml_model_path(project, "alice", "1.0.0").exists()


def test_reliable_model_trains_to_json_and_infers_without_pickle(project):
    _install_voice(project, 40)
    comparison = _comparison_files(project, 40)

    result = train_voice_ml_model(project, "alice", None, comparison)
    artifact_path = ml_model_path(project, "alice", "1.0.0")
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    author_report = assess_with_ml_artifact(
        project, "alice", "1.0.0", _author_text(1), 100
    )
    comparison_report = assess_with_ml_artifact(
        project, "alice", "1.0.0", _comparison_text(1), 100
    )
    configured_report = assess_voice_draft(
        project,
        "alice",
        "1.0.0",
        _author_text(2),
        {
            "mode": "ml",
            "minimum_draft_words": 100,
            "minimum_sources": 20,
            "outlier_iqr_multiplier": 1.5,
            "max_reported_outliers": 8,
        },
    )

    assert result["status"] == "trained"
    assert artifact["classifier"]["type"] == "logistic-regression"
    assert "pickle" not in artifact
    assert author_report["model_score"] > comparison_report["model_score"]
    assert author_report["claim_limit"].startswith("The classifier score")
    assert configured_report["framework"] == artifact["framework"]
