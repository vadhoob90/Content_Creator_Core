"""Run and report repeated advisory host-level skill-routing trials."""

from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .skill_routing import KNOWN_SKILLS, validate_skill_routing_suite

RoutingExecutor = Callable[[Sequence[str], str], str]


def run_skill_routing_trials(
    suite: dict[str, Any],
    host: str,
    model_version: str,
    command: Sequence[str],
    trials_per_case: int = 3,
    executor: RoutingExecutor | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Run repeated host-routing trials and return an advisory evidence report.

    The adapter receives one JSON request on standard input and emits one JSON
    observation. It executes without a shell so the reviewed boundary remains
    provider-neutral and injection-safe.

    Args:
        suite (dict[str, Any]): Validated routing suite.
        host (str): Host or harness identifier recorded with the evidence.
        model_version (str): Exact host model version recorded with the evidence.
        command (Sequence[str]): Adapter executable and arguments.
        trials_per_case (int): Odd trial count for every case. Defaults to ``3``.
        executor (RoutingExecutor | None): Injectable command executor for tests.
            Defaults to ``None``.
        generated_at (str | None): Stable UTC timestamp override for tests. Defaults
            to ``None``.

    Returns:
        dict[str, Any]: Metadata, metrics, case majorities, outcomes, and failures.

    Raises:
        ValueError: If configuration, suite, or adapter output is invalid, or an
            adapter invocation fails.
    """
    errors = validate_skill_routing_suite(suite)
    if errors:
        raise ValueError("Invalid skill-routing suite: " + "; ".join(errors))
    if not host.strip() or not model_version.strip():
        raise ValueError("Host and model version must be non-empty")
    if trials_per_case < 1 or trials_per_case % 2 == 0:
        raise ValueError("Trials per case must be a positive odd integer")
    if not command:
        raise ValueError("Adapter command must not be empty")
    invoke = executor or _execute_routing_adapter
    outcomes: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []
    prompts = {case["id"]: case["prompt"] for case in suite["cases"]}
    for case in suite["cases"]:
        case_trials = _run_case_trials(case, host, model_version, command, trials_per_case, invoke)
        outcomes.extend(case_trials)
        cases.append(_case_report(case, case_trials, trials_per_case))
    return {
        "schema_version": "1.0",
        "generated_at": generated_at or datetime.now(UTC).isoformat(),
        "host": host,
        "model_version": model_version,
        "trials_per_case": trials_per_case,
        "metrics": _routing_metrics(outcomes),
        "cases": cases,
        "failed_prompts": [
            {
                "case": item["case"],
                "trial": item["trial"],
                "prompt": prompts[item["case"]],
                "observed": item["observed"],
            }
            for item in outcomes
            if not item["passed"]
        ],
    }


def _run_case_trials(
    case: dict[str, Any],
    host: str,
    model_version: str,
    command: Sequence[str],
    trials_per_case: int,
    executor: RoutingExecutor,
) -> list[dict[str, Any]]:
    """Run all configured trials for one reviewed case.

    Args:
        case (dict[str, Any]): Reviewed routing case.
        host (str): Host identifier.
        model_version (str): Model version identifier.
        command (Sequence[str]): Adapter executable and arguments.
        trials_per_case (int): Configured odd trial count.
        executor (RoutingExecutor): Command execution boundary.

    Returns:
        list[dict[str, Any]]: Classified outcomes in trial order.
    """
    outcomes = []
    for trial in range(1, trials_per_case + 1):
        request = {
            "schema_version": "1.0",
            "host": host,
            "model_version": model_version,
            "trial": trial,
            "case": case["id"],
            "prompt": case["prompt"],
            "available_skills": sorted(KNOWN_SKILLS),
        }
        raw = executor(command, json.dumps(request))
        observed = _parse_trial_observation(raw, case["id"], trial)
        outcome = _routing_outcome(case, observed)
        outcome["trial"] = trial
        outcomes.append(outcome)
    return outcomes


def _case_report(
    case: dict[str, Any], outcomes: list[dict[str, Any]], trials_per_case: int
) -> dict[str, Any]:
    """Build the evidence record for one reviewed case.

    Args:
        case (dict[str, Any]): Reviewed routing case.
        outcomes (list[dict[str, Any]]): Classified trial outcomes.
        trials_per_case (int): Configured odd trial count.

    Returns:
        dict[str, Any]: Case expectations, strict majority, and trials.
    """
    return {
        "id": case["id"],
        "category": case["category"],
        "prompt": case["prompt"],
        "expected_activation": case["expected_activation"],
        "expected_skill": case.get("expected_skill"),
        "majority": _majority_decision(outcomes, trials_per_case),
        "trials": outcomes,
    }


def _execute_routing_adapter(command: Sequence[str], request: str) -> str:
    """Execute one routing adapter without invoking a shell.

    Args:
        command (Sequence[str]): Adapter executable and arguments.
        request (str): JSON request supplied on standard input.

    Returns:
        str: Adapter standard output.

    Raises:
        ValueError: If the adapter exits unsuccessfully.
    """
    completed = subprocess.run(
        list(command), input=request, text=True, capture_output=True, check=False
    )
    if completed.returncode:
        detail = completed.stderr.strip() or f"exit {completed.returncode}"
        raise ValueError(f"Skill-routing adapter failed: {detail}")
    return completed.stdout


def _parse_trial_observation(raw: str, case_id: str, trial: int) -> dict[str, Any]:
    """Parse and validate one adapter observation.

    Args:
        raw (str): Adapter JSON output.
        case_id (str): Expected case identifier.
        trial (int): Expected one-based trial number.

    Returns:
        dict[str, Any]: Normalized observation.

    Raises:
        ValueError: If the adapter output violates the observation contract.
    """
    try:
        observed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Skill-routing adapter output must be JSON") from exc
    if not isinstance(observed, dict) or not isinstance(observed.get("activated"), bool):
        raise ValueError("Skill-routing adapter output requires boolean activated")
    if observed.get("case", case_id) != case_id or observed.get("trial", trial) != trial:
        raise ValueError("Skill-routing adapter output identifies the wrong trial")
    skill = observed.get("skill")
    if observed["activated"] and not isinstance(skill, str):
        raise ValueError("Activated routing observations require a skill")
    if not observed["activated"] and skill is not None:
        raise ValueError("Inactive routing observations must omit skill")
    return {"case": case_id, "activated": observed["activated"], "skill": skill}


def _routing_outcome(case: dict[str, Any], observed: dict[str, Any]) -> dict[str, Any]:
    """Classify one routing observation against its reviewed expectation.

    Args:
        case (dict[str, Any]): Reviewed routing case.
        observed (dict[str, Any]): Normalized host observation.

    Returns:
        dict[str, Any]: Trial classification used for metrics and reporting.
    """
    activated = observed["activated"]
    expected_activation = case["expected_activation"]
    correct_skill = not activated or observed.get("skill") == case.get("expected_skill")
    return {
        "case": case["id"],
        "passed": activated == expected_activation and correct_skill,
        "true_positive": activated and expected_activation and correct_skill,
        "false_positive": activated and not expected_activation,
        "false_negative": expected_activation and (not activated or not correct_skill),
        "observed": observed,
    }


def _routing_metrics(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate trial-level routing metrics.

    Args:
        outcomes (list[dict[str, Any]]): Classified trial outcomes.

    Returns:
        dict[str, Any]: Counts, precision, recall, and error totals.
    """
    true_positive = sum(item["true_positive"] for item in outcomes)
    false_positive = sum(item["false_positive"] for item in outcomes)
    false_negative = sum(item["false_negative"] for item in outcomes)
    precision_denominator = true_positive + false_positive
    recall_denominator = true_positive + false_negative
    return {
        "total_trials": len(outcomes),
        "passed_trials": sum(item["passed"] for item in outcomes),
        "precision": true_positive / precision_denominator if precision_denominator else 1.0,
        "recall": true_positive / recall_denominator if recall_denominator else 1.0,
        "false_positives": false_positive,
        "false_negatives": false_negative,
    }


def _majority_decision(outcomes: list[dict[str, Any]], trials_per_case: int) -> dict[str, Any]:
    """Return the strict-majority route for one case.

    Args:
        outcomes (list[dict[str, Any]]): Classified trials for one case.
        trials_per_case (int): Odd configured trial count.

    Returns:
        dict[str, Any]: Majority observation, vote count, and pass state.
    """
    routes = Counter(
        (item["observed"]["activated"], item["observed"].get("skill")) for item in outcomes
    )
    route, votes = routes.most_common(1)[0]
    strict = votes > trials_per_case // 2
    matching = [
        item
        for item in outcomes
        if item["observed"]["activated"] == route[0] and item["observed"].get("skill") == route[1]
    ]
    return {
        "reached": strict,
        "votes": votes,
        "activated": route[0] if strict else None,
        "skill": route[1] if strict else None,
        "passed": strict and matching[0]["passed"],
    }


def skill_routing_result_path(root: Path, host: str, model_version: str, generated_at: str) -> Path:
    """Return a stable host/model result path for one live report.

    Args:
        root (Path): Root directory for advisory routing evidence.
        host (str): Host identifier.
        model_version (str): Exact model version identifier.
        generated_at (str): Report timestamp.

    Returns:
        Path: Sanitized JSON report path grouped by host and model version.
    """
    timestamp = _path_component(generated_at.replace("+00:00", "Z").replace(":", ""))
    return root / _path_component(host) / _path_component(model_version) / f"{timestamp}.json"


def _path_component(value: str) -> str:
    """Return a filesystem-safe routing evidence path component.

    Args:
        value (str): Host, model, or timestamp text.

    Returns:
        str: Sanitized non-hierarchical path component.
    """
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-")
