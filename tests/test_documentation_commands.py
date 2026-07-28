import re
from pathlib import Path

from content_creator.cli import build_parser

ROOT = Path(__file__).resolve().parents[1]


def test_documented_command_families_are_parseable():
    parser = build_parser()
    commands = [
        ["init"],
        ["doctor"],
        ["provider", "verify", "openai"],
        ["pack", "list"],
        ["pack", "show", "general-text", "--resolved"],
        ["pack", "validate", "general-text"],
        ["voice", "list"],
        ["voice", "status", "example-person"],
        ["voice", "show", "example-person"],
        ["voice", "signature", "example-person"],
        ["voice", "verify", "example-person"],
        ["voice", "approve", "example-person"],
        ["voice", "deactivate", "example-person", "--reason", "withdrawn"],
        ["voice", "reactivate", "example-person"],
        ["voice", "consolidate-learnings", "example-person"],
        ["status", "run-id"],
        ["approve-research", "run-id"],
        ["reject-research", "run-id"],
        ["publish", "run-id"],
        ["run", "--brief", "brief.yaml"],
        ["eval"],
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


def test_private_cache_is_ignored():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".voice-cache/" in ignore
