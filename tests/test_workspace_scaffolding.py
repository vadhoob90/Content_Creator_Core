import json

import pytest
import yaml

from content_creator.cli import main
from content_creator.voices import VoiceError, VoiceRegistry


def _create_arguments(destination):
    return [
        "workspace",
        "create",
        str(destination),
        "--name",
        "Content Creator Alice",
        "--author-name",
        "Alice Example",
        "--voice-id",
        "alice-general",
        "--voice-label",
        "Alice — General",
        "--pack",
        "linkedin-post",
        "--pack",
        "linkedin-article",
        "--core-ref",
        "v0.4.0",
    ]


def test_workspace_create_generates_complete_thin_repository(tmp_path, capsys):
    destination = tmp_path / "Content_Creator_Alice"

    assert main(_create_arguments(destination)) == 0
    result = json.loads(capsys.readouterr().out)

    assert result["status"] == "ok"
    assert result["voice_id"] == "alice-general"
    assert result["packs"] == ["linkedin-post", "linkedin-article"]
    assert result["core_dependency"] == "content-creator==0.4.0"
    assert "content-creator.yaml" in result["created"]
    assert "profiles/registry.json" in result["created"]

    expected = {
        "README.md",
        "PERSONALISATION.md",
        "AGENTS.md",
        "CLAUDE.md",
        "pyproject.toml",
        "content-creator.yaml",
        ".gitignore",
        ".env.example",
        ".agents/skills/content-creator/SKILL.md",
        ".agents/skills/voice-builder/SKILL.md",
        "agents/writer.md",
        "learnings/memory.json",
        "profiles/registry.json",
        "profiles/README.md",
        "profiles/alice-general/README.md",
        "profiles/alice-general/onboarding.json",
        "profiles/alice-general/learnings/memory.json",
        "learnings/README.md",
        "docs/setup-and-technical-guide.md",
        "voice-material/alice-general/source-urls.txt",
        "content/linkedin-post/published/.gitkeep",
        "content/linkedin-article/published/.gitkeep",
        "tests/test_workspace.py",
        "publication-receipts/baseline.json",
    }
    assert all((destination / path).exists() for path in expected)
    assert not (destination / "src" / "content_creator").exists()

    pyproject = (destination / "pyproject.toml").read_text(encoding="utf-8")
    assert "content-creator==0.4.0" in pyproject
    configuration = yaml.safe_load(
        (destination / "content-creator.yaml").read_text(encoding="utf-8")
    )
    assert configuration["perspective"]["mode"] == "automatic"
    assert configuration["perspective"]["allow_multiple"] is True
    assert configuration["coordinator"]["default_voice"] == "alice-general"
    assert configuration["coordinator"]["default_pack"] == "linkedin-post"
    assert configuration["coordinator"]["external_publication"] == "disabled"
    assert configuration["statistical_voice_score"]["enabled"] is False
    assert configuration["statistical_voice_score"]["method"] == "deterministic"
    assert configuration["publication_provenance"]["policy"] == "required-for-new-publications"
    onboarding = json.loads(
        (destination / "profiles" / "alice-general" / "onboarding.json").read_text(encoding="utf-8")
    )
    assert onboarding["status"] == "undecided"
    assert onboarding["strategy"] is None
    with pytest.raises(VoiceError, match="onboarding decision required"):
        VoiceRegistry(destination).resolve("alice-general")
    with pytest.raises(VoiceError, match="default test profile is unavailable"):
        VoiceRegistry(destination).resolve("default")

    readme = (destination / "README.md").read_text(encoding="utf-8")
    ignore = (destination / ".gitignore").read_text(encoding="utf-8")
    assert "profiles/*/work-order.json" in ignore
    assert "voice-material/**/*" in ignore
    assert "!voice-material/**/source-urls.txt" in ignore
    assert "- `linkedin-post`" in readme
    assert "- `linkedin-article`" in readme
    assert "## Core dependency" in readme
    assert "content-creator==0.4.0" in readme
    assert "Content_Creator_Core/tree/v0.4.0" in readme
    assert "pyproject.toml` and the\nresolution in `uv.lock` are authoritative" in readme
    _assert_author_navigation(destination, readme)

    _assert_generated_workspace_runs(destination, capsys)


def _assert_author_navigation(destination, readme):
    assert "## Quick start" in readme
    assert "How this system is personalised to me" in readme
    assert "Technical setup, uv, providers, and CLI usage" in readme
    assert "Terminal installation and maintenance use `uv`" in readme
    personalisation = (destination / "PERSONALISATION.md").read_text(encoding="utf-8")
    assert "## What my agents have learnt" in personalisation
    assert "profiles/alice-general/learnings/memory.json" in personalisation
    technical = (destination / "docs" / "setup-and-technical-guide.md").read_text(encoding="utf-8")
    assert "uv sync --dev" in technical
    assert "`voice add-sources` command" in technical


def _assert_generated_workspace_runs(destination, capsys):
    generated_test = (destination / "tests" / "test_workspace.py").read_text(encoding="utf-8")
    compile(generated_test, "test_workspace.py", "exec")
    assert main(["--workspace", str(destination), "doctor"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"


def test_workspace_create_is_idempotent_and_preserves_customisation(tmp_path, capsys):
    destination = tmp_path / "Content_Creator_Alice"
    arguments = _create_arguments(destination)
    assert main(arguments) == 0
    capsys.readouterr()

    readme = destination / "README.md"
    writer = destination / "agents" / "writer.md"
    readme.write_text("# Custom README", encoding="utf-8")
    writer.write_text("# Custom Writer", encoding="utf-8")

    assert main(arguments) == 0
    result = json.loads(capsys.readouterr().out)

    assert readme.read_text(encoding="utf-8") == "# Custom README"
    assert writer.read_text(encoding="utf-8") == "# Custom Writer"
    assert "README.md" in result["preserved"]
    assert "agents/writer.md" in result["preserved"]
    assert result["created"] == []


def test_workspace_create_defaults_to_general_text(tmp_path, capsys):
    destination = tmp_path / "general-workspace"

    assert (
        main(
            [
                "workspace",
                "create",
                str(destination),
                "--author-name",
                "Example Author",
                "--core-ref",
                "reviewed-commit",
                "--core-source",
                "git",
                "--perspective-mode",
                "explicit",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)

    assert result["name"] == "general-workspace"
    assert result["voice_id"] == "example-author-general"
    assert result["packs"] == ["general-text"]
    assert result["perspective_mode"] == "explicit"
    assert (destination / "content" / "general-text" / "published" / ".gitkeep").exists()


def test_workspace_create_can_pin_a_reviewed_git_commit(tmp_path, capsys):
    destination = tmp_path / "git-workspace"
    commit = "a" * 40

    assert (
        main(
            [
                "workspace",
                "create",
                str(destination),
                "--author-name",
                "Example Author",
                "--core-source",
                "git",
                "--core-ref",
                commit,
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)

    assert result["core_dependency"].endswith("Content_Creator_Core.git@{}".format(commit))


def test_workspace_create_rejects_unknown_pack(tmp_path):
    with pytest.raises(ValueError, match="Unknown content packs"):
        main(
            [
                "workspace",
                "create",
                str(tmp_path / "workspace"),
                "--author-name",
                "Example Author",
                "--pack",
                "not-a-pack",
            ]
        )
