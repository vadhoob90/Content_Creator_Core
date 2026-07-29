import json

import pytest
import yaml

from content_creator.cli import main


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


def test_workspace_create_generates_complete_thin_repository(
    tmp_path, capsys
):
    destination = tmp_path / "Content_Creator_Alice"

    assert main(_create_arguments(destination)) == 0
    result = json.loads(capsys.readouterr().out)

    assert result["status"] == "ok"
    assert result["voice_id"] == "alice-general"
    assert result["packs"] == ["linkedin-post", "linkedin-article"]
    assert result["core_dependency"].endswith(
        "Content_Creator_Core.git@v0.4.0"
    )
    assert "content-creator.yaml" in result["created"]
    assert "profiles/registry.json" in result["created"]

    expected = {
        "README.md",
        "AGENTS.md",
        "CLAUDE.md",
        "pyproject.toml",
        "content-creator.yaml",
        ".gitignore",
        ".env.example",
        "agents/writer.md",
        "learnings/memory.json",
        "profiles/registry.json",
        "profiles/alice-general/learnings/memory.json",
        "voice-material/alice-general/source-urls.txt",
        "content/linkedin-post/published/.gitkeep",
        "content/linkedin-article/published/.gitkeep",
        "tests/test_workspace.py",
    }
    assert all((destination / path).exists() for path in expected)
    assert not (destination / "src" / "content_creator").exists()

    pyproject = (destination / "pyproject.toml").read_text(encoding="utf-8")
    assert (
        "content-creator @ "
        "git+https://github.com/vadhoob90/Content_Creator_Core.git@v0.4.0"
        in pyproject
    )
    configuration = yaml.safe_load(
        (destination / "content-creator.yaml").read_text(encoding="utf-8")
    )
    assert configuration["perspective"]["mode"] == "automatic"
    assert configuration["perspective"]["allow_multiple"] is True

    readme = (destination / "README.md").read_text(encoding="utf-8")
    assert "Create content using chat" in readme
    assert "voice create" in readme
    assert "--use linkedin-post" in readme
    assert "--use linkedin-article" in readme

    generated_test = (
        destination / "tests" / "test_workspace.py"
    ).read_text(encoding="utf-8")
    compile(generated_test, "test_workspace.py", "exec")

    assert main(["--workspace", str(destination), "doctor"]) == 0
    doctor = json.loads(capsys.readouterr().out)
    assert doctor["status"] == "ok"


def test_workspace_create_is_idempotent_and_preserves_customisation(
    tmp_path, capsys
):
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
    assert (
        destination / "content" / "general-text" / "published" / ".gitkeep"
    ).exists()


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
