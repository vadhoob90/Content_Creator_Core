"""Provide ingestion capabilities."""

from __future__ import annotations

import hashlib
import html
import re
import urllib.request
import zipfile
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable, Tuple
from xml.etree import ElementTree


class IngestionError(RuntimeError):
    """Report ingestion failures."""

    pass


def normalize_text(value: str) -> str:
    """Return the normalize text.

    Args:
        value (str): The value to process.

    Returns:
        str: The resulting text for normalize text.
    """
    value = html.unescape(value)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[^\S\n]+", " ", line).strip() for line in value.splitlines()]
    value = "\n".join(lines)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def content_hash(value: str) -> str:
    """Return the content hash.

    Args:
        value (str): The value to process.

    Returns:
        str: The resulting text for content hash.
    """
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _html_text(raw: str) -> Tuple[str, str]:
    """Return the html text.

    Args:
        raw (str): The raw text processed when html text.

    Returns:
        Tuple[str, str]: The resulting html text values in their documented order.
    """
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw, re.I | re.S)
    title = normalize_text(re.sub(r"<[^>]+>", " ", title_match.group(1))) if title_match else ""
    raw = re.sub(r"<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", raw, flags=re.I | re.S)
    raw = re.sub(
        r"</?(?:article|aside|blockquote|br|div|h[1-6]|li|main|p|section)[^>]*>",
        "\n\n",
        raw,
        flags=re.I,
    )
    return title, normalize_text(re.sub(r"<[^>]+>", " ", raw))


def _docx_text(path: Path) -> str:
    """Return the docx text.

    Args:
        path (Path): The filesystem path to inspect or update.

    Returns:
        str: The resulting text for docx text.
    """
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    paragraphs = []
    for paragraph in (node for node in root.iter() if node.tag.endswith("}p")):
        text = " ".join(node.text or "" for node in paragraph.iter() if node.tag.endswith("}t"))
        if text.strip():
            paragraphs.append(text)
    return normalize_text("\n\n".join(paragraphs))


def _pdf_text(path: Path) -> str:
    """Return the pdf text.

    Args:
        path (Path): The filesystem path to inspect or update.

    Returns:
        str: The resulting text for pdf text.

    Raises:
        IngestionError: If the ingestion operation cannot complete.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise IngestionError("PDF support requires the pypdf dependency") from exc
    return normalize_text("\n\n".join(page.extract_text() or "" for page in PdfReader(path).pages))


def read_source(locator: str) -> Tuple[str, str, str]:
    """Read the source.

    Args:
        locator (str): The source locator used to retrieve the document.

    Returns:
        Tuple[str, str, str]: The loaded source values in their documented order.

    Raises:
        IngestionError: If the ingestion operation cannot complete.
    """
    if locator.startswith(("http://", "https://")):
        with urllib.request.urlopen(locator, timeout=20) as response:
            raw = response.read().decode(
                response.headers.get_content_charset() or "utf-8", errors="replace"
            )
        title, text = _html_text(raw)
        return "webpage", title or locator, text
    path = Path(locator)
    if not path.exists():
        raise IngestionError("Source does not exist: {}".format(locator))
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm"}:
        title, text = _html_text(path.read_text(encoding="utf-8"))
        return "html", title or path.stem, text
    if suffix == ".docx":
        return "docx", path.stem, _docx_text(path)
    if suffix == ".pdf":
        return "pdf", path.stem, _pdf_text(path)
    kind = "transcript" if "transcript" in path.name.lower() else "text"
    return (
        kind,
        path.stem,
        normalize_text(path.read_text(encoding="utf-8")),
    )


def is_near_duplicate(text: str, existing: Iterable[str], threshold: float = 0.92) -> bool:
    """Return whether near duplicate satisfies the required condition.

    Args:
        text (str): The text to process.
        existing (Iterable[str]): The existing value passed to is near duplicate.
        threshold (float): The threshold value that controls is near duplicate. Defaults
            to ``0.92``.

    Returns:
        bool: Whether is near duplicate satisfies the documented condition.
    """
    return any(SequenceMatcher(None, text, prior).ratio() >= threshold for prior in existing)
