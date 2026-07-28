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


def test_licensing_documents_distinguish_noncommercial_and_commercial_use():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    commercial_summary = (
        ROOT / "COMMERCIAL-LICENSING.md"
    ).read_text(encoding="utf-8")

    assert "source-available" in readme
    assert "Commercial use" in readme
    assert "separate written commercial licence" in commercial_summary
    assert "not a replacement for the licence" in commercial_summary


def test_packaged_core_resources_match_repository_sources():
    packaged = ROOT / "src" / "content_creator" / "resources"
    mappings = {
        "agents": "agent-templates/standard/agents",
        "contracts": "contracts",
        "config": "config",
        "evals": "evals",
        "packs": "packs",
        "rubrics": "rubrics",
        "profiles/default": "profiles/default",
    }
    for source_directory, packaged_directory in mappings.items():
        source_root = ROOT / source_directory
        packaged_root = packaged / packaged_directory
        source_files = {
            path.relative_to(source_root): path
            for path in source_root.rglob("*")
            if path.is_file()
        }
        packaged_files = {
            path.relative_to(packaged_root): path
            for path in packaged_root.rglob("*")
            if path.is_file()
        }
        assert source_files.keys() == packaged_files.keys()
        for relative, source in source_files.items():
            assert source.read_bytes() == packaged_files[relative].read_bytes()


def test_readme_contains_end_to_end_diagram():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "```mermaid" in readme
    assert "Voice Builder" in readme
    assert "Capability router" in readme


def test_readme_covers_the_complete_operator_journey():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "installation to your first finished piece" in readme
    assert "content-creator voice create" in readme
    assert "content-creator voice approve" in readme
    assert "content-creator run" in readme
    assert "updates only that voice’s learning memory" in readme


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


def test_migration_audit_tracks_all_linkedin_writer_capabilities():
    audit = (
        ROOT / "docs" / "linkedin-writer-migration-audit.md"
    ).read_text(encoding="utf-8")

    for capability in (
        "Six post/article × research routes",
        "OpenAI adapter",
        "Anthropic adapter",
        "Publication-triggered learning",
        "Replay evaluation harness",
        "Conversational invocation",
    ):
        assert capability in audit
