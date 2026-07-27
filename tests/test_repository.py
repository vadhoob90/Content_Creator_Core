import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_general_pack_references_existing_rubric():
    pack_path = ROOT / "packs" / "general-text" / "pack.json"
    pack = json.loads(pack_path.read_text(encoding="utf-8"))

    rubric_path = (pack_path.parent / pack["rubric"]).resolve()
    assert rubric_path.is_file()


def test_required_notice_is_present():
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")

    assert notice.startswith("Required Notice:")


def test_readme_contains_end_to_end_diagram():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "```mermaid" in readme
    assert "Voice Builder" in readme
    assert "Capability router" in readme


def test_readme_covers_the_complete_operator_journey():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "Current status:" in readme
    assert "content-creator voice create" in readme
    assert "content-creator voice approve" in readme
    assert "content-creator content run" in readme
    assert "triggers a voice-scoped learning update" in readme


def test_work_package_uses_the_repository_cli_name():
    work_package = ROOT / "docs" / "work-package"

    for path in work_package.rglob("*"):
        if path.is_file():
            assert "content-studio" not in path.read_text(encoding="utf-8")


def test_documentation_uses_an_explicit_fictional_voice_placeholder():
    example_documents = [
        ROOT / "README.md",
        ROOT / "docs" / "work-package" / "README.md",
        ROOT / "docs" / "work-package" / "schemas-and-commands.md",
        ROOT / "docs" / "work-package" / "general-text-pack.md",
    ]

    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in example_documents
    )

    assert "Example Person" in combined
    assert "example-person" in combined
