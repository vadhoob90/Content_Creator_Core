#!/usr/bin/env python3
"""Report production Google Style documentation coverage and contract quality."""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import asdict
from pathlib import Path

from documentation_contracts import DocumentationIssue, validate_docstring

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "content_creator"


class DefinitionVisitor(ast.NodeVisitor):
    """Validate definitions while retaining qualified names and coverage totals."""

    def __init__(self, path: str) -> None:
        """Initialize validation state for one source path.

        Args:
            path (str): The repository-relative source path being inspected.

        Returns:
            None: The visitor is initialized in place.
        """
        self.path = path
        self.parents: list[str] = []
        self.totals = {"class": 0, "function": 0}
        self.documented = {"class": 0, "function": 0}
        self.issues: list[DocumentationIssue] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Validate a class and recursively inspect its definitions.

        Args:
            node (ast.ClassDef): The class syntax node to validate.

        Returns:
            None: Validation findings are appended to the visitor state.
        """
        self._record("class", node)
        self.parents.append(node.name)
        self.generic_visit(node)
        self.parents.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Validate a synchronous function and its nested definitions.

        Args:
            node (ast.FunctionDef): The synchronous function syntax node.

        Returns:
            None: Validation findings are appended to the visitor state.
        """
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Validate an asynchronous function and its nested definitions.

        Args:
            node (ast.AsyncFunctionDef): The asynchronous function syntax node.

        Returns:
            None: Validation findings are appended to the visitor state.
        """
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Validate a callable while preserving its qualified name.

        Args:
            node (ast.FunctionDef | ast.AsyncFunctionDef): The callable syntax node.

        Returns:
            None: Validation findings are appended to the visitor state.
        """
        self._record("function", node)
        self.parents.append(node.name)
        self.generic_visit(node)
        self.parents.pop()

    def _record(
        self,
        kind: str,
        node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        """Record coverage and validate one class or callable.

        Args:
            kind (str): The definition category, either ``class`` or ``function``.
            node (ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef): The syntax node.

        Returns:
            None: Counters and validation findings are updated in place.
        """
        self.totals[kind] += 1
        qualified_name = ".".join([*self.parents, node.name])
        docstring = ast.get_docstring(node, clean=True)
        if not docstring:
            self.issues.append(
                DocumentationIssue(
                    code="docstring-missing",
                    kind=kind,
                    path=self.path,
                    line=node.lineno,
                    qualified_name=qualified_name,
                    message="Add a docstring.",
                )
            )
            return
        self.documented[kind] += 1
        self.issues.extend(validate_docstring(self.path, kind, node, qualified_name, docstring))


def inspect_source(path: str, source: str) -> dict:
    """Measure and validate documentation for one Python source string.

    Args:
        path (str): The repository-relative source path used in findings.
        source (str): The Python source text to parse.

    Returns:
        dict: Coverage totals, documented totals, and structured issue records.

    Raises:
        SyntaxError: If source is not valid Python syntax.
    """
    tree = ast.parse(source, filename=path)
    visitor = DefinitionVisitor(path)
    visitor.visit(tree)
    module_docstring = ast.get_docstring(tree, clean=True)
    issues = list(visitor.issues)
    if module_docstring:
        issues[0:0] = validate_docstring(path, "module", tree, Path(path).stem, module_docstring)
    else:
        issues.insert(
            0,
            DocumentationIssue(
                code="docstring-missing",
                kind="module",
                path=path,
                line=1,
                qualified_name=Path(path).stem,
                message="Add a module docstring.",
            ),
        )
    return {
        "totals": {
            "module": 1,
            "class": visitor.totals["class"],
            "function": visitor.totals["function"],
        },
        "documented": {
            "module": int(bool(module_docstring)),
            "class": visitor.documented["class"],
            "function": visitor.documented["function"],
        },
        "issues": issues,
    }


def build_report(package_root: Path = PACKAGE_ROOT, root: Path = ROOT) -> dict:
    """Build a deterministic documentation report for a production package.

    Args:
        package_root (Path): The package directory to scan. Defaults to ``PACKAGE_ROOT``.
        root (Path): The repository root used for relative paths. Defaults to ``ROOT``.

    Returns:
        dict: Coverage totals, strict validation summary, and serialized issues.
    """
    totals = {"module": 0, "class": 0, "function": 0}
    documented = {"module": 0, "class": 0, "function": 0}
    issues: list[DocumentationIssue] = []
    for path in sorted(package_root.rglob("*.py")):
        relative = str(path.relative_to(root))
        result = inspect_source(relative, path.read_text(encoding="utf-8"))
        for kind in totals:
            totals[kind] += result["totals"][kind]
            documented[kind] += result["documented"][kind]
        issues.extend(result["issues"])
    total_definitions = sum(totals.values())
    documented_definitions = sum(documented.values())
    missing = sum(item.code == "docstring-missing" for item in issues)
    return {
        "scope": str(package_root.relative_to(root)),
        "summary": {
            "total": total_definitions,
            "documented": documented_definitions,
            "missing": missing,
            "invalid": len(issues) - missing,
            "coverage_percent": (
                round(documented_definitions / total_definitions * 100, 2)
                if total_definitions
                else 100.0
            ),
        },
        "totals": totals,
        "documented": documented,
        "issues": [asdict(item) for item in issues],
    }


def main() -> int:
    """Render the documentation report and optionally enforce the strict contract.

    Returns:
        int: Zero when valid or reporting only, otherwise one for failed enforcement.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--check", action="store_true", help="fail when documentation is invalid")
    args = parser.parse_args()
    report = build_report()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for item in report["issues"]:
            print("ERROR [{code}]: {path}:{line} {kind} {qualified_name}: {message}".format(**item))
        summary = report["summary"]
        print(
            "Documentation: {documented}/{total} definitions ({coverage_percent:.2f}%); "
            "{missing} missing, {invalid} invalid".format(**summary)
        )
    return 1 if args.check and report["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
