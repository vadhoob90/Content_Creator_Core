import json

from content_creator.configuration import Configuration
from content_creator.prompting import PromptAssembler
from content_creator.providers import FakeProvider, ProviderRegistry
from content_creator.runner import AgentRunner
from content_creator.voice_builder import VoiceBuilder
from content_creator.voices import Authorisation, VoiceWorkOrder


def test_agentic_voice_build_runs_independent_analysis_criticism_and_evaluation(
    project,
):
    material = project / "example.txt"
    material.write_text(
        "By Example Person. " + "Concrete explanations make decisions visible. " * 50,
        encoding="utf-8",
    )
    responses = {
        "voice-analyst": [
            {
                "summary": "Evidence-led profile",
                "patterns": [
                    {
                        "id": "pattern-1",
                        "name": "Concrete explanation",
                        "description": "Makes decisions visible.",
                        "status": "provisional",
                        "confidence": 0.8,
                        "supporting_source_ids": ["source-001"],
                    }
                ],
            }
        ],
        "profile-critic": [{"rejected_pattern_ids": [], "warnings": []}],
        "voice-evaluator": [
            {
                "passed": True,
                "scores": {
                    "transfer": 8,
                    "naturalness": 8,
                    "personal_integrity": 10,
                },
                "hard_failures": [],
                "notes": ["Candidate is deliberately conservative."],
            }
        ],
    }
    fake = FakeProvider(responses)
    runner = AgentRunner(
        Configuration(project),
        ProviderRegistry({"anthropic": fake}),
        PromptAssembler(project),
    )
    builder = VoiceBuilder(project, runner=runner, provider="anthropic")
    builder.save_work_order(
        VoiceWorkOrder(
            display_name="Example Person",
            voice_id="example-person",
            authorisation=Authorisation(
                confirmed=True,
                attested_by="Owner",
                intended_uses=["general-text"],
            ),
            documents=[str(material)],
        )
    )
    manifest = builder.build("example-person")
    evaluation = json.loads(
        (
            project
            / "profiles"
            / "example-person"
            / "candidate"
            / "evaluation-report.json"
        ).read_text()
    )
    assert manifest.status.value == "awaiting_approval"
    assert evaluation["agent_judgement"]["passed"]
    assert [request.role for request in fake.requests] == [
        "voice-analyst",
        "profile-critic",
        "voice-evaluator",
    ]
