#!/usr/bin/env python3
"""Report package size and internal import dependencies without third-party tools."""

from __future__ import annotations

import argparse
import ast
import json
import runpy
from pathlib import Path

BOUNDARY_CHECKER = runpy.run_path(str(Path(__file__).with_name("dependency_boundaries.py")))
dependency_boundary_violations = BOUNDARY_CHECKER["dependency_boundary_violations"]

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "content_creator"
PACKAGE_NAME = "content_creator"
MAX_MODULE_LINES = 500
MAX_RUNTIME_FACADE_LINES = 300


def module_name(path: Path) -> str:
    relative = path.relative_to(PACKAGE_ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join([PACKAGE_NAME, *parts]) if parts else PACKAGE_NAME


def _import_from_targets(target: str, node: ast.ImportFrom) -> set[str]:
    """Resolve imported child modules without mistaking imported symbols for modules."""
    children = set()
    for alias in node.names:
        candidate = ".".join(part for part in (target, alias.name) if part)
        relative = candidate.split(".")[1:]
        path = PACKAGE_ROOT.joinpath(*relative)
        if path.with_suffix(".py").exists() or (path / "__init__.py").exists():
            children.add(candidate)
    return children or {target}


def internal_import_edges(path: Path, tree: ast.AST) -> list[dict[str, object]]:
    """Return line-aware package imports made by one parsed module."""
    current = module_name(path)
    package_parts = current.split(".") if path.name == "__init__.py" else current.split(".")[:-1]
    edges: set[tuple[str, int]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            edges.update(
                (alias.name, node.lineno)
                for alias in node.names
                if alias.name.startswith(PACKAGE_NAME)
            )
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                keep = len(package_parts) - (node.level - 1)
                base = package_parts[:keep]
                target = ".".join([*base, *(node.module or "").split(".")]).rstrip(".")
            else:
                target = node.module or ""
            if target.startswith(PACKAGE_NAME):
                edges.update(
                    (imported, node.lineno)
                    for imported in _import_from_targets(target, node)
                    if imported != current
                )
    return [
        {"target": target, "line": line}
        for target, line in sorted(edges, key=lambda item: (item[0], item[1]))
    ]


def internal_imports(path: Path, tree: ast.AST) -> list[str]:
    """Return unique package imports made by one parsed module."""
    return sorted({str(edge["target"]) for edge in internal_import_edges(path, tree)})


def terminal_output_lines(tree: ast.AST) -> list[int]:
    """Return direct built-in print calls made by one production module."""
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "print"
    )


def command_persistence_accesses(tree: ast.AST) -> list[dict[str, object]]:
    """Return command-layer access to mutable persistence implementation details."""
    accesses = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "RunStore":
                accesses.append({"line": node.lineno, "expression": "RunStore(...)"})
        if not isinstance(node, ast.Attribute):
            continue
        expression = ast.unparse(node)
        if expression == "RunStore._atomic_text" or expression.endswith(".orchestrator.store"):
            accesses.append({"line": node.lineno, "expression": expression})
    return sorted(accesses, key=lambda item: (int(item["line"]), str(item["expression"])))


def docstring_lines(tree: ast.AST) -> set[int]:
    """Return source lines occupied by definition docstrings."""
    lines: set[int] = set()
    definition_types = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, definition_types) or not node.body:
            continue
        statement = node.body[0]
        if not (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            continue
        lines.update(range(statement.lineno, (statement.end_lineno or statement.lineno) + 1))
    return lines


def deleted_parameters(tree: ast.AST) -> list[dict[str, object]]:
    """Return function parameters explicitly deleted from production code."""

    class DeleteVisitor(ast.NodeVisitor):
        def __init__(self, parameters: set[str]):
            self.parameters = parameters
            self.matches: list[dict[str, object]] = []

        def visit_Delete(self, node: ast.Delete) -> None:
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in self.parameters:
                    self.matches.append({"parameter": target.id, "line": node.lineno})

        def visit_FunctionDef(self, _node: ast.FunctionDef) -> None:
            return

        def visit_AsyncFunctionDef(self, _node: ast.AsyncFunctionDef) -> None:
            return

        def visit_ClassDef(self, _node: ast.ClassDef) -> None:
            return

    violations = []
    function_types = (ast.FunctionDef, ast.AsyncFunctionDef)
    for function in (node for node in ast.walk(tree) if isinstance(node, function_types)):
        arguments = function.args
        parameters = {
            argument.arg
            for argument in [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
        }
        if arguments.vararg:
            parameters.add(arguments.vararg.arg)
        if arguments.kwarg:
            parameters.add(arguments.kwarg.arg)
        visitor = DeleteVisitor(parameters)
        for statement in function.body:
            visitor.visit(statement)
        for match in visitor.matches:
            violations.append({"function": function.name, **match})
    return violations


def defined_classes(tree: ast.AST) -> list[dict[str, object]]:
    """Return top-level classes and the bases they declare."""
    return [
        {"name": node.name, "bases": [ast.unparse(base) for base in node.bases]}
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    ]


def architecture_advisories(modules: list[dict[str, object]]) -> dict[str, object]:
    """Build non-blocking cohesion and inheritance review signals."""
    importer_counts = {str(module["module"]): 0 for module in modules}
    for module in modules:
        for imported in module["imports"]:
            if imported in importer_counts:
                importer_counts[imported] += 1
    single_importers = sorted(
        name for name, count in importer_counts.items() if count == 1 and name != PACKAGE_NAME
    )
    owners = {
        str(item["name"]): str(module["module"]) for module in modules for item in module["classes"]
    }
    cross_file_inheritance = []
    for module in modules:
        for item in module["classes"]:
            for base in item["bases"]:
                owner = owners.get(str(base).rsplit(".", 1)[-1])
                if owner and owner != module["module"]:
                    cross_file_inheritance.append(
                        {
                            "class": f"{module['module']}.{item['name']}",
                            "base": f"{owner}.{str(base).rsplit('.', 1)[-1]}",
                        }
                    )
    return {
        "single_importer_modules": single_importers,
        "cross_file_inheritance": cross_file_inheritance,
    }


def _depends_on(graph: dict[str, set[str]], start: str, target: str) -> bool:
    """Return whether one internal module transitively imports another."""
    pending = [start]
    visited = set()
    while pending:
        current = pending.pop()
        if current == target:
            return True
        if current in visited:
            continue
        visited.add(current)
        pending.extend(graph.get(current, set()) - visited)
    return False


def import_cycle_edges(modules: list[dict[str, object]]) -> list[dict[str, str]]:
    """Return every direct internal import that participates in a cycle."""
    names = {str(module["module"]) for module in modules}
    graph = {
        str(module["module"]): {
            str(imported) for imported in module["imports"] if str(imported) in names
        }
        for module in modules
    }
    return [
        {"source": source, "target": target}
        for source, targets in sorted(graph.items())
        for target in sorted(targets)
        if _depends_on(graph, target, source)
    ]


def build_report() -> dict:
    """Build module size and dependency measurements for production code."""
    modules = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        import_edges = internal_import_edges(path, tree)
        physical_line_count = len(source.splitlines())
        implementation_line_count = physical_line_count - len(docstring_lines(tree))
        modules.append(
            {
                "module": module_name(path),
                "path": str(path.relative_to(ROOT)),
                "line_count": physical_line_count,
                "implementation_line_count": implementation_line_count,
                "imports": sorted({str(edge["target"]) for edge in import_edges}),
                "import_edges": import_edges,
                "classes": defined_classes(tree),
                "deleted_parameters": deleted_parameters(tree),
                "terminal_output_lines": terminal_output_lines(tree),
                "command_persistence_accesses": command_persistence_accesses(tree),
            }
        )
    report = {
        "package": PACKAGE_NAME,
        "summary": {
            "module_count": len(modules),
            "line_count": sum(module["line_count"] for module in modules),
            "implementation_line_count": sum(
                module["implementation_line_count"] for module in modules
            ),
        },
        "modules": modules,
    }
    report["import_cycle_edges"] = import_cycle_edges(modules)
    report["advisories"] = architecture_advisories(modules)
    return report


def module_structure_violations(name: str, module: dict) -> list[str]:
    """Return size, parameter, terminal, and command-boundary violations."""
    violations = []
    if module["implementation_line_count"] > MAX_MODULE_LINES:
        violations.append(
            "{} exceeds the {}-line production-module implementation limit "
            "({} implementation lines; {} physical lines)".format(
                name,
                MAX_MODULE_LINES,
                module["implementation_line_count"],
                module["line_count"],
            )
        )
    for deletion in module["deleted_parameters"]:
        violations.append(
            "{}:{} deletes parameter {!r} in {}; prefix intentionally unused parameters "
            "with an underscore instead".format(
                module["path"],
                deletion["line"],
                deletion["parameter"],
                deletion["function"],
            )
        )
    if name != "content_creator.cli" and not name.startswith("content_creator.commands"):
        for line in module.get("terminal_output_lines", []):
            violations.append(
                "{}:{} writes directly to terminal output outside the entry-point layer".format(
                    module["path"], line
                )
            )
    if name.startswith("content_creator.commands"):
        for access in module.get("command_persistence_accesses", []):
            violations.append(
                "{}:{} command accesses mutable persistence through {}".format(
                    module["path"], access["line"], access["expression"]
                )
            )
    return violations


def architecture_violations(report: dict) -> list[str]:
    """Evaluate precise dependency rules that have an established green baseline."""
    modules = {module["module"]: module for module in report["modules"]}
    violations = dependency_boundary_violations(list(modules.values()))
    for edge in import_cycle_edges(list(modules.values())):
        violations.append("internal import cycle includes {source} -> {target}".format(**edge))
    cli = modules.get("content_creator.cli")
    if not cli or cli["implementation_line_count"] > 100:
        violations.append("content_creator.cli must remain a façade of at most 100 lines")

    runtime = modules.get("content_creator.commands.runtime")
    if not runtime or runtime["implementation_line_count"] > MAX_RUNTIME_FACADE_LINES:
        violations.append(
            "content_creator.commands.runtime must remain a façade of at most {} lines".format(
                MAX_RUNTIME_FACADE_LINES
            )
        )

    for name, module in sorted(modules.items()):
        violations.extend(module_structure_violations(name, module))

    orchestrator = modules.get("content_creator.orchestrator", {})
    orchestrator_imports = set(orchestrator.get("imports", []))
    for forbidden in ("content_creator.visuals", "content_creator.voice_assessment"):
        if forbidden in orchestrator_imports:
            violations.append("content_creator.orchestrator must not import {}".format(forbidden))
    for required in ("content_creator.capabilities", "content_creator.stages"):
        if required not in orchestrator_imports:
            violations.append("content_creator.orchestrator must compose {}".format(required))

    for domain_module in ("content_creator.voices", "content_creator.perspectives"):
        imports = set(modules.get(domain_module, {}).get("imports", []))
        if "content_creator.versioned_artifacts" not in imports:
            violations.append(
                "{} must use shared versioned-artifact mechanics".format(domain_module)
            )
    return violations


def main() -> int:
    """Render the architecture report and optionally enforce its rules."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--check", action="store_true", help="enforce accepted dependency rules")
    args = parser.parse_args()
    report = build_report()
    violations = architecture_violations(report)
    if args.json:
        report["violations"] = violations
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1 if args.check and violations else 0
    print(
        "{module_count} modules, {implementation_line_count} implementation lines "
        "({line_count} physical)".format(**report["summary"])
    )
    for module in sorted(
        report["modules"], key=lambda item: item["implementation_line_count"], reverse=True
    ):
        print("{implementation_line_count:5}  {module} ({line_count} physical)".format(**module))
    advisories = report["advisories"]
    print(
        "Advisories: {} single-importer modules; {} cross-file inheritance relationships".format(
            len(advisories["single_importer_modules"]),
            len(advisories["cross_file_inheritance"]),
        )
    )
    if args.check:
        if violations:
            for violation in violations:
                print("ERROR: {}".format(violation))
        else:
            print("Architecture rules: passed")
    return 1 if args.check and violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
