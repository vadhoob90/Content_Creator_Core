import json

import pytest

from content_creator.cli import main
from content_creator.versioned_artifacts import hash_file, hash_json
from content_creator.voice_build.models import VoiceBuildError
from content_creator.voice_models import VoiceManifest


def _source(path, phrase):
    path.write_text(
        (phrase + " The explanation makes the decision visible to the reader. ") * 35,
        encoding="utf-8",
    )
    return path


def _refresh_candidate_manifest(candidate):
    manifest_path = candidate / "manifest.json"
    manifest = VoiceManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    manifest.component_hashes = {
        name: hash_file(candidate / filename) for name, filename in manifest.components.items()
    }
    manifest.candidate_hash = hash_json(manifest.component_hashes)
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")


def _activate_curated_voice(project, capsys):
    material = project / "voice-material"
    material.mkdir()
    _source(material / "one.md", "By Example Person. Start from a concrete problem.")
    _source(material / "two.md", "By Example Person. End with a bounded practical choice.")
    assert (
        main(
            [
                "--root",
                str(project),
                "voice",
                "create",
                "--name",
                "Example Person",
                "--authorised-by",
                "Owner",
                "--documents",
                str(material),
                "--offline-analysis",
            ]
        )
        == 0
    )
    capsys.readouterr()
    candidate = project / "profiles" / "example-person" / "candidate"
    profile = (candidate / "profile.md").read_text(encoding="utf-8")
    (candidate / "profile.md").write_text(
        profile
        + "\n## Author-approved opening rule\n\nOpen with a concrete tension, never a slogan.\n",
        encoding="utf-8",
    )
    constraints = json.loads((candidate / "constraints.json").read_text(encoding="utf-8"))
    constraints["author_approved"] = {
        "opening": "Open with a concrete tension, never a slogan.",
        "ending": "End with a bounded practical choice.",
    }
    (candidate / "constraints.json").write_text(json.dumps(constraints, indent=2), encoding="utf-8")
    patterns = json.loads((candidate / "patterns.json").read_text(encoding="utf-8"))
    patterns.append(
        {
            "id": "curated-opening",
            "name": "Concrete tension opening",
            "description": "Begin with a concrete tension rather than a slogan.",
            "status": "confirmed",
            "confidence": 1.0,
            "supporting_source_ids": ["source-001"],
            "mandatory": True,
            "category": "openings",
            "generation_guidance": "Open with a concrete tension.",
            "anti_pattern": "Do not open with a generic slogan.",
        }
    )
    (candidate / "patterns.json").write_text(json.dumps(patterns, indent=2), encoding="utf-8")
    _refresh_candidate_manifest(candidate)
    assert main(["--root", str(project), "voice", "approve", "example-person"]) == 0
    capsys.readouterr()
    return project / "profiles" / "example-person" / "versions" / "1.0.0"


def _add_new_evidence(project, capsys):
    article = _source(
        project / "new-article.md",
        "By Example Person. New evidence supports a more precise transition.",
    )
    assert (
        main(
            [
                "--root",
                str(project),
                "voice",
                "add-sources",
                "example-person",
                "--documents",
                str(article),
            ]
        )
        == 0
    )
    capsys.readouterr()


def _rebuild(project, *extra):
    return main(
        [
            "--root",
            str(project),
            "voice",
            "rebuild",
            "example-person",
            "--offline-analysis",
            *extra,
        ]
    )


def _evolution_change_set(project):
    change_set = project / "voice-change-set.json"
    change_set.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "changes": [
                    {
                        "action": "supersede",
                        "target_id": "curated-opening",
                        "replacement": {
                            "id": "evolved-opening",
                            "name": "Precise tension opening",
                            "description": "Begin with a precise evidence-backed tension.",
                            "status": "for-review",
                            "confidence": 0.9,
                            "supporting_source_ids": ["source-003"],
                            "mandatory": True,
                            "category": "openings",
                            "generation_guidance": "Open with a precise tension.",
                            "anti_pattern": "Do not overstate the opening claim.",
                        },
                        "evidence_source_ids": ["source-003"],
                        "confidence": 0.9,
                        "rationale": "The new article evidences a narrower opening rule.",
                    },
                    {
                        "action": "add",
                        "replacement": {
                            "id": "evidence-transition",
                            "name": "Evidence-led transition",
                            "description": "Make the evidence-to-decision transition explicit.",
                            "status": "for-review",
                            "confidence": 0.85,
                            "supporting_source_ids": ["source-003"],
                            "mandatory": False,
                            "category": "transitions",
                            "generation_guidance": "Connect evidence to the bounded decision.",
                            "anti_pattern": "Do not jump from evidence to an unsupported claim.",
                        },
                        "evidence_source_ids": ["source-003"],
                        "confidence": 0.85,
                        "rationale": "The new article supplies an additional transition pattern.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return change_set


def test_active_guidance_is_preserved_and_diffed_by_default(project, capsys):
    active = _activate_curated_voice(project, capsys)
    active_profile = (active / "profile.md").read_text(encoding="utf-8")
    active_constraints = json.loads((active / "constraints.json").read_text(encoding="utf-8"))
    active_manifest = VoiceManifest.model_validate_json(
        (active / "manifest.json").read_text(encoding="utf-8")
    )
    _add_new_evidence(project, capsys)

    assert _rebuild(project) == 0
    capsys.readouterr()
    candidate = project / "profiles" / "example-person" / "candidate"
    manifest = VoiceManifest.model_validate_json(
        (candidate / "manifest.json").read_text(encoding="utf-8")
    )
    delta = json.loads((candidate / "voice-evolution.json").read_text(encoding="utf-8"))
    evaluation = json.loads((candidate / "evaluation-report.json").read_text(encoding="utf-8"))
    patterns = json.loads((candidate / "patterns.json").read_text(encoding="utf-8"))

    assert manifest.evolution_mode == "evolve"
    assert manifest.baseline_version == "1.0.0"
    assert manifest.baseline_candidate_hash == active_manifest.candidate_hash
    assert (candidate / "profile.md").read_text(
        encoding="utf-8"
    ).rstrip() == active_profile.rstrip()
    assert json.loads((candidate / "constraints.json").read_text()) == active_constraints
    assert "curated-opening" in {item["id"] for item in patterns}
    assert {item["guidance_id"] for item in delta["retained"]} >= {
        "curated-opening",
        "artifact:profile.md",
        "artifact:constraints.json",
        "artifact:voice-rubric.json",
    }
    assert evaluation["regression_evaluation"]["passed"] is True
    assert (active / "profile.md").read_text(encoding="utf-8") == active_profile

    assert main(["--root", str(project), "voice", "diff", "example-person"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert set(report["semantic_delta"]) >= {
        "retained",
        "added",
        "modified",
        "superseded",
        "removed",
    }


def test_evolution_supersession_is_evidenced_deterministic_and_approved(project, capsys):
    _activate_curated_voice(project, capsys)
    _add_new_evidence(project, capsys)
    change_set = _evolution_change_set(project)

    assert _rebuild(project, "--change-set", str(change_set)) == 0
    capsys.readouterr()
    candidate = project / "profiles" / "example-person" / "candidate"
    first_manifest = (candidate / "manifest.json").read_text(encoding="utf-8")
    first_delta = (candidate / "voice-evolution.json").read_text(encoding="utf-8")
    patterns = json.loads((candidate / "patterns.json").read_text(encoding="utf-8"))
    ids = {item["id"] for item in patterns}
    delta = json.loads(first_delta)

    assert "curated-opening" not in ids
    assert "evolved-opening" in ids
    assert "evidence-transition" in ids
    assert {item["guidance_id"] for item in delta["added"]} >= {"evidence-transition"}
    assert delta["superseded"] == [
        {
            "guidance_id": "curated-opening",
            "replacement_id": "evolved-opening",
            "provenance": ["source:source-003"],
            "confidence": 0.9,
            "rationale": "The new article evidences a narrower opening rule.",
        }
    ]
    assert _rebuild(project, "--change-set", str(change_set)) == 0
    capsys.readouterr()
    assert (candidate / "manifest.json").read_text(encoding="utf-8") == first_manifest
    assert (candidate / "voice-evolution.json").read_text(encoding="utf-8") == first_delta

    assert main(["--root", str(project), "voice", "approve", "example-person"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["activated_version"] == "2.0.0"
    activated = VoiceManifest.model_validate_json(
        (
            project / "profiles" / "example-person" / "versions" / "2.0.0" / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert activated.baseline_version == "1.0.0"


def test_failed_evolution_preserves_active_and_previous_candidate(project, capsys):
    active = _activate_curated_voice(project, capsys)
    _add_new_evidence(project, capsys)
    assert _rebuild(project) == 0
    capsys.readouterr()
    candidate = project / "profiles" / "example-person" / "candidate"
    candidate_before = (candidate / "manifest.json").read_text(encoding="utf-8")
    active_before = (active / "profile.md").read_text(encoding="utf-8")
    invalid = project / "invalid-change-set.json"
    invalid.write_text(
        json.dumps(
            {
                "changes": [
                    {
                        "action": "remove",
                        "target_id": "curated-opening",
                        "evidence_source_ids": ["source-999"],
                        "confidence": 0.8,
                        "rationale": "Unsupported removal must fail.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(VoiceBuildError, match="Unsupported evolution evidence"):
        _rebuild(project, "--change-set", str(invalid))

    assert (candidate / "manifest.json").read_text(encoding="utf-8") == candidate_before
    assert (active / "profile.md").read_text(encoding="utf-8") == active_before


def test_full_regeneration_requires_explicit_replacement_mode(project, capsys):
    active = _activate_curated_voice(project, capsys)
    active_profile = (active / "profile.md").read_text(encoding="utf-8")
    _add_new_evidence(project, capsys)

    assert _rebuild(project, "--full-regenerate") == 0
    capsys.readouterr()
    candidate = project / "profiles" / "example-person" / "candidate"
    manifest = VoiceManifest.model_validate_json(
        (candidate / "manifest.json").read_text(encoding="utf-8")
    )
    delta = json.loads((candidate / "voice-evolution.json").read_text(encoding="utf-8"))
    evaluation = json.loads((candidate / "evaluation-report.json").read_text(encoding="utf-8"))

    assert manifest.evolution_mode == "full-regenerate"
    assert "Author-approved opening rule" not in (candidate / "profile.md").read_text()
    assert {item["guidance_id"] for item in delta["removed"]} == {"curated-opening"}
    assert evaluation["regression_evaluation"]["explicit_replacement"] is True
    assert (active / "profile.md").read_text(encoding="utf-8") == active_profile
