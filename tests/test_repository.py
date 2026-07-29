import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_general_pack_references_existing_rubric():
    pack_path = ROOT / "packs" / "general-text" / "pack.json"
    pack = json.loads(pack_path.read_text(encoding="utf-8"))

    rubric_path = (pack_path.parent / pack["rubric"]).resolve()
    assert rubric_path.is_file()


def test_copyright_notice_is_present():
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")

    assert "Copyright © 2026 Bharath Vadhoola" in notice
    assert "GNU Affero General Public License" in notice


def test_licensing_documents_describe_agpl_and_legacy_releases():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    licensing_summary = (ROOT / "LICENSING.md").read_text(encoding="utf-8")
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")

    assert "AGPL-3.0-or-later" in readme
    assert "Commercial use is permitted" in readme
    assert "PolyForm Noncommercial License 1.0.0" in licensing_summary
    assert "Earlier licence grants are not revoked" in licensing_summary
    assert "not a substitute for the licence" in licensing_summary
    assert "does not accept external code contributions" in contributing


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
        "profiles/starter": "profiles/starter",
        ".agents/skills": "skills",
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


def test_readme_is_a_streamlined_operator_journey():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "### 1. Create an author workspace" in readme
    assert "### 2. Choose a voice route" in readme
    assert "### 3. Ask for content naturally" in readme
    assert "```bash" not in readme
    assert (
        "[Create a thin content workspace]"
        "(docs/guides/creating-a-content-workspace.md)" in readme
    )
    assert "[Voice onboarding](docs/guides/voice-onboarding.md)" in readme
    assert (
        "[Content Creator Coordinator]"
        "(docs/guides/content-coordinator.md)" in readme
    )


def test_linked_guides_preserve_detailed_operator_commands():
    workspace_guide = (
        ROOT / "docs" / "guides" / "creating-a-content-workspace.md"
    ).read_text(encoding="utf-8")
    voice_guide = (
        ROOT / "docs" / "guides" / "voice-onboarding.md"
    ).read_text(encoding="utf-8")
    coordinator_guide = (
        ROOT / "docs" / "guides" / "content-coordinator.md"
    ).read_text(encoding="utf-8")

    assert "content-creator workspace create" in workspace_guide
    assert "--strategy source-derived" in voice_guide
    assert "--strategy starter" in voice_guide
    assert "voice approve example-person-general" in voice_guide
    assert "content-creator --workspace . run" in coordinator_guide
    assert "selected voice's learning memory" in coordinator_guide


def test_core_development_readme_covers_clone_and_validation():
    guide = (ROOT / "docs" / "core" / "README.md").read_text(
        encoding="utf-8"
    )

    assert "git clone" in guide
    assert 'python -m pip install -e ".[dev]"' in guide
    assert "ruff check ." in guide
    assert "pytest" in guide
    assert "Core versus a thin workspace" in guide


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
