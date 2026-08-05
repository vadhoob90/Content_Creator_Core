"""Validate Google Style docstrings against Python definition contracts."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from documentation_vocabulary import (
    IMPERATIVE_VERBS,
    PLACEHOLDER_PHRASES,
    SECTION_HEADERS,
    SECTION_ORDER,
)


@dataclass(frozen=True)
class DocumentationIssue:
    """Describe one stable, machine-readable documentation violation."""

    code: str
    kind: str
    path: str
    line: int
    qualified_name: str
    message: str


@dataclass(frozen=True)
class ParameterContract:
    """Describe one callable parameter expected in an ``Args`` section."""

    name: str
    type_name: str
    default: str | None


class ExplicitRaiseVisitor(ast.NodeVisitor):
    """Collect explicit exception types without entering nested callables."""

    def __init__(self) -> None:
        """Initialize an empty exception-name collection."""
        self.names: set[str] = set()

    def visit_Raise(self, node: ast.Raise) -> None:
        """Record a statically named exception from a ``raise`` statement."""
        exception = node.exc
        if isinstance(exception, ast.Call):
            exception = exception.func
        name = expression_name(exception)
        if name and (
            isinstance(node.exc, ast.Call)
            or name.rsplit(".", 1)[-1].endswith(("Error", "Exception"))
        ):
            self.names.add(name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Skip nested synchronous functions."""

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Skip nested asynchronous functions."""

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Skip nested classes."""


def expression_name(node: ast.AST | None) -> str | None:
    """Return a dotted name for a statically named expression."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = expression_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def issue(
    code: str,
    path: str,
    kind: str,
    node: ast.AST,
    qualified_name: str,
    message: str,
) -> DocumentationIssue:
    """Create one documentation issue for a definition."""
    return DocumentationIssue(
        code=code,
        kind=kind,
        path=path,
        line=getattr(node, "lineno", 1),
        qualified_name=qualified_name,
        message=message,
    )


def parse_sections(docstring: str) -> tuple[list[str], dict[str, list[str]], list[str]]:
    """Split a cleaned docstring into prose and named Google Style sections."""
    prose: list[str] = []
    sections: dict[str, list[str]] = {}
    order: list[str] = []
    current: str | None = None
    for line in docstring.splitlines():
        stripped = line.strip()
        if stripped in SECTION_HEADERS:
            current = stripped[:-1]
            sections.setdefault(current, [])
            order.append(current)
        elif current is None:
            prose.append(line)
        else:
            sections[current].append(line)
    return prose, sections, order


def parameters(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ParameterContract]:
    """Return explicit callable parameters and whether each has a default."""
    positional = [*node.args.posonlyargs, *node.args.args]
    default_start = len(positional) - len(node.args.defaults)
    contracts: list[ParameterContract] = []
    for index, argument in enumerate(positional):
        if argument.arg in {"self", "cls"}:
            continue
        default = node.args.defaults[index - default_start] if index >= default_start else None
        contracts.append(
            ParameterContract(
                argument.arg,
                annotation_text(argument.annotation),
                ast.unparse(default) if default is not None else None,
            )
        )
    if node.args.vararg:
        contracts.append(
            ParameterContract(
                f"*{node.args.vararg.arg}",
                f"tuple[{annotation_text(node.args.vararg.annotation)}, ...]",
                None,
            )
        )
    contracts.extend(
        ParameterContract(
            argument.arg,
            annotation_text(argument.annotation),
            ast.unparse(default) if default is not None else None,
        )
        for argument, default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True)
    )
    if node.args.kwarg:
        contracts.append(
            ParameterContract(
                f"**{node.args.kwarg.arg}",
                f"dict[str, {annotation_text(node.args.kwarg.annotation)}]",
                None,
            )
        )
    return contracts


def annotation_text(annotation: ast.AST | None) -> str:
    """Render a signature annotation as stable contract text."""
    return ast.unparse(annotation).replace("'", "") if annotation is not None else "object"


def normalized_text(value: str) -> str:
    """Normalize type and default text for documentation comparisons."""
    return re.sub(r"[\s`'\"]", "", value)


def argument_entries(lines: list[str]) -> tuple[dict[str, tuple[str, str]], set[str]]:
    """Parse argument entries and identify entries missing explicit type text."""
    entries: dict[str, tuple[str, str]] = {}
    missing_types: set[str] = set()
    typed = re.compile(r"^\s*(\*{0,2}[A-Za-z_]\w*)\s+\(([^)]+)\):\s+(.+)$")
    untyped = re.compile(r"^\s*(\*{0,2}[A-Za-z_]\w*):\s+(.+)$")
    current_name: str | None = None
    for line in lines:
        match = typed.match(line)
        if match:
            current_name = match.group(1)
            entries[current_name] = (match.group(2).strip(), match.group(3).strip())
            continue
        match = untyped.match(line)
        if match:
            current_name = match.group(1)
            missing_types.add(current_name)
            entries[current_name] = ("", match.group(2).strip())
            continue
        if current_name and line.strip():
            type_name, description = entries[current_name]
            entries[current_name] = (type_name, f"{description} {line.strip()}")
    return entries, missing_types


def section_entries(lines: list[str]) -> set[str]:
    """Return leading type names from ``Returns`` or ``Raises`` entries."""
    entries: set[str] = set()
    for line in lines:
        match = re.match(r"^\s*([^:]+):\s+(.+)$", line)
        if match:
            entries.add(match.group(1).strip())
    return entries


def explicit_raises(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Return statically named exception types raised directly by a callable."""
    visitor = ExplicitRaiseVisitor()
    for statement in node.body:
        visitor.visit(statement)
    return visitor.names


def implementation_line_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Measure callable lines without counting its docstring."""
    total = (node.end_lineno or node.lineno) - node.lineno + 1
    if not node.body or not isinstance(node.body[0], ast.Expr):
        return total
    expression = node.body[0]
    if not isinstance(expression.value, ast.Constant) or not isinstance(
        expression.value.value, str
    ):
        return total
    return total - ((expression.end_lineno or expression.lineno) - expression.lineno + 1)


def validate_summary(
    path: str,
    kind: str,
    node: ast.AST,
    qualified_name: str,
    summary: str,
) -> list[DocumentationIssue]:
    """Validate summary punctuation, sentence count, and imperative mood."""
    issues: list[DocumentationIssue] = []
    if not summary.endswith((".", "!", "?")) or re.search(r"[.!?]\s+\S", summary[:-1]):
        issues.append(
            issue(
                "summary-not-single-sentence",
                path,
                kind,
                node,
                qualified_name,
                "Use one punctuated sentence on the summary line.",
            )
        )
    first_word = re.sub(r"[^A-Za-z-]", "", summary.split(maxsplit=1)[0]).lower()
    if first_word not in IMPERATIVE_VERBS:
        issues.append(
            issue(
                "summary-not-imperative",
                path,
                kind,
                node,
                qualified_name,
                "Start the summary with an active imperative verb.",
            )
        )
    return issues


def validate_section_order(
    path: str,
    kind: str,
    node: ast.AST,
    qualified_name: str,
    sections: dict[str, list[str]],
    order: list[str],
) -> list[DocumentationIssue]:
    """Require Google Style sections to appear in their canonical order."""
    expected = [name for name in SECTION_ORDER if name in sections]
    if order == expected:
        return []
    return [
        issue(
            "section-order",
            path,
            kind,
            node,
            qualified_name,
            "Order Google Style sections as Args, Returns, then Raises.",
        )
    ]


def validate_arguments(
    path: str,
    kind: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    qualified_name: str,
    sections: dict[str, list[str]],
) -> list[DocumentationIssue]:
    """Match typed ``Args`` entries and defaults to the callable signature."""
    issues: list[DocumentationIssue] = []
    contracts = parameters(node)
    entries, missing_types = argument_entries(sections.get("Args", []))
    expected_names = {contract.name for contract in contracts}
    for name in sorted(expected_names - entries.keys()):
        issues.append(
            issue("arg-missing", path, kind, node, qualified_name, f"Document {name!r} in Args.")
        )
    for name in sorted(entries.keys() - expected_names):
        issues.append(
            issue("arg-stale", path, kind, node, qualified_name, f"Remove Args entry {name!r}.")
        )
    for name in sorted(missing_types):
        issues.append(
            issue(
                "arg-missing-type",
                path,
                kind,
                node,
                qualified_name,
                f"Add explicit type text for parameter {name!r}.",
            )
        )
    for contract in contracts:
        entry = entries.get(contract.name)
        if entry and normalized_text(entry[0]) != normalized_text(contract.type_name):
            issues.append(
                issue(
                    "arg-type-mismatch",
                    path,
                    kind,
                    node,
                    qualified_name,
                    f"Match the documented type for parameter {contract.name!r} to its annotation.",
                )
            )
        if contract.default is not None and (
            entry is None
            or "defaults to" not in entry[1].lower()
            or normalized_text(contract.default) not in normalized_text(entry[1])
        ):
            issues.append(
                issue(
                    "default-undocumented",
                    path,
                    kind,
                    node,
                    qualified_name,
                    f"State the default value for parameter {contract.name!r}.",
                )
            )
    return issues


def validate_returns(
    path: str,
    kind: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    qualified_name: str,
    sections: dict[str, list[str]],
) -> list[DocumentationIssue]:
    """Require a typed ``Returns`` entry for every callable."""
    entries = section_entries(sections.get("Returns", []))
    if not entries:
        return [
            issue(
                "returns-missing",
                path,
                kind,
                node,
                qualified_name,
                "Add a Returns section with type and output meaning.",
            )
        ]
    expected = "None" if node.name == "__init__" else annotation_text(node.returns)
    if any(normalized_text(entry) == normalized_text(expected) for entry in entries):
        return []
    return [
        issue(
            "returns-type-mismatch",
            path,
            kind,
            node,
            qualified_name,
            f"Document the annotated return type {expected!r}.",
        )
    ]


def validate_raises(
    path: str,
    kind: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    qualified_name: str,
    sections: dict[str, list[str]],
) -> list[DocumentationIssue]:
    """Match ``Raises`` entries to statically named explicit exceptions."""
    issues: list[DocumentationIssue] = []
    raised = explicit_raises(node)
    documented = section_entries(sections.get("Raises", []))
    for name in sorted(raised - documented):
        issues.append(
            issue(
                "raises-missing",
                path,
                kind,
                node,
                qualified_name,
                f"Document explicitly raised exception {name!r}.",
            )
        )
    for name in sorted(documented - raised):
        issues.append(
            issue(
                "raises-stale",
                path,
                kind,
                node,
                qualified_name,
                f"Remove exception {name!r}, which is not raised explicitly.",
            )
        )
    return issues


def validate_description(
    path: str,
    kind: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    qualified_name: str,
    prose: list[str],
) -> list[DocumentationIssue]:
    """Require context for callables above the readability review threshold."""
    if implementation_line_count(node) <= 40 or "\n".join(prose[1:]).strip():
        return []
    return [
        issue(
            "description-missing",
            path,
            kind,
            node,
            qualified_name,
            "Add context for this callable's non-trivial implementation.",
        )
    ]


def validate_prose_quality(
    path: str,
    kind: str,
    node: ast.AST,
    qualified_name: str,
    docstring: str,
) -> list[DocumentationIssue]:
    """Reject known placeholder phrases from earlier mechanical documentation."""
    lowered = docstring.lower()
    if not any(phrase in lowered for phrase in PLACEHOLDER_PHRASES):
        return []
    return [
        issue(
            "placeholder-prose",
            path,
            kind,
            node,
            qualified_name,
            "Replace template prose with concrete domain behavior.",
        )
    ]


def validate_docstring(
    path: str,
    kind: str,
    node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef | ast.Module,
    qualified_name: str,
    docstring: str,
) -> list[DocumentationIssue]:
    """Validate one present docstring against the repository standard."""
    prose, sections, order = parse_sections(docstring)
    summary = prose[0].strip() if prose else ""
    issues = validate_summary(path, kind, node, qualified_name, summary)
    issues.extend(validate_prose_quality(path, kind, node, qualified_name, docstring))
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return issues
    issues.extend(validate_section_order(path, kind, node, qualified_name, sections, order))
    issues.extend(validate_arguments(path, kind, node, qualified_name, sections))
    issues.extend(validate_returns(path, kind, node, qualified_name, sections))
    issues.extend(validate_raises(path, kind, node, qualified_name, sections))
    issues.extend(validate_description(path, kind, node, qualified_name, prose))
    return issues
