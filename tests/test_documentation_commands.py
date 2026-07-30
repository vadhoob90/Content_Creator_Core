import re
from pathlib import Path

from content_creator.cli import build_parser

ROOT = Path(__file__).resolve().parents[1]


def test_documented_command_families_are_parseable():
    parser = build_parser()
    commands = [
        ["init"],
        ["init", "--agent-template", "standard"],
        [
            "workspace",
            "create",
            "Content_Creator_Alice",
            "--author-name",
            "Alice Example",
            "--pack",
            "linkedin-post",
        ],
        ["agents", "scaffold"],
        ["agents", "status"],
        ["agents", "diff-template"],
        ["doctor"],
        ["overview"],
        ["overview", "--json"],
        ["start"],
        ["start", "Write a useful article"],
        ["advanced"],
        ["provider", "verify", "openai"],
        ["provider", "select", "codex-native"],
        ["provider", "verify", "codex-native"],
        ["provider", "verify", "claude-native"],
        ["pack", "list"],
        ["pack", "show", "general-text", "--resolved"],
        ["pack", "validate", "general-text"],
        ["voice", "list"],
        [
            "voice",
            "onboard",
            "example-person",
            "--strategy",
            "starter",
            "--author-name",
            "Example Person",
        ],
        ["voice", "status", "example-person"],
        ["voice", "show", "example-person"],
        ["voice", "signature", "example-person"],
        ["voice", "verify", "example-person"],
        ["voice", "approve", "example-person"],
        ["voice", "deactivate", "example-person", "--reason", "withdrawn"],
        ["voice", "reactivate", "example-person"],
        ["voice", "consolidate-learnings", "example-person"],
        [
            "perspective",
            "create",
            "--voice",
            "default",
            "--context",
            "legal-training",
        ],
        ["perspective", "list", "--voice", "default"],
        [
            "perspective",
            "status",
            "--voice",
            "default",
            "--context",
            "legal-training",
        ],
        [
            "perspective",
            "proposals",
            "--voice",
            "default",
            "--context",
            "legal-training",
        ],
        [
            "perspective",
            "compare-create",
            "--run",
            "run-id",
            "--baseline",
            "ordinary-chat.md",
        ],
        [
            "perspective",
            "compare-record",
            "--run",
            "run-id",
            "--assessment",
            "assessment.json",
        ],
        ["status", "run-id"],
        ["approve-research", "run-id"],
        ["reject-research", "run-id"],
        ["publish", "run-id"],
        ["run", "--brief", "brief.yaml"],
        ["eval"],
        ["workspace", "upgrade", "--to", "v0.6.0"],
        ["workspace", "upgrade", "--to", "v0.6.0", "--apply"],
    ]
    for command in commands:
        assert parser.parse_args(command).command


def test_local_documentation_links_resolve():
    documents = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
    broken = []
    for document in documents:
        text = document.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
            if target.startswith(("http://", "https://", "#")):
                continue
            path_text = target.split("#", 1)[0]
            if path_text and not (document.parent / path_text).resolve().exists():
                broken.append("{} -> {}".format(document.relative_to(ROOT), target))
    assert not broken


def test_private_voice_material_and_operational_paths_are_ignored():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".voice-cache/" in ignore
    assert "voice-material/" in ignore
    assert "profiles/*/work-order.json" in ignore


def test_publication_perspective_proposals_do_not_trigger_offline_ci():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert "!profiles/*/perspectives/*/proposals/**" in workflow
