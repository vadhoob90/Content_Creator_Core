#!/usr/bin/env python3
"""Validate packaged skill routing fixtures and score optional host observations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from content_creator.skill_routing import (
    load_skill_routing_suite,
    score_skill_routing,
    validate_packaged_skills,
    validate_skill_routing_suite,
    write_skill_routing_report,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--observations", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    suite_path = root / "evals" / "skill-routing.yaml"
    packaged_path = root / "src" / "content_creator" / "resources" / "evals" / "skill-routing.yaml"
    suite = load_skill_routing_suite(suite_path)
    errors = validate_skill_routing_suite(suite)
    if not packaged_path.is_file() or suite_path.read_bytes() != packaged_path.read_bytes():
        errors.append("packaged skill-routing suite differs from the development copy")
    budget = suite.get("instruction_word_budget")
    if isinstance(budget, int) and not isinstance(budget, bool):
        errors.extend(validate_packaged_skills(root, budget))
    result: dict = {"valid": not errors, "errors": errors}
    if arguments.observations and not errors:
        observations = json.loads(arguments.observations.read_text(encoding="utf-8"))
        if not isinstance(observations, list):
            raise ValueError("Observations must be a JSON list")
        result["routing"] = score_skill_routing(suite, observations)
    if arguments.output:
        write_skill_routing_report(arguments.output, result)
    print(json.dumps(result, indent=2))
    return 1 if arguments.check and errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
