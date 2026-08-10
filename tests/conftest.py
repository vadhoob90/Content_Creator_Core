import copy
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def anthropic_sdk_stub(monkeypatch):
    module = ModuleType("anthropic")

    def transform_schema(schema):
        transformed = copy.deepcopy(schema)

        def visit(value):
            if isinstance(value, list):
                for item in value:
                    visit(item)
                return
            if not isinstance(value, dict):
                return
            if value.get("type") == "object":
                value["additionalProperties"] = False
            constraints = []
            for name in ("minimum", "maximum"):
                if name in value:
                    constraints.append("{}: {}".format(name, value.pop(name)))
            if constraints:
                description = str(value.get("description", "")).strip()
                value["description"] = "; ".join(filter(None, [description, *constraints]))
            for item in value.values():
                visit(item)

        visit(transformed)
        return transformed

    module.transform_schema = transform_schema
    module.Anthropic = object
    module.AnthropicFoundry = object
    monkeypatch.setitem(sys.modules, "anthropic", module)
    return module


@pytest.fixture
def project(tmp_path):
    for name in (
        "agents",
        "learnings",
        "profiles",
        "rubrics",
        "config",
        "evals",
        "packs",
    ):
        source = REPO / name
        if source.exists():
            shutil.copytree(source, tmp_path / name)
    models = tmp_path / "config" / "models.yaml"
    if models.exists():
        configuration = yaml.safe_load(models.read_text(encoding="utf-8"))
        configuration["defaults"]["provider"] = "anthropic"
        models.write_text(
            yaml.safe_dump(configuration, sort_keys=False),
            encoding="utf-8",
        )
    (tmp_path / "content" / "linkedin-post" / "published").mkdir(parents=True)
    (tmp_path / "content" / "linkedin-article" / "published").mkdir(parents=True)
    return tmp_path


def passing_critique(score=9, issues=None, prior=None):
    return {
        "scores": {
            "hook": score,
            "clarity": score,
            "evidence_integrity": score,
            "reader_value": score,
            "voice_authenticity": score,
        },
        "issues": issues or [],
        "strengths": ["Strong"],
        "prior_issue_status": prior or {},
        "summary": "Review complete",
    }


def valid_draft(article=False, researched=False):
    suffix = " [Source](https://example.org/source)." if researched else "."
    paragraph = (
        "A useful writing system does not remove judgment. It makes the choices visible, "
        "keeps the author's intent explicit, and catches avoidable weaknesses before a "
        "draft reaches its reader{}".format(suffix)
    )
    if article:
        return "\n\n".join([paragraph] * 30)
    return "\n\n".join([paragraph] * 3)


def research_brief():
    return {
        "summary": "Research summary",
        "evidence": [
            {
                "claim": "A supported claim",
                "source_urls": ["https://example.org/source"],
                "confidence": "high",
            }
        ],
        "sources": [{"title": "Source", "url": "https://example.org/source"}],
        "tensions": [],
        "gaps": [],
    }
