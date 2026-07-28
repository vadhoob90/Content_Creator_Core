from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .storage import RunStore, StorageError

DIMENSIONS = [
    "voice_authenticity",
    "originality_of_thought",
    "factual_reliability",
    "publishability",
]


def create_blind_comparison(root: Path, run_id: str, baseline: Path) -> dict:
    run_dir = RunStore(root).run_dir(run_id)
    candidate = run_dir / "final.md"
    if not candidate.exists():
        raise StorageError("Run has no final.md: {}".format(run_id))
    if not baseline.exists():
        raise StorageError("Baseline does not exist: {}".format(baseline))
    candidate_text = candidate.read_text(encoding="utf-8")
    baseline_text = baseline.read_text(encoding="utf-8")
    selector = hashlib.sha256(
        (run_id + baseline_text).encode("utf-8")
    ).digest()[0] % 2
    candidate_label = "A" if selector == 0 else "B"
    baseline_label = "B" if candidate_label == "A" else "A"
    options = {
        candidate_label: candidate_text,
        baseline_label: baseline_text,
    }
    directory = run_dir / "blind-comparison"
    RunStore._atomic_text(directory / "option-a.md", options["A"].rstrip())
    RunStore._atomic_text(directory / "option-b.md", options["B"].rstrip())
    template = {
        "schema_version": "1.0",
        "run_id": run_id,
        "blind": True,
        "preferred_option": None,
        "scores": {
            label: {dimension: None for dimension in DIMENSIONS}
            for label in ("A", "B")
        },
        "revision_effort": {"A": None, "B": None},
        "comments": None,
    }
    RunStore._atomic_text(
        directory / "assessment-template.json",
        json.dumps(template, indent=2),
    )
    RunStore._atomic_text(
        directory / ".mapping.json",
        json.dumps(
            {
                "candidate": candidate_label,
                "ordinary_chat_baseline": baseline_label,
            },
            indent=2,
        ),
    )
    return {
        "run_id": run_id,
        "option_a": str((directory / "option-a.md").relative_to(root)),
        "option_b": str((directory / "option-b.md").relative_to(root)),
        "assessment_template": str(
            (directory / "assessment-template.json").relative_to(root)
        ),
        "mapping_hidden_until_recorded": True,
    }


def record_blind_comparison(root: Path, run_id: str, assessment: Path) -> dict:
    run_dir = RunStore(root).run_dir(run_id)
    directory = run_dir / "blind-comparison"
    mapping_path = directory / ".mapping.json"
    if not mapping_path.exists():
        raise StorageError("Blind comparison has not been created")
    data = json.loads(assessment.read_text(encoding="utf-8"))
    preferred = data.get("preferred_option")
    if preferred not in {"A", "B", "tie"}:
        raise ValueError("preferred_option must be A, B, or tie")
    for label in ("A", "B"):
        for dimension in DIMENSIONS:
            value = data.get("scores", {}).get(label, {}).get(dimension)
            if not isinstance(value, (int, float)) or not 1 <= value <= 10:
                raise ValueError(
                    "{} {} must be scored from 1 to 10".format(label, dimension)
                )
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    preferred_system = (
        "tie"
        if preferred == "tie"
        else next(name for name, label in mapping.items() if label == preferred)
    )
    result = {
        **data,
        "blind": True,
        "revealed_mapping": mapping,
        "preferred_system": preferred_system,
    }
    RunStore._atomic_text(
        directory / "assessment-result.json",
        json.dumps(result, indent=2),
    )
    return result
