"""Resolve source-list and document arguments for voice commands."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional


def source_lines(path: Optional[str]) -> List[str]:
    """Return the source lines.

    Args:
        path (Optional[str]): The filesystem path to inspect or update.

    Returns:
        List[str]: The resulting source lines values in their documented order.
    """
    if not path:
        return []
    return [
        line.strip()
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def documents(values: List[str]) -> List[str]:
    """Return the documents.

    Args:
        values (List[str]): The values collection consumed while documents.

    Returns:
        List[str]: The resulting documents values in their documented order.
    """
    resolved_documents: List[str] = []
    for value in values:
        path = Path(value).expanduser().resolve()
        if path.is_dir():
            resolved_documents.extend(
                str(candidate)
                for candidate in sorted(path.rglob("*"))
                if candidate.is_file()
                and candidate.suffix.lower() in {".txt", ".md", ".html", ".pdf", ".docx"}
            )
        else:
            resolved_documents.append(str(path))
    return resolved_documents
