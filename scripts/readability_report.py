#!/usr/bin/env python3
"""Report function-level readability guardrails for every Python source file."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = (ROOT / "src", ROOT / "scripts", ROOT / "tests")
MAX_FUNCTION_LINES = 80
IDEAL_FUNCTION_LINES = 40
MAX_PARAMETERS = 7
MAX_MODULE_LINES = 500
IDEAL_MODULE_LINES = 300
REVIEW_MODULE_LINES = 400
GENERIC_NAMES = {"data", "item", "manager", "utils"}


@dataclass(frozen=True)
class ModuleMeasure:
    path: Path
    line_count: int
    generic_name: bool
    generic_classes: tuple[str, ...]


@dataclass(frozen=True)
class FunctionMeasure:
    """Physical size and signature measurements for one Python function."""

    path: Path
    name: str
    line: int
    line_count: int
    parameter_count: int


def _function_measure(path: Path, node: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionMeasure:
    end_line = node.end_lineno or node.lineno
    positional_parameters = [*node.args.posonlyargs, *node.args.args]
    if positional_parameters and positional_parameters[0].arg in {"self", "cls"}:
        positional_parameters = positional_parameters[1:]
    parameter_count = len(positional_parameters) + len(node.args.kwonlyargs)
    return FunctionMeasure(
        path=path.relative_to(ROOT),
        name=node.name,
        line=node.lineno,
        line_count=end_line - node.lineno + 1,
        parameter_count=parameter_count,
    )


def collect_measures() -> tuple[list[ModuleMeasure], list[FunctionMeasure]]:
    """Collect measurements from production, maintenance, and test Python files."""
    measures: list[FunctionMeasure] = []
    modules: list[ModuleMeasure] = []
    for scan_root in SCAN_ROOTS:
        for path in sorted(scan_root.rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            syntax_tree = ast.parse(source, filename=str(path))
            modules.append(
                ModuleMeasure(
                    path=path.relative_to(ROOT),
                    line_count=len(source.splitlines()),
                    generic_name=path.stem.lower() in GENERIC_NAMES,
                    generic_classes=tuple(
                        node.name
                        for node in ast.walk(syntax_tree)
                        if isinstance(node, ast.ClassDef) and node.name.lower() in GENERIC_NAMES
                    ),
                )
            )
            measures.extend(
                _function_measure(path, node)
                for node in ast.walk(syntax_tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
    return modules, measures


def violations(modules: list[ModuleMeasure], measures: list[FunctionMeasure]) -> list[str]:
    """Return hard-limit failures while leaving ideal targets as review warnings."""
    failures: list[str] = []
    for module in modules:
        if module.line_count > MAX_MODULE_LINES:
            failures.append(
                f"{module.path} has {module.line_count} lines; maximum is {MAX_MODULE_LINES}"
            )
        if module.generic_name:
            failures.append(f"{module.path} uses a banned generic module name")
        for class_name in module.generic_classes:
            failures.append(f"{module.path} uses banned generic class name {class_name}")
    for measure in measures:
        location = f"{measure.path}:{measure.line} {measure.name}"
        if measure.line_count > MAX_FUNCTION_LINES:
            failures.append(
                f"{location} has {measure.line_count} lines; maximum is {MAX_FUNCTION_LINES}"
            )
        if measure.parameter_count > MAX_PARAMETERS:
            failures.append(
                f"{location} has {measure.parameter_count} parameters; maximum is {MAX_PARAMETERS}"
            )
    return failures


def warnings(modules: list[ModuleMeasure], measures: list[FunctionMeasure]) -> list[str]:
    """Return non-blocking signals for functions outside the preferred size."""
    function_warnings = [
        f"{measure.path}:{measure.line} {measure.name} exceeds the "
        f"{IDEAL_FUNCTION_LINES}-line ideal ({measure.line_count})"
        for measure in measures
        if IDEAL_FUNCTION_LINES < measure.line_count <= MAX_FUNCTION_LINES
    ]
    module_warnings = [
        f"{module.path} exceeds the {IDEAL_MODULE_LINES}-line ideal "
        f"({module.line_count}; focused review required above {REVIEW_MODULE_LINES})"
        for module in modules
        if IDEAL_MODULE_LINES < module.line_count <= MAX_MODULE_LINES
    ]
    return [*module_warnings, *function_warnings]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail on hard-limit violations")
    args = parser.parse_args()
    modules, measures = collect_measures()
    hard_failures = violations(modules, measures)
    for warning in warnings(modules, measures):
        print(f"WARNING: {warning}")
    for failure in hard_failures:
        print(f"ERROR: {failure}")
    print(
        f"Readability: {len(modules)} modules, {len(measures)} functions, "
        f"{len(hard_failures)} hard violations"
    )
    return 1 if args.check and hard_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
