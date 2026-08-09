#!/usr/bin/env python3
"""Build a PR mutation plan and validate recorded survivor decisions."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import cast

from content_creator.mutation_policy import ReleaseImpact, plan_mutation_scope, validate_waivers


def _impact_from_event(path: Path | None) -> ReleaseImpact:
    if path is None:
        return "none"
    event = json.loads(path.read_text(encoding="utf-8"))
    labels = {
        item.get("name", "")
        for item in event.get("pull_request", {}).get("labels", [])
        if isinstance(item, dict)
    }
    selected = [impact for impact in ("patch", "minor", "major") if f"release:{impact}" in labels]
    return cast(ReleaseImpact, selected[0] if len(selected) == 1 else "none")


def _write_github_output(path: Path, patterns: tuple[str, ...], required: bool) -> None:
    with path.open("a", encoding="utf-8") as output:
        output.write(f"required={'true' if required else 'false'}\n")
        output.write("patterns<<MUTATION_PATTERNS\n")
        output.write("\n".join(patterns))
        output.write("\nMUTATION_PATTERNS\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--changed-files", type=Path)
    parser.add_argument("--event", type=Path)
    parser.add_argument("--impact", choices=("none", "patch", "minor", "major"))
    parser.add_argument("--waivers", type=Path, default=Path(".github/mutation-waivers.yaml"))
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()

    errors = validate_waivers(args.waivers)
    if errors:
        for error in errors:
            print(f"mutation waiver error: {error}")
        return 1

    changed = []
    if args.changed_files:
        changed = [
            line.strip() for line in args.changed_files.read_text().splitlines() if line.strip()
        ]
    impact = cast(ReleaseImpact, args.impact) if args.impact else _impact_from_event(args.event)
    plan = plan_mutation_scope(changed, impact)
    print(json.dumps(plan.as_dict(), indent=2))
    github_output = args.github_output or (
        Path(os.environ["GITHUB_OUTPUT"]) if "GITHUB_OUTPUT" in os.environ else None
    )
    if github_output:
        _write_github_output(github_output, plan.patterns, plan.required)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
