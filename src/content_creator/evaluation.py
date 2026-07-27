from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Iterable, List

import yaml

from .domain import (
    ContentFormat,
    ResearchBrief,
    ResearchSource,
    RunStatus,
    WorkOrder,
)
from .orchestrator import Orchestrator
from .providers import FakeProvider, ProviderRegistry
from .storage import RunStore


def _passing_critique() -> Dict:
    return {
        "scores": {
            "hook": 9,
            "clarity": 9,
            "evidence_integrity": 9,
            "reader_value": 9,
            "voice_authenticity": 9,
        },
        "issues": [],
        "strengths": ["Clear and useful"],
        "prior_issue_status": {},
        "summary": "Ready for author review",
    }


def _draft(order: WorkOrder) -> str:
    link = " [Source](https://example.org/source)." if order.research_depth.value != "none" else "."
    if order.format == ContentFormat.ARTICLE:
        paragraph = (
            "The useful question is not whether tools change work, but which choices "
            "they make newly visible. A good system keeps judgment with the person "
            "using it and makes its assumptions inspectable{}".format(link)
        )
        return "\n\n".join([paragraph] * 50)
    return (
        "The fastest writing workflow is not always the one with the fewest steps.\n\n"
        "A small amount of structure can protect the part that matters: judgment. "
        "Define the brief, make research an explicit choice, and let a reviewer expose "
        "weak reasoning before publication{}\n\n"
        "The system should reduce avoidable work without pretending taste can be automated."
    ).format(link)


def _research() -> Dict:
    return ResearchBrief(
        summary="A bounded evidence brief",
        evidence=[
            {
                "claim": "Tools shape choices as well as speed.",
                "source_urls": ["https://example.org/source"],
                "confidence": "medium",
            }
        ],
        sources=[{"title": "Source", "url": "https://example.org/source"}],
    ).model_dump(mode="json")


def load_cases(root: Path) -> List[Dict]:
    cases = []
    for path in sorted((root / "evals" / "cases").glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            cases.extend(data)
        else:
            cases.append(data)
    return cases


def run_replay_suite(root: Path, providers: Iterable[str]) -> Dict:
    outcomes = []
    for provider_name in providers:
        for case in load_cases(root):
            order = WorkOrder(
                request=case["request"],
                topic=case["topic"],
                format=case["format"],
                research_depth=case["research_depth"],
                research_source=case["research_source"],
                provider=provider_name,
            )
            responses = {
                "writer": [_draft(order)],
                "critic": [_passing_critique()],
            }
            if order.research_source == ResearchSource.AGENT:
                responses["researcher"] = [_research()]
            registry = ProviderRegistry({provider_name: FakeProvider(responses)})
            orchestrator = Orchestrator(root, registry=registry, max_revisions=1)
            state = orchestrator.start(order)
            if state.status == RunStatus.AWAITING_RESEARCH_APPROVAL:
                state = orchestrator.resume_research(state.id, approved=True)
            outcomes.append(
                {
                    "case": case["id"],
                    "provider_contract": provider_name,
                    "route": state.route_plan.route,
                    "status": state.status.value,
                    "passed": state.status == RunStatus.READY,
                    "run_id": state.id,
                }
            )
    report = {
        "mode": "replay",
        "total": len(outcomes),
        "passed": sum(item["passed"] for item in outcomes),
        "outcomes": outcomes,
    }
    output = root / ".eval-results" / "route-matrix.json"
    RunStore._atomic_text(output, json.dumps(report, indent=2))
    return report


def run_live_suite(root: Path, providers: Iterable[str]) -> Dict:
    """Run two bounded flagship cases against real provider adapters."""
    flagship_ids = {"post-none", "human-machine-deep"}
    cases = [case for case in load_cases(root) if case["id"] in flagship_ids]
    outcomes = []
    for provider_name in providers:
        for case in cases:
            started = time.monotonic()
            order = WorkOrder(
                request=case["request"],
                topic=case["topic"],
                format=case["format"],
                research_depth=case["research_depth"],
                research_source=case["research_source"],
                provider=provider_name,
            )
            orchestrator = Orchestrator(root, max_revisions=2)
            state = orchestrator.start(order)
            if state.status == RunStatus.AWAITING_RESEARCH_APPROVAL:
                state = orchestrator.resume_research(
                    state.id, approved=True, notes="Automated live-eval checkpoint"
                )
            selections = json.loads(
                orchestrator.store.read_artifact(state.id, "model-selections.json")
            )
            quality_paths = sorted(
                orchestrator.store.run_dir(state.id).glob("quality-*.json")
            )
            quality = (
                json.loads(quality_paths[-1].read_text(encoding="utf-8"))
                if quality_paths
                else {}
            )
            outcomes.append(
                {
                    "case": case["id"],
                    "provider": provider_name,
                    "status": state.status.value,
                    "passed": state.status == RunStatus.READY,
                    "run_id": state.id,
                    "input_tokens": sum(item.get("input_tokens") or 0 for item in selections),
                    "output_tokens": sum(
                        item.get("output_tokens") or 0 for item in selections
                    ),
                    "revisions": state.revision,
                    "weighted_score": quality.get("weighted_score"),
                    "latency_seconds": round(time.monotonic() - started, 2),
                }
            )
    report = {
        "mode": "live",
        "total": len(outcomes),
        "passed": sum(item["passed"] for item in outcomes),
        "outcomes": outcomes,
    }
    output = root / ".eval-results" / "live-provider.json"
    RunStore._atomic_text(output, json.dumps(report, indent=2))
    return report
