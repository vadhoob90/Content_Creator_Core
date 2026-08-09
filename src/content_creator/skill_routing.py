"""Validate and score host-level routing cases for packaged Core skills."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

KNOWN_SKILLS = {"content-creator", "voice-builder"}
KNOWN_CATEGORIES = {"positive", "negative", "near-miss"}


def load_skill_routing_suite(path: Path) -> dict[str, Any]:
    """Load one skill-routing suite from YAML.

    Args:
        path (Path): YAML suite containing routing cases and validation policy.

    Returns:
        dict[str, Any]: Parsed suite mapping.

    Raises:
        ValueError: If the YAML document is not a mapping.
    """
    suite = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(suite, dict):
        raise ValueError("Skill-routing suite must be a mapping")
    return suite


def validate_skill_routing_suite(suite: dict[str, Any]) -> list[str]:
    """Return deterministic schema and coverage errors for a routing suite.

    Validate structure before aggregating category and skill coverage so malformed
    cases produce bounded errors instead of preventing the remainder from being
    inspected.

    Args:
        suite (dict[str, Any]): Parsed routing suite to validate.

    Returns:
        list[str]: Stable validation errors; an empty list means the suite is valid.
    """
    errors: list[str] = []
    if suite.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    budget = suite.get("instruction_word_budget")
    if not isinstance(budget, int) or isinstance(budget, bool) or budget < 1:
        errors.append("instruction_word_budget must be a positive integer")
    cases = suite.get("cases")
    if not isinstance(cases, list) or not cases:
        return errors + ["cases must be a non-empty list"]
    seen_ids: set[str] = set()
    prompt_expectations: dict[str, tuple[bool, str | None]] = {}
    covered_categories: set[str] = set()
    positive_skills: set[str] = set()
    for index, case in enumerate(cases):
        errors.extend(_case_errors(case, index))
        if not isinstance(case, dict):
            continue
        case_id = case.get("id")
        if isinstance(case_id, str):
            if case_id in seen_ids:
                errors.append(f"duplicate case id: {case_id}")
            seen_ids.add(case_id)
        category = case.get("category")
        covered_categories.add(str(category))
        skill = case.get("expected_skill")
        if case.get("expected_activation") is True and skill in KNOWN_SKILLS:
            positive_skills.add(skill)
        prompt = case.get("prompt")
        if isinstance(prompt, str):
            normalized = " ".join(prompt.casefold().split())
            expectation = (case.get("expected_activation") is True, skill)
            previous = prompt_expectations.get(normalized)
            if previous is not None:
                qualifier = "contradictory" if previous != expectation else "duplicate"
                errors.append(f"{qualifier} prompt: {case_id or index}")
            prompt_expectations[normalized] = expectation
    missing_categories = KNOWN_CATEGORIES - covered_categories
    if missing_categories:
        errors.append("missing categories: " + ", ".join(sorted(missing_categories)))
    missing_skills = KNOWN_SKILLS - positive_skills
    if missing_skills:
        errors.append("missing positive skill coverage: " + ", ".join(sorted(missing_skills)))
    return errors


def _case_errors(case: Any, index: int) -> list[str]:
    """Return schema errors for one routing case.

    Args:
        case (Any): Candidate routing case value.
        index (int): Zero-based case position used in error messages.

    Returns:
        list[str]: Stable schema errors for the case.
    """
    if not isinstance(case, dict):
        return [f"case {index} must be a mapping"]
    errors = []
    case_id = case.get("id")
    if not isinstance(case_id, str) or not case_id.strip():
        errors.append(f"case {index} requires a non-empty id")
    prompt = case.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        errors.append(f"case {case_id or index} requires a non-empty prompt")
    category = case.get("category")
    if category not in KNOWN_CATEGORIES:
        errors.append(f"case {case_id or index} has invalid category")
    activation = case.get("expected_activation")
    if not isinstance(activation, bool):
        errors.append(f"case {case_id or index} requires boolean expected_activation")
    skill = case.get("expected_skill")
    if activation is True and skill not in KNOWN_SKILLS:
        errors.append(f"case {case_id or index} requires a known expected_skill")
    if activation is False and skill is not None:
        errors.append(f"case {case_id or index} must omit expected_skill")
    return errors


def validate_packaged_skills(root: Path, word_budget: int) -> list[str]:
    """Validate skill frontmatter, instruction budget, and packaged-copy parity.

    Args:
        root (Path): Repository root containing development and packaged skill copies.
        word_budget (int): Maximum instruction words permitted for each skill.

    Returns:
        list[str]: Stable validation errors; an empty list means both skills are valid.
    """
    errors: list[str] = []
    for skill in sorted(KNOWN_SKILLS):
        development = root / ".agents" / "skills" / skill
        packaged = root / "src" / "content_creator" / "resources" / "skills" / skill
        for relative in (Path("SKILL.md"), Path("agents/openai.yaml")):
            left = development / relative
            right = packaged / relative
            if not left.is_file() or not right.is_file():
                errors.append(f"{skill} is missing {relative}")
            elif left.read_bytes() != right.read_bytes():
                errors.append(f"{skill} packaged copy differs: {relative}")
        skill_path = development / "SKILL.md"
        if not skill_path.is_file():
            continue
        text = skill_path.read_text(encoding="utf-8")
        metadata = _frontmatter(text, skill, errors)
        if metadata.get("name") != skill:
            errors.append(f"{skill} frontmatter name must match its directory")
        if not isinstance(metadata.get("description"), str) or not metadata["description"].strip():
            errors.append(f"{skill} requires a frontmatter description")
        if len(text.split()) > word_budget:
            errors.append(f"{skill} exceeds the {word_budget}-word instruction budget")
    return errors


def _frontmatter(text: str, skill: str, errors: list[str]) -> dict[str, Any]:
    """Parse one skill's YAML frontmatter while recording bounded errors.

    Args:
        text (str): Complete skill Markdown text.
        skill (str): Stable skill identifier used in errors.
        errors (list[str]): Mutable error collection receiving parse failures.

    Returns:
        dict[str, Any]: Parsed metadata, or an empty mapping after failure.
    """
    parts = text.split("---", 2)
    if len(parts) != 3 or parts[0].strip():
        errors.append(f"{skill} requires YAML frontmatter")
        return {}
    try:
        metadata = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        errors.append(f"{skill} frontmatter is invalid YAML")
        return {}
    if not isinstance(metadata, dict):
        errors.append(f"{skill} frontmatter must be a mapping")
        return {}
    return metadata


def score_skill_routing(
    suite: dict[str, Any], observations: list[dict[str, Any]]
) -> dict[str, Any]:
    """Score observed host routing against reviewed expectations.

    Args:
        suite (dict[str, Any]): Validated routing suite.
        observations (list[dict[str, Any]]): Host results keyed by case id with
            ``activated`` and optional ``skill`` fields.

    Returns:
        dict[str, Any]: Precision, recall, errors, and per-case outcomes.

    Raises:
        ValueError: If observations are missing, duplicated, or unknown.
    """
    expected = {case["id"]: case for case in suite["cases"]}
    observed: dict[str, dict[str, Any]] = {}
    for item in observations:
        case_id = item.get("case")
        if not isinstance(case_id, str):
            raise ValueError("Observed case id must be a string")
        if case_id not in expected:
            raise ValueError(f"Unknown observed case: {case_id}")
        if case_id in observed:
            raise ValueError(f"Duplicate observed case: {case_id}")
        observed[case_id] = item
    missing = expected.keys() - observed.keys()
    if missing:
        raise ValueError("Missing observed cases: " + ", ".join(sorted(missing)))
    outcomes = []
    true_positive = false_positive = false_negative = 0
    for case_id, case in expected.items():
        item = observed[case_id]
        activated = item.get("activated") is True
        expected_activation = case["expected_activation"]
        correct_skill = not activated or item.get("skill") == case.get("expected_skill")
        passed = activated == expected_activation and correct_skill
        true_positive += int(activated and expected_activation and correct_skill)
        false_positive += int(activated and not expected_activation)
        false_negative += int(expected_activation and (not activated or not correct_skill))
        outcomes.append({"case": case_id, "passed": passed, "observed": item})
    precision_denominator = true_positive + false_positive
    recall_denominator = true_positive + false_negative
    return {
        "total": len(outcomes),
        "passed": sum(item["passed"] for item in outcomes),
        "precision": true_positive / precision_denominator if precision_denominator else 1.0,
        "recall": true_positive / recall_denominator if recall_denominator else 1.0,
        "false_positives": false_positive,
        "false_negatives": false_negative,
        "outcomes": outcomes,
    }


def write_skill_routing_report(path: Path, report: dict[str, Any]) -> None:
    """Persist a deterministic JSON routing report.

    Args:
        path (Path): Output file path.
        report (dict[str, Any]): Scored routing report.

    Returns:
        None: The report is written atomically enough for advisory tooling.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
