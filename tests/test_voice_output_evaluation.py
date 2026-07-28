import json

from content_creator.domain import WorkOrder
from content_creator.voice_evaluation import evaluate_voice_output
from content_creator.voices import hash_file


def _active_voice(project, source_text):
    cache = project / ".voice-cache" / "person"
    cache.mkdir(parents=True)
    (cache / "source.txt").write_text(source_text, encoding="utf-8")
    version = project / "profiles" / "person" / "versions" / "1.0.0"
    version.mkdir(parents=True)
    source_index = version / "source-index.json"
    source_index.write_text(
        json.dumps(
            [
                {
                    "cache_path": ".voice-cache/person/source.txt",
                    "approved_for_analysis": True,
                }
            ]
        ),
        encoding="utf-8",
    )
    (version / "manifest.json").write_text(
        json.dumps(
            {
                "id": "person",
                "display_name": "Person",
                "version": "1.0.0",
                "status": "active",
                "candidate_hash": "sha256:fixture",
                "components": {"sources": "source-index.json"},
                "component_hashes": {"sources": hash_file(source_index)},
                "supported_packs": {"general-text": "medium"},
                "authorisation": {"confirmed": True},
            }
        ),
        encoding="utf-8",
    )
    (project / "profiles" / "registry.json").write_text(
        json.dumps(
            {
                "profiles": {
                    "person": {
                        "status": "active",
                        "active_version": "1.0.0",
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def test_phrase_copying_and_unsupported_experience_are_hard_failures(project):
    source = (
        "This unusually distinctive sequence of twelve source words must never "
        "be copied directly into generated content for publication."
    )
    _active_voice(project, source)
    order = WorkOrder(
        request="write",
        topic="topic",
        voice_id="person",
        voice_version="1.0.0",
    )
    copied = evaluate_voice_output(project, order, source)
    invented = evaluate_voice_output(
        project,
        order,
        "I founded a global organisation and then explained the underlying decision.",
    )
    assert not copied["passed"]
    assert not invented["passed"]
