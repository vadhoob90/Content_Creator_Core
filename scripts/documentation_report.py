#!/usr/bin/env python3
"""Report missing production module, class, function, and method docstrings."""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "content_creator"


@dataclass(frozen=True)
class MissingDocstring:
    """Identify one production definition that lacks a docstring."""

    kind: str
    path: str
    line: int
    qualified_name: str


class DefinitionVisitor(ast.NodeVisitor):
    """Collect documentation coverage while retaining qualified names."""

    def __init__(self, path: str):
        """Initialise coverage counters for one source path."""
        self.path = path
        self.parents: list[str] = []
        self.totals = {"class": 0, "function": 0}
        self.documented = {"class": 0, "function": 0}
        self.missing: list[MissingDocstring] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Record a class and recursively inspect its contained definitions."""
        self._record("class", node)
        self.parents.append(node.name)
        self.generic_visit(node)
        self.parents.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Record a synchronous function and its nested definitions."""
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Record an asynchronous function and its nested definitions."""
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Record a callable while preserving nesting for qualified names."""
        self._record("function", node)
        self.parents.append(node.name)
        self.generic_visit(node)
        self.parents.pop()

    def _record(
        self,
        kind: str,
        node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        """Update coverage for one class or callable definition."""
        self.totals[kind] += 1
        if _has_docstring(node):
            self.documented[kind] += 1
            return
        qualified_name = ".".join([*self.parents, node.name])
        self.missing.append(
            MissingDocstring(
                kind=kind,
                path=self.path,
                line=node.lineno,
                qualified_name=qualified_name,
            )
        )


def _has_docstring(
    node: ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    """Return whether a definition starts with a non-empty docstring."""
    value = ast.get_docstring(node, clean=False)
    return bool(value and value.strip())


def inspect_source(path: str, source: str) -> dict:
    """Measure docstring coverage for one Python source string."""
    tree = ast.parse(source, filename=path)
    visitor = DefinitionVisitor(path)
    visitor.visit(tree)
    module_documented = _has_docstring(tree)
    missing = list(visitor.missing)
    if not module_documented:
        missing.insert(
            0,
            MissingDocstring(
                kind="module",
                path=path,
                line=1,
                qualified_name=Path(path).stem,
            ),
        )
    return {
        "totals": {
            "module": 1,
            "class": visitor.totals["class"],
            "function": visitor.totals["function"],
        },
        "documented": {
            "module": int(module_documented),
            "class": visitor.documented["class"],
            "function": visitor.documented["function"],
        },
        "missing": missing,
    }


def build_report(package_root: Path = PACKAGE_ROOT, root: Path = ROOT) -> dict:
    """Build deterministic documentation coverage for a production package."""
    totals = {"module": 0, "class": 0, "function": 0}
    documented = {"module": 0, "class": 0, "function": 0}
    missing: list[MissingDocstring] = []
    for path in sorted(package_root.rglob("*.py")):
        relative = str(path.relative_to(root))
        result = inspect_source(relative, path.read_text(encoding="utf-8"))
        for kind in totals:
            totals[kind] += result["totals"][kind]
            documented[kind] += result["documented"][kind]
        missing.extend(result["missing"])
    total_definitions = sum(totals.values())
    documented_definitions = sum(documented.values())
    return {
        "scope": str(package_root.relative_to(root)),
        "summary": {
            "total": total_definitions,
            "documented": documented_definitions,
            "missing": len(missing),
            "coverage_percent": (
                round(documented_definitions / total_definitions * 100, 2)
                if total_definitions
                else 100.0
            ),
        },
        "totals": totals,
        "documented": documented,
        "missing": [asdict(item) for item in missing],
    }


def main() -> int:
    """Render the documentation report and optionally enforce full coverage."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--check", action="store_true", help="fail when any docstring is missing")
    args = parser.parse_args()
    report = build_report()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for item in report["missing"]:
            print("ERROR: {path}:{line} {kind} {qualified_name} lacks a docstring".format(**item))
        summary = report["summary"]
        print(
            "Documentation: {documented}/{total} definitions ({coverage_percent:.2f}%); "
            "{missing} missing".format(**summary)
        )
    return 1 if args.check and report["summary"]["missing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
