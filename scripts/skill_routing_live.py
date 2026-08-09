#!/usr/bin/env python3
"""Run repeated advisory host-level routing trials through a reviewed adapter."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from content_creator.skill_routing import (
    load_skill_routing_suite,
    write_skill_routing_report,
)
from content_creator.skill_routing_trials import (
    run_skill_routing_trials,
    skill_routing_result_path,
)


def main() -> int:
    """Run the live routing-trial command.

    Returns:
        int: Zero after a complete advisory report; adapter and contract failures
            raise instead of producing partial evidence.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--host", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--output-root", type=Path, default=Path("reports/skill-routing"))
    parser.add_argument("adapter", nargs=argparse.REMAINDER)
    arguments = parser.parse_args()
    adapter = arguments.adapter
    if adapter and adapter[0] == "--":
        adapter = adapter[1:]
    suite = load_skill_routing_suite(arguments.root.resolve() / "evals/skill-routing.yaml")
    report = run_skill_routing_trials(
        suite,
        arguments.host,
        arguments.model_version,
        adapter,
        trials_per_case=arguments.trials,
    )
    output = skill_routing_result_path(
        arguments.output_root, arguments.host, arguments.model_version, report["generated_at"]
    )
    write_skill_routing_report(output, report)
    print(json.dumps({"output": str(output), **report["metrics"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
