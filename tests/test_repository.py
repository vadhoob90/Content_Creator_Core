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
