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
    pass


def normalize_text(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def content_hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _html_text(raw: str) -> Tuple[str, str]:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw, re.I | re.S)
    title = normalize_text(re.sub(r"<[^>]+>", " ", title_match.group(1))) if title_match else ""
    raw = re.sub(r"<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", raw, flags=re.I | re.S)
    return title, normalize_text(re.sub(r"<[^>]+>", " ", raw))


def _docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    return normalize_text(" ".join(node.text or "" for node in root.iter()))


def _pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise IngestionError("PDF support requires the pypdf dependency") from exc
    return normalize_text(" ".join(page.extract_text() or "" for page in PdfReader(path).pages))


def read_source(locator: str) -> Tuple[str, str, str]:
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
    return any(SequenceMatcher(None, text, prior).ratio() >= threshold for prior in existing)
