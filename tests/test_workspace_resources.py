import json

from content_creator.cli import main
from content_creator.configuration import Configuration
from content_creator.domain import WorkOrder
from content_creator.packs import PackRegistry
from content_creator.prompting import PromptAssembler


def test_empty_workspace_uses_packaged_core_resources(tmp_path, capsys):
    assert main(["--workspace", str(tmp_path), "init"]) == 0
    capsys.readouterr()

    assert main(["--workspace", str(tmp_path), "doctor"]) == 0
    doctor = json.loads(capsys.readouterr().out)

    assert doctor["checks"]["content_packs"] == [
        "general-text",
        "linkedin-article",
        "linkedin-post",
    ]
    assert Configuration(tmp_path).models["roles"]["writer-text"]
    prompt = PromptAssembler(tmp_path).system_prompt(
        "writer", WorkOrder(request="write", topic="topic")
    )
    assert "# Writer" in prompt
    assert "Default Placeholder" in prompt


def test_workspace_pack_overrides_packaged_pack(tmp_path):
    pack_dir = tmp_path / "packs" / "general-text"
    pack_dir.mkdir(parents=True)
    pack_dir.joinpath("pack.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "id": "general-text",
                "version": "9.0.0",
                "format": "text",
                "destination": "content/general-text/published",
                "rubric": None,
            }
        ),
        encoding="utf-8",
    )

    packs = PackRegistry(tmp_path)

    assert packs.get("general-text").version == "9.0.0"
    assert {pack.id for pack in packs.list()} == {
        "general-text",
        "linkedin-article",
        "linkedin-post",
    }
